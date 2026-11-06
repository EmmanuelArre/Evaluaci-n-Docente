"""CRUD del administrador: grupos, profesores, materias, asignaciones y borrado de evaluaciones.
(El acceso exige sesión: lo impone app.before_request para toda ruta bajo /api/admin.)"""
from collections import defaultdict

from flask import Blueprint, jsonify, request

from . import cifrado, db, validar
from .errores import ErrorHttp, es_fk_inexistente, traducir_mysql

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _id(valor):
    i = validar.id_entero(valor)
    if not i:
        raise ErrorHttp(400, "Identificador no válido.")
    return i


def _cuerpo():
    c = request.get_json(silent=True)
    return c if isinstance(c, dict) else {}


# ============================ GRUPOS ============================
# La contraseña de acceso de cada grupo se guarda CIFRADA (app/cifrado.py). Aquí, y solo aquí (ruta protegida por la
# sesión del administrador y con Cache-Control: no-store), se descifra para mostrarla en el panel.
@bp.get("/grupos")
def listar_grupos():
    filas = db.filas(
        """SELECT g.id, g.clave, g.descripcion, g.activo, g.num_alumnos, g.acceso_cifrado,
                  (SELECT COUNT(*) FROM encuestas e WHERE e.grupo_id = g.id) AS encuestas,
                  (SELECT COUNT(*) FROM evaluaciones v WHERE v.grupo_id = g.id) AS evaluaciones
             FROM grupos g ORDER BY g.clave""")
    for f in filas:
        token = f.pop("acceso_cifrado")
        f["tiene_clave"] = bool(token)
        f["clave_acceso"] = cifrado.descifrar(token) if token else None
        f["clave_ilegible"] = bool(token) and f["clave_acceso"] is None     # la clave de cifrado no corresponde
        f["disponibles"] = max(0, f["num_alumnos"] - f["encuestas"])
        f["inconsistente"] = f["encuestas"] > f["num_alumnos"]
    return jsonify(filas)


def _leer_grupo(body, es_alta):
    errores = {}
    clave, e1 = validar.grupo_clave(body.get("clave"))
    if e1:
        errores["clave"] = e1
    desc, e2 = validar.descripcion(body.get("descripcion"))
    if e2:
        errores["descripcion"] = e2
    activo = validar.booleano(body.get("activo"))
    if activo is None:
        errores["activo"] = "Valor no válido."
    alumnos = None
    if es_alta or body.get("num_alumnos") is not None:        # en la edición, omitirlo = no cambiarlo
        alumnos, e3 = validar.num_alumnos(body.get("num_alumnos"))
        if e3:
            errores["num_alumnos"] = e3
    acceso = None
    if "clave_acceso" in body and (es_alta is False or body.get("clave_acceso") not in (None, "")):
        acceso, e4 = validar.clave_acceso(body.get("clave_acceso"))
        if e4:
            errores["clave_acceso"] = e4
    if errores:
        raise ErrorHttp(400, "Revisa los datos del grupo.", errores)
    return clave, desc, activo, alumnos, acceso


def _clave_en_uso(clave, excepto_id=None):
    """¿Otro grupo ya usa esta contraseña? Cada grupo debe tener la suya (así la de otro grupo no abre este)."""
    for f in db.filas("SELECT id, acceso_cifrado FROM grupos WHERE acceso_cifrado IS NOT NULL"):
        if f["id"] != excepto_id and cifrado.coincide(f["acceso_cifrado"], clave):
            return True
    return False


