
import pymysql
from flask import Blueprint, current_app, jsonify, request

from . import cifrado, db, sesion, validar
from .errores import ErrorHttp

bp = Blueprint("publico", __name__, url_prefix="/api")

MSG_ACCESO = "Escribe la contraseña del grupo para continuar."


def _grupo_activo(id_texto):
    """Grupo activo por identificador (no por nombre); 400 si el id no es válido, 404 si no existe o está inactivo."""
    gid = validar.id_entero(id_texto)
    if not gid:
        raise ErrorHttp(400, "Grupo no válido.")
    g = db.una("SELECT id, clave, num_alumnos, acceso_cifrado, acceso_version FROM grupos WHERE id = %s AND activo = 1", (gid,))
    if not g:
        raise ErrorHttp(404, "El grupo no existe o no está activo.")
    return g


def _bloqueo(alumnos, encuestas):
    """Mensaje si el grupo NO puede recibir más encuestas; None si todavía hay lugar."""
    if alumnos <= 0:
        return "Este grupo no tiene alumnos registrados, así que no recibe encuestas. Avisa al administrador."
    if encuestas > alumnos:
        return ("Se detectó una inconsistencia en este grupo: hay más encuestas que alumnos registrados. "
                "No se aceptan más encuestas hasta que el administrador la revise.")
    if encuestas == alumnos:
        return "Este grupo ya alcanzó el límite de encuestas (una por alumno registrado)."
    return None


def _estado(g):
    n = db.una("SELECT COUNT(*) AS n FROM encuestas WHERE grupo_id = %s", (g["id"],))["n"]
    return {"alumnos": g["num_alumnos"], "encuestas": n, "disponibles": max(0, g["num_alumnos"] - n)}, n


def _exigir_acceso(g):
    """403 si el navegador no tiene una autorización vigente PARA ESTE grupo y para la contraseña actual."""
    acc = sesion.acceso_actual()
    if (not acc or acc.get("grupo") != g["id"] or acc.get("version") != g["acceso_version"] or not g["acceso_cifrado"]):
        raise ErrorHttp(403, MSG_ACCESO)


@bp.get("/grupos")
def grupos():
    # Solo lo necesario para elegir el grupo: nunca contraseñas ni indicadores internos
    return jsonify(db.filas("SELECT id, clave, descripcion FROM grupos WHERE activo = 1 ORDER BY clave"))


@bp.post("/grupos/<id_texto>/acceso")
def acceso(id_texto):
    """Verifica la contraseña del grupo EN EL SERVIDOR y abre la autorización. Nunca devuelve ni registra la contraseña."""
    g = _grupo_activo(id_texto)
    ip, lim_ip, lim_g = request.remote_addr, current_app.extensions["limite_acceso_ip"], current_app.extensions["limite_acceso_grupo"]
    if lim_ip.excedido(f"{ip}|{g['id']}") or lim_g.excedido(g["id"]):
        raise ErrorHttp(429, "Demasiados intentos con contraseña incorrecta. Espera unos minutos e inténtalo de nuevo.")

    cuerpo = request.get_json(silent=True)
    clave = cuerpo.get("clave") if isinstance(cuerpo, dict) else None
    if not isinstance(clave, str) or not clave or len(clave) > 200:
        raise ErrorHttp(400, "Escribe la contraseña del grupo.")
    if not g["acceso_cifrado"]:
        raise ErrorHttp(409, "El acceso a la encuesta de este grupo todavía no está disponible: "
                             "el administrador debe configurar la contraseña del grupo.")
    if not cifrado.coincide(g["acceso_cifrado"], clave):
        lim_ip.registrar(f"{ip}|{g['id']}")
        lim_g.registrar(g["id"])
        raise ErrorHttp(401, "La contraseña no es válida.")

    estado, n = _estado(g)
    motivo = _bloqueo(g["num_alumnos"], n)
    if motivo:                               # contraseña correcta, pero no se supera el límite de encuestas
        raise ErrorHttp(409, motivo)
    token, vida = sesion.crear_acceso(g["id"], g["acceso_version"])
    resp = jsonify({"ok": True, **estado})
    resp.set_cookie(sesion.COOKIE_ACCESO, token, httponly=True, samesite="Strict", max_age=vida,
                    secure=current_app.config["EVAL"]["COOKIE_SECURE"], path="/")
    return resp


@bp.get("/grupos/<id_texto>/cuestionario")
def cuestionario(id_texto):
    """Tabla de profesores/materias del grupo + preguntas. Exige la autorización abierta con la contraseña."""
    g = _grupo_activo(id_texto)
    _exigir_acceso(g)
    estado, n = _estado(g)
    motivo = _bloqueo(g["num_alumnos"], n)
    if motivo:
        raise ErrorHttp(409, motivo)
    asignaciones = db.filas(
        """SELECT p.id AS profesor_id, p.nombre AS profesor, m.id AS materia_id, m.nombre AS materia
             FROM asignaciones a
             JOIN profesores p ON p.id = a.profesor_id AND p.activo = 1
             JOIN materias m ON m.id = a.materia_id AND m.activo = 1
            WHERE a.grupo_id = %s AND a.activo = 1
            ORDER BY p.nombre, m.nombre""", (g["id"],))
    preguntas = db.filas("SELECT num_pregunta AS num, texto FROM preguntas ORDER BY num_pregunta")
    return jsonify({"grupo": {"id": g["id"], "clave": g["clave"]}, "disponibilidad": estado,
                    "asignaciones": asignaciones, "preguntas": preguntas})


