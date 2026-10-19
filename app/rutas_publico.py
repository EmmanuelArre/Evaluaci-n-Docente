"""Endpoints para el alumno (sin sesión): catálogo de profesores/materias y envío de la evaluación."""
from flask import Blueprint, current_app, jsonify, request

from . import db, validar
from .errores import ErrorHttp

bp = Blueprint("publico", __name__, url_prefix="/api")


@bp.get("/profesores")
def profesores():
    return jsonify(db.filas("SELECT id, nombre FROM profesores WHERE activo = 1 ORDER BY nombre"))


@bp.get("/profesores/<id_texto>/materias")
def materias_de_profesor(id_texto):
    pid = validar.id_entero(id_texto)
    if not pid:
        raise ErrorHttp(400, "Profesor no válido.")
    return jsonify(db.filas(
        """SELECT m.id, m.nombre
             FROM profesor_materia pm
             JOIN materias m ON m.id = pm.materia_id AND m.activo = 1
             JOIN profesores p ON p.id = pm.profesor_id AND p.activo = 1
            WHERE pm.profesor_id = %s
            ORDER BY m.nombre""", (pid,)))


@bp.post("/evaluaciones")
def guardar_evaluacion():
    # Freno a ráfagas desde una misma IP (un salón comparte IP, por eso el tope es holgado)
    lim = current_app.extensions["limite_envios"]
    if lim.excedido(request.remote_addr):
        raise ErrorHttp(429, "Demasiados envíos desde esta red. Intenta de nuevo en unos minutos.")
    lim.registrar(request.remote_addr)

    datos, errores = validar.evaluacion(request.get_json(silent=True))
    if errores:
        raise ErrorHttp(400, "Revisa los datos capturados.", errores)

    conn = db.conexion()
    conn.begin()
    try:
        with conn.cursor() as cur:
            # Las relaciones se comprueban dentro de la transacción y se bloquean las filas leídas
            cur.execute("SELECT id FROM grupos WHERE clave = %s AND activo = 1 FOR SHARE", (datos["grupo"],))
            grupo = cur.fetchone()
            cur.execute("SELECT id FROM profesores WHERE id = %s AND activo = 1 FOR SHARE", (datos["profesor_id"],))
            prof = cur.fetchone()
            cur.execute("SELECT id FROM materias WHERE id = %s AND activo = 1 FOR SHARE", (datos["materia_id"],))
            mat = cur.fetchone()

            errores = {}
            if not grupo:
                errores["grupo"] = "El grupo no existe o no está activo."
            if not prof:
                errores["profesor"] = "El profesor no existe o no está activo."
            if not mat:
                errores["materia"] = "La materia no existe o no está activa."
            if prof and mat:
                cur.execute("SELECT 1 AS ok FROM profesor_materia WHERE profesor_id = %s AND materia_id = %s FOR SHARE",
                            (datos["profesor_id"], datos["materia_id"]))
                if not cur.fetchone():
                    errores["materia"] = "La materia no pertenece al profesor seleccionado."
            if errores:
                raise ErrorHttp(400, "Revisa los datos capturados.", errores)

            cur.execute("INSERT INTO evaluaciones (grupo_id, profesor_id, materia_id, comentario) VALUES (%s, %s, %s, %s)",
                        (grupo["id"], datos["profesor_id"], datos["materia_id"], datos["comentario"]))
            nuevo_id = cur.lastrowid
            cur.executemany("INSERT INTO respuestas (evaluacion_id, num_pregunta, calificacion) VALUES (%s, %s, %s)",
                            [(nuevo_id, i + 1, cal) for i, cal in enumerate(datos["respuestas"])])
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return jsonify({"ok": True, "id": nuevo_id}), 201