@bp.post("/grupos")
def crear_grupo():
    clave, desc, activo, alumnos, acceso = _leer_grupo(_cuerpo(), True)
    if acceso and _clave_en_uso(acceso):
        raise ErrorHttp(409, "Esa contraseña ya la usa otro grupo.", {"clave_acceso": "Esa contraseña ya la usa otro grupo. Cada grupo debe tener la suya."})
    try:
        _, nuevo = db.ejecutar(
            "INSERT INTO grupos (clave, descripcion, activo, num_alumnos, acceso_cifrado) VALUES (%s, %s, %s, %s, %s)",
            (clave, desc, activo, alumnos, cifrado.cifrar(acceso) if acceso else None))
    except Exception as e:
        raise traducir_mysql(e, "Ya existe un grupo con esa clave.")
    return jsonify({"ok": True, "id": nuevo}), 201


def _actualizar_grupo(gid, clave, desc, activo, alumnos, acceso):
    """UPDATE del grupo dentro de una transacción con la fila bloqueada (el mismo bloqueo que usa el envío de encuestas),
    para que cambiar alumnos o contraseña no se cruce con una encuesta que se está guardando."""
    conn = db.conexion()
    conn.begin()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, clave, descripcion, activo, num_alumnos, acceso_cifrado FROM grupos WHERE id = %s FOR UPDATE", (gid,))
            actual = cur.fetchone()
            if not actual:
                raise ErrorHttp(404, "El grupo no existe.")
            if alumnos is not None:
                cur.execute("SELECT COUNT(*) AS n FROM encuestas WHERE grupo_id = %s", (gid,))
                n = cur.fetchone()["n"]
                if alumnos < n:
                    raise ErrorHttp(409, f"No se puede reducir a {alumnos} alumnos: el grupo ya tiene {n} encuestas válidas y "
                                         f"el total de encuestas no puede superar el de alumnos. El mínimo permitido es {n}. "
                                         "Las encuestas no se eliminan automáticamente.",
                                    {"num_alumnos": f"Mínimo {n} (encuestas ya registradas)."})
            sets, par = ["clave = %s", "descripcion = %s", "activo = %s"], [clave, desc, activo]
            if alumnos is not None:
                sets.append("num_alumnos = %s"); par.append(alumnos)
            if acceso is not None and not cifrado.coincide(actual["acceso_cifrado"], acceso):
                sets += ["acceso_cifrado = %s", "acceso_version = acceso_version + 1"]   # la contraseña anterior deja de servir
                par.append(cifrado.cifrar(acceso))
            cur.execute(f"UPDATE grupos SET {', '.join(sets)} WHERE id = %s", par + [gid])
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


@bp.put("/grupos/<id_texto>")
def editar_grupo(id_texto):
    gid = _id(id_texto)
    clave, desc, activo, alumnos, acceso = _leer_grupo(_cuerpo(), False)
    if acceso and _clave_en_uso(acceso, gid):
        raise ErrorHttp(409, "Esa contraseña ya la usa otro grupo.", {"clave_acceso": "Esa contraseña ya la usa otro grupo. Cada grupo debe tener la suya."})
    try:
        _actualizar_grupo(gid, clave, desc, activo, alumnos, acceso)
    except Exception as e:
        raise traducir_mysql(e, "Ya existe un grupo con esa clave.")
    return jsonify({"ok": True})


@bp.put("/grupos/<id_texto>/acceso")
def asignar_acceso(id_texto):
    """Asigna o cambia SOLO la contraseña de acceso del grupo."""
    gid = _id(id_texto)
    acceso, e = validar.clave_acceso(_cuerpo().get("clave_acceso"))
    if e:
        raise ErrorHttp(400, "Revisa la contraseña.", {"clave_acceso": e})
    if _clave_en_uso(acceso, gid):
        raise ErrorHttp(409, "Esa contraseña ya la usa otro grupo.", {"clave_acceso": "Esa contraseña ya la usa otro grupo. Cada grupo debe tener la suya."})
    g = db.una("SELECT clave, descripcion, activo FROM grupos WHERE id = %s", (gid,))
    if not g:
        raise ErrorHttp(404, "El grupo no existe.")
    _actualizar_grupo(gid, g["clave"], g["descripcion"], g["activo"], None, acceso)
    return jsonify({"ok": True})