@bp.post("/encuestas")
def guardar_encuesta():
    # Freno a ráfagas desde una misma IP (un salón comparte IP, por eso el tope es holgado)
    lim = current_app.extensions["limite_envios"]
    if lim.excedido(request.remote_addr):
        raise ErrorHttp(429, "Demasiados envíos desde esta red. Intenta de nuevo en unos minutos.")
    lim.registrar(request.remote_addr)

    datos, errores = validar.encuesta(request.get_json(silent=True))
    if errores:
        raise ErrorHttp(400, "Revisa los datos capturados.", errores)
    gid = datos["grupo_id"]
    acc = sesion.acceso_actual()
    if not acc or acc.get("grupo") != gid:       # primer filtro, barato; el definitivo se repite dentro de la transacción
        raise ErrorHttp(403, MSG_ACCESO)

    conn = db.conexion()
    conn.begin()
    try:
        with conn.cursor() as cur:
            # 1) Se bloquea la fila del grupo: los envíos del MISMO grupo se atienden uno por uno, así el conteo
            #    de encuestas y el INSERT no se pueden cruzar con otro envío (ni con un cambio de contraseña o de alumnos).
            cur.execute("SELECT id, num_alumnos, acceso_cifrado, acceso_version FROM grupos WHERE id = %s AND activo = 1 FOR UPDATE", (gid,))
            g = cur.fetchone()
            if not g:
                raise ErrorHttp(404, "El grupo no existe o no está activo.", {"grupo": "El grupo no existe o no está activo."})
            # 2) La autorización debe seguir vigente para la contraseña ACTUAL del grupo
            if acc.get("version") != g["acceso_version"] or not g["acceso_cifrado"]:
                raise ErrorHttp(403, "La contraseña del grupo cambió. " + MSG_ACCESO)
            # 3) Límite de encuestas
            cur.execute("SELECT COUNT(*) AS n FROM encuestas WHERE grupo_id = %s", (gid,))
            n = cur.fetchone()["n"]
            motivo = _bloqueo(g["num_alumnos"], n)
            if motivo:
                raise ErrorHttp(409, motivo)
            # 4) Las evaluaciones recibidas deben ser EXACTAMENTE las asignaciones activas del grupo
            cur.execute(
                """SELECT a.profesor_id, a.materia_id
                     FROM asignaciones a
                     JOIN profesores p ON p.id = a.profesor_id AND p.activo = 1
                     JOIN materias m ON m.id = a.materia_id AND m.activo = 1
                    WHERE a.grupo_id = %s AND a.activo = 1 FOR SHARE""", (gid,))
            esperadas = {(f["profesor_id"], f["materia_id"]) for f in cur.fetchall()}
            enviadas = {(e["profesor_id"], e["materia_id"]) for e in datos["evaluaciones"]}
            if not esperadas:
                raise ErrorHttp(409, "Este grupo no tiene profesores asignados. Avisa al administrador.")
            if enviadas - esperadas:
                raise ErrorHttp(400, "Revisa los datos capturados.", {
                    "evaluaciones": "La encuesta incluye profesores o materias que no corresponden a tu grupo."})
            if esperadas - enviadas:
                raise ErrorHttp(400, "Revisa los datos capturados.", {
                    "evaluaciones": "Faltan evaluaciones de profesores de tu grupo. Si la lista cambió, "
                                    "recarga la página y vuelve a contestar."})
            # 5) Todo en una sola operación lógica: encuesta + evaluaciones + respuestas
            cur.execute("INSERT INTO encuestas (grupo_id) VALUES (%s)", (gid,))
            encuesta_id = cur.lastrowid
            filas_resp = []
            for e in datos["evaluaciones"]:
                cur.execute("INSERT INTO evaluaciones (encuesta_id, grupo_id, profesor_id, materia_id, comentario) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (encuesta_id, gid, e["profesor_id"], e["materia_id"], e["comentario"]))
                eid = cur.lastrowid
                filas_resp += [(eid, i + 1, cal) for i, cal in enumerate(e["respuestas"])]
            cur.executemany("INSERT INTO respuestas (evaluacion_id, num_pregunta, calificacion) VALUES (%s, %s, %s)", filas_resp)
        conn.commit()
    except BaseException as e:
        conn.rollback()                       # nada queda a medias: ni la encuesta ni parte de sus evaluaciones
        if isinstance(e, pymysql.err.OperationalError) and e.args and e.args[0] in (1205, 1213):
            raise ErrorHttp(503, "El servidor está ocupado. Vuelve a presionar «Enviar encuesta» en unos segundos.")
        raise
    # La autorización se consume: para contestar otra encuesta hay que escribir de nuevo la contraseña
    sesion.cerrar_acceso()
    resp = jsonify({"ok": True, "id": encuesta_id, "disponibles": max(0, g["num_alumnos"] - n - 1)})
    resp.delete_cookie(sesion.COOKIE_ACCESO, path="/")
    resp.status_code = 201
    return resp
