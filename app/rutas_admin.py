"""CRUD del administrador: grupos, profesores, materias, asignaciones y borrado de evaluaciones.
(El acceso exige sesión: lo impone app.before_request para toda ruta bajo /api/admin.)"""
from collections import defaultdict

from flask import Blueprint, jsonify, request

from . import db, validar
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
@bp.get("/grupos")
def listar_grupos():
    return jsonify(db.filas(
        """SELECT g.id, g.clave, g.descripcion, g.activo, COUNT(e.id) AS evaluaciones
             FROM grupos g LEFT JOIN evaluaciones e ON e.grupo_id = g.id
            GROUP BY g.id, g.clave, g.descripcion, g.activo ORDER BY g.clave"""))


def _leer_grupo(body):
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
    if errores:
        raise ErrorHttp(400, "Revisa los datos del grupo.", errores)
    return clave, desc, activo


@bp.post("/grupos")
def crear_grupo():
    clave, desc, activo = _leer_grupo(_cuerpo())
    try:
        _, nuevo = db.ejecutar("INSERT INTO grupos (clave, descripcion, activo) VALUES (%s, %s, %s)", (clave, desc, activo))
    except Exception as e:
        raise traducir_mysql(e, "Ya existe un grupo con esa clave.")
    return jsonify({"ok": True, "id": nuevo}), 201


@bp.put("/grupos/<id_texto>")
def editar_grupo(id_texto):
    gid = _id(id_texto)
    clave, desc, activo = _leer_grupo(_cuerpo())
    try:
        n, _ = db.ejecutar("UPDATE grupos SET clave = %s, descripcion = %s, activo = %s WHERE id = %s", (clave, desc, activo, gid))
    except Exception as e:
        raise traducir_mysql(e, "Ya existe un grupo con esa clave.")
    if not n and not db.una("SELECT id FROM grupos WHERE id = %s", (gid,)):
        raise ErrorHttp(404, "El grupo no existe.")
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


# ============================ PROFESORES ============================
@bp.get("/profesores")
def listar_profesores():
    filas = db.filas(
        """SELECT p.id, p.nombre, p.activo, COUNT(e.id) AS evaluaciones
             FROM profesores p LEFT JOIN evaluaciones e ON e.profesor_id = p.id
            GROUP BY p.id, p.nombre, p.activo ORDER BY p.nombre""")
    mapa = defaultdict(list)
    if filas:
        ids = [f["id"] for f in filas]
        for r in db.filas(
                f"""SELECT pm.profesor_id, m.id, m.nombre, m.activo
                      FROM profesor_materia pm JOIN materias m ON m.id = pm.materia_id
                     WHERE pm.profesor_id IN ({db.marcadores(ids)}) ORDER BY m.nombre""", ids):
            mapa[r["profesor_id"]].append({"id": r["id"], "nombre": r["nombre"], "activo": r["activo"]})
    for f in filas:
        f["materias"] = mapa.get(f["id"], [])
    return jsonify(filas)


def _leer_profesor(body):
    errores = {}
    nombre, e1 = validar.nombre_profesor(body.get("nombre"))
    if e1:
        errores["nombre"] = e1
    activo = validar.booleano(body.get("activo"))
    if activo is None:
        errores["activo"] = "Valor no válido."
    if errores:
        raise ErrorHttp(400, "Revisa los datos del profesor.", errores)
    return nombre, activo


@bp.post("/profesores")
def crear_profesor():
    nombre, activo = _leer_profesor(_cuerpo())
    try:
        _, nuevo = db.ejecutar("INSERT INTO profesores (nombre, activo) VALUES (%s, %s)", (nombre, activo))
    except Exception as e:
        raise traducir_mysql(e, "Ya existe un profesor con ese nombre.")
    return jsonify({"ok": True, "id": nuevo}), 201


@bp.put("/profesores/<id_texto>")
def editar_profesor(id_texto):
    pid = _id(id_texto)
    nombre, activo = _leer_profesor(_cuerpo())
    try:
        n, _ = db.ejecutar("UPDATE profesores SET nombre = %s, activo = %s WHERE id = %s", (nombre, activo, pid))
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
        raise traducir_mysql(e, None, "No se puede quitar: esa combinación profesor–materia ya tiene evaluaciones. "
                                      "Desactiva la materia o el profesor en su lugar.")
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
    eid = _id(id_texto)
    n, _ = db.ejecutar("DELETE FROM evaluaciones WHERE id = %s", (eid,))   # respuestas: ON DELETE CASCADE
    if not n:
        raise ErrorHttp(404, "La evaluación no existe.")
    return jsonify({"ok": True})