@bp.delete("/grupos/<id_texto>")
def eliminar_grupo(id_texto):
    gid = _id(id_texto)
    try:
        n, _ = db.ejecutar("DELETE FROM grupos WHERE id = %s", (gid,))
    except Exception as e:
        raise traducir_mysql(e, None, "No se puede eliminar: el grupo tiene evaluaciones. Desactívalo para conservar el historial.")
    if not n:
        raise ErrorHttp(404, "El grupo no existe.")
    return jsonify({"ok": True})


# ============================ ASIGNACIONES (grupo ↔ profesor ↔ materia) ============================
_SQL_ASIG = """SELECT a.profesor_id, p.nombre AS profesor, p.activo AS profesor_activo,
                      a.materia_id, m.nombre AS materia, m.activo AS materia_activa, a.activo,
                      (SELECT COUNT(*) FROM evaluaciones e
                        WHERE e.grupo_id = a.grupo_id AND e.profesor_id = a.profesor_id AND e.materia_id = a.materia_id) AS evaluaciones
                 FROM asignaciones a
                 JOIN profesores p ON p.id = a.profesor_id
                 JOIN materias m ON m.id = a.materia_id
                WHERE a.grupo_id = %s
                ORDER BY p.nombre, m.nombre"""


def _grupo_existe(gid):
    if not db.una("SELECT id FROM grupos WHERE id = %s", (gid,)):
        raise ErrorHttp(404, "El grupo no existe.")


@bp.get("/grupos/<id_texto>/asignaciones")
def listar_asignaciones(id_texto):
    gid = _id(id_texto)
    _grupo_existe(gid)
    return jsonify(db.filas(_SQL_ASIG, (gid,)))


@bp.post("/grupos/<id_texto>/asignaciones")
def crear_asignacion(id_texto):
    gid = _id(id_texto)
    cuerpo = _cuerpo()
    pid, mid = validar.id_entero(cuerpo.get("profesor_id")), validar.id_entero(cuerpo.get("materia_id"))
    errores = {}
    if not pid:
        errores["profesor_id"] = "Selecciona un profesor."
    if not mid:
        errores["materia_id"] = "Selecciona una materia."
    if errores:
        raise ErrorHttp(400, "Revisa la asignación.", errores)
    _grupo_existe(gid)
    if not db.una("SELECT id FROM profesores WHERE id = %s", (pid,)):
        raise ErrorHttp(404, "El profesor no existe.")
    if not db.una("SELECT id FROM materias WHERE id = %s", (mid,)):
        raise ErrorHttp(404, "La materia no existe.")
    if not db.una("SELECT 1 AS ok FROM profesor_materia WHERE profesor_id = %s AND materia_id = %s", (pid, mid)):
        raise ErrorHttp(400, "Esa materia no está asignada al profesor. Asígnala primero en la pestaña Profesores.",
                        {"materia_id": "El profesor no imparte esa materia."})
    try:
        db.ejecutar("INSERT INTO asignaciones (grupo_id, profesor_id, materia_id) VALUES (%s, %s, %s)", (gid, pid, mid))
    except Exception as e:
        if es_fk_inexistente(e):
            raise ErrorHttp(404, "El grupo, el profesor o la materia ya no existe.")
        raise traducir_mysql(e, "Ese profesor ya imparte esa materia a este grupo.")
    return jsonify({"ok": True}), 201


@bp.put("/grupos/<id_texto>/asignaciones/<profesor_texto>/<materia_texto>")
def cambiar_estado_asignacion(id_texto, profesor_texto, materia_texto):
    """Activa/desactiva una asignación (el historial de evaluaciones se conserva)."""
    gid, pid, mid = _id(id_texto), _id(profesor_texto), _id(materia_texto)
    crudo = _cuerpo().get("activo")
    activo = None if crudo is None else validar.booleano(crudo)
    if activo is None:
        raise ErrorHttp(400, "Valor de «activo» no válido.")
    n, _ = db.ejecutar("UPDATE asignaciones SET activo = %s WHERE grupo_id = %s AND profesor_id = %s AND materia_id = %s",
                       (activo, gid, pid, mid))
    if not n and not db.una("SELECT 1 AS ok FROM asignaciones WHERE grupo_id = %s AND profesor_id = %s AND materia_id = %s",
                            (gid, pid, mid)):
        raise ErrorHttp(404, "La asignación no existe.")
    return jsonify({"ok": True})


@bp.delete("/grupos/<id_texto>/asignaciones/<profesor_texto>/<materia_texto>")
def quitar_asignacion(id_texto, profesor_texto, materia_texto):
    gid, pid, mid = _id(id_texto), _id(profesor_texto), _id(materia_texto)
    try:
        n, _ = db.ejecutar("DELETE FROM asignaciones WHERE grupo_id = %s AND profesor_id = %s AND materia_id = %s",
                           (gid, pid, mid))
    except Exception as e:
        raise traducir_mysql(e, None, "No se puede quitar: esta asignación ya tiene evaluaciones. "
                                      "Desactívala para conservar el historial.")
    if not n:
        raise ErrorHttp(404, "La asignación no existe.")
    return jsonify({"ok": True})


# ============================ PROFESORES ============================
@bp.get("/profesores")
def listar_profesores():
    filas = db.filas(
        """SELECT p.id, p.nombre, p.nombres, p.apellido_paterno, p.apellido_materno, p.activo, COUNT(e.id) AS evaluaciones
             FROM profesores p LEFT JOIN evaluaciones e ON e.profesor_id = p.id
            GROUP BY p.id, p.nombre, p.nombres, p.apellido_paterno, p.apellido_materno, p.activo ORDER BY p.nombre""")
    mapa = defaultdict(list)
    if filas:
        ids = [f["id"] for f in filas]
        for r in db.filas(
                f"""SELECT pm.profesor_id, m.id, m.nombre, m.activo
                      FROM profesor_materia pm JOIN materias m ON m.id = pm.materia_id
                     WHERE pm.profesor_id IN ({db.marcadores(ids)}) ORDER BY m.nombre""", ids):
            mapa[r["profesor_id"]].append({"id": r["id"], "nombre": r["nombre"], "activo": r["activo"]})
        grupos = defaultdict(list)
        for r in db.filas(
                f"""SELECT DISTINCT a.profesor_id, g.id, g.clave, g.activo
                      FROM asignaciones a JOIN grupos g ON g.id = a.grupo_id
                     WHERE a.profesor_id IN ({db.marcadores(ids)}) AND a.activo = 1 ORDER BY g.clave""", ids):
            grupos[r["profesor_id"]].append({"id": r["id"], "clave": r["clave"], "activo": r["activo"]})
    else:
        grupos = {}
    for f in filas:
        f["materias"] = mapa.get(f["id"], [])
        f["grupos"] = grupos.get(f["id"], [])      # lista vacía = profesor sin grupos (no se ofrece a ningún alumno)
    return jsonify(filas)


def _leer_profesor(body, solo_estado=False):
    """Nombre(s) de pila (1 a 5) + apellido paterno (obligatorio) + apellido materno (opcional), se arma `nombre`."""
    activo = validar.booleano(body.get("activo"))
    errores = {}
    if activo is None:
        errores["activo"] = "Valor no válido."
    datos = None
    if not solo_estado:
        datos, e = validar.datos_profesor(body)
        errores.update(e or {})
    if errores:
        raise ErrorHttp(400, "Revisa los datos del profesor.", errores)
    return datos, activo


@bp.post("/profesores")
def crear_profesor():
    d, activo = _leer_profesor(_cuerpo())
    try:
        _, nuevo = db.ejecutar(
            "INSERT INTO profesores (nombre, nombres, apellido_paterno, apellido_materno, activo) VALUES (%s, %s, %s, %s, %s)",
            (d["nombre"], d["nombres"], d["apellido_paterno"], d["apellido_materno"], activo))
    except Exception as e:
        raise traducir_mysql(e, "Ya existe un profesor con ese nombre.")
    return jsonify({"ok": True, "id": nuevo}), 201


@bp.put("/profesores/<id_texto>")
def editar_profesor(id_texto):
    pid = _id(id_texto)
    cuerpo = _cuerpo()
    solo_estado = set(cuerpo) <= {"activo"} and "activo" in cuerpo    # activar/desactivar sin tocar el nombre
    d, activo = _leer_profesor(cuerpo, solo_estado)
    try:
        if solo_estado:
            n, _ = db.ejecutar("UPDATE profesores SET activo = %s WHERE id = %s", (activo, pid))
        else:
            n, _ = db.ejecutar(
                "UPDATE profesores SET nombre = %s, nombres = %s, apellido_paterno = %s, apellido_materno = %s, activo = %s WHERE id = %s",
                (d["nombre"], d["nombres"], d["apellido_paterno"], d["apellido_materno"], activo, pid))
    except Exception as e:
        raise traducir_mysql(e, "Ya existe un profesor con ese nombre.")
    if not n and not db.una("SELECT id FROM profesores WHERE id = %s", (pid,)):
        raise ErrorHttp(404, "El profesor no existe.")
    return jsonify({"ok": True})


@bp.delete("/profesores/<id_texto>")
def eliminar_profesor(id_texto):
    pid = _id(id_texto)
    try:
        n, _ = db.ejecutar("DELETE FROM profesores WHERE id = %s", (pid,))
    except Exception as e:
        raise traducir_mysql(e, None, "No se puede eliminar: el profesor tiene evaluaciones. Desactívalo para conservar el historial.")
    if not n:
        raise ErrorHttp(404, "El profesor no existe.")
    return jsonify({"ok": True})


# ---- Materias asignadas a un profesor ----
@bp.get("/profesores/<id_texto>/materias")
def materias_del_profesor(id_texto):
    pid = _id(id_texto)
    if not db.una("SELECT id FROM profesores WHERE id = %s", (pid,)):
        raise ErrorHttp(404, "El profesor no existe.")
    return jsonify(db.filas(
        """SELECT m.id, m.nombre, m.activo
             FROM profesor_materia pm JOIN materias m ON m.id = pm.materia_id
            WHERE pm.profesor_id = %s ORDER BY m.nombre""", (pid,)))


@bp.post("/profesores/<id_texto>/materias")
def asignar_materia(id_texto):
    pid = _id(id_texto)
    mid = validar.id_entero(_cuerpo().get("materia_id"))
    if not mid:
        raise ErrorHttp(400, "Selecciona una materia.", {"materia_id": "Selecciona una materia."})
    try:
        db.ejecutar("INSERT INTO profesor_materia (profesor_id, materia_id) VALUES (%s, %s)", (pid, mid))
    except Exception as e:
        if es_fk_inexistente(e):
            raise ErrorHttp(404, "El profesor o la materia no existe.")
        raise traducir_mysql(e, "Esa materia ya está asignada al profesor.")
    return jsonify({"ok": True}), 201


@bp.delete("/profesores/<id_texto>/materias/<materia_texto>")
def quitar_materia(id_texto, materia_texto):
    pid = _id(id_texto)
    mid = validar.id_entero(materia_texto)
    if not mid:
        raise ErrorHttp(400, "Materia no válida.")
    try:
        n, _ = db.ejecutar("DELETE FROM profesor_materia WHERE profesor_id = %s AND materia_id = %s", (pid, mid))
    except Exception as e:
        raise traducir_mysql(e, None, "No se puede quitar: esa materia está asignada a este profesor en uno o más grupos "
                                      "o ya tiene evaluaciones. Quita primero la asignación del grupo, o desactiva la materia o el profesor.")
    if not n:
        raise ErrorHttp(404, "La asignación no existe.")
    return jsonify({"ok": True})


# ============================ MATERIAS ============================
@bp.get("/materias")
def listar_materias():
    filas = db.filas(
        """SELECT m.id, m.nombre, m.activo, COUNT(e.id) AS evaluaciones
             FROM materias m LEFT JOIN evaluaciones e ON e.materia_id = m.id
            GROUP BY m.id, m.nombre, m.activo ORDER BY m.nombre""")
    mapa = defaultdict(list)
    for a in db.filas(
            """SELECT pm.materia_id, p.id, p.nombre FROM profesor_materia pm
                 JOIN profesores p ON p.id = pm.profesor_id ORDER BY p.nombre"""):
        mapa[a["materia_id"]].append({"id": a["id"], "nombre": a["nombre"]})
    for f in filas:
        f["profesores"] = mapa.get(f["id"], [])
    return jsonify(filas)


def _leer_materia(body):
    errores = {}
    nombre, e1 = validar.nombre_materia(body.get("nombre"))
    if e1:
        errores["nombre"] = e1
    activo = validar.booleano(body.get("activo"))
    if activo is None:
        errores["activo"] = "Valor no válido."
    if errores:
        raise ErrorHttp(400, "Revisa los datos de la materia.", errores)
    return nombre, activo


@bp.post("/materias")
def crear_materia():
    nombre, activo = _leer_materia(_cuerpo())
    try:
        _, nuevo = db.ejecutar("INSERT INTO materias (nombre, activo) VALUES (%s, %s)", (nombre, activo))
    except Exception as e:
        raise traducir_mysql(e, "Ya existe una materia con ese nombre.")
    return jsonify({"ok": True, "id": nuevo}), 201


@bp.put("/materias/<id_texto>")
def editar_materia(id_texto):
    mid = _id(id_texto)
    nombre, activo = _leer_materia(_cuerpo())
    try:
        n, _ = db.ejecutar("UPDATE materias SET nombre = %s, activo = %s WHERE id = %s", (nombre, activo, mid))
    except Exception as e:
        raise traducir_mysql(e, "Ya existe una materia con ese nombre.")
    if not n and not db.una("SELECT id FROM materias WHERE id = %s", (mid,)):
        raise ErrorHttp(404, "La materia no existe.")
    return jsonify({"ok": True})


@bp.delete("/materias/<id_texto>")
def eliminar_materia(id_texto):
    mid = _id(id_texto)
    try:
        n, _ = db.ejecutar("DELETE FROM materias WHERE id = %s", (mid,))
    except Exception as e:
        raise traducir_mysql(e, None, "No se puede eliminar: la materia tiene evaluaciones. Desactívala para conservar el historial.")
    if not n:
        raise ErrorHttp(404, "La materia no existe.")
    return jsonify({"ok": True})


# ============================ EVALUACIONES ============================
@bp.delete("/evaluaciones/<id_texto>")
def eliminar_evaluacion(id_texto):
    """Borra la evaluación de UN profesor-materia (sus respuestas caen en cascada). Si la encuesta se queda sin
    evaluaciones, también se borra la encuesta vacía, para que no siga ocupando un lugar del límite del grupo."""
    eid = _id(id_texto)
    conn = db.conexion()
    conn.begin()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT encuesta_id FROM evaluaciones WHERE id = %s FOR UPDATE", (eid,))
            fila = cur.fetchone()
            if not fila:
                raise ErrorHttp(404, "La evaluación no existe.")
            cur.execute("DELETE FROM evaluaciones WHERE id = %s", (eid,))
            cur.execute("DELETE FROM encuestas WHERE id = %s AND NOT EXISTS (SELECT 1 FROM evaluaciones WHERE encuesta_id = %s)",
                        (fila["encuesta_id"], fila["encuesta_id"]))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return jsonify({"ok": True})
