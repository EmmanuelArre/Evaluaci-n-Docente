"""Reportes (solo administrador). Todos los promedios se calculan en SQL a partir de `respuestas`;
las agrupaciones solo unen tablas N:1 (grupo, profesor, materia), de modo que ninguna respuesta
se cuenta dos veces. AVG se hace en doble precisión (`+ 0e0`) para no redondear dos veces."""
from flask import Blueprint, jsonify, request

from . import db, validar
from .errores import ErrorHttp

bp = Blueprint("reportes", __name__, url_prefix="/api/admin/reportes")

LIMITE_DETALLE = 1000
N = validar.TOTAL_PREGUNTAS

# Cada tipo de reporte define qué filtros son obligatorios
TIPOS = {
    "grupo": ["grupo"],
    "profesor": ["profesor"],
    "grupo-profesor": ["grupo", "profesor"],
    "general-grupo": ["grupo"],
}


def _num(v):
    return None if v is None else float(v)


@bp.get("/<tipo>")
def reporte(tipo):
    if tipo not in TIPOS:
        raise ErrorHttp(404, "Tipo de reporte no válido.")

    # ---- Filtros ----
    def leer(nombre):
        crudo = request.args.get(nombre)
        if crudo is None or crudo == "":
            return None
        i = validar.id_entero(crudo)
        if not i:
            raise ErrorHttp(400, f'Filtro "{nombre}" no válido.')
        return i

    f = {"grupo": leer("grupo"), "profesor": leer("profesor"), "materia": leer("materia")}
    for req in TIPOS[tipo]:
        if not f[req]:
            raise ErrorHttp(400, f"Selecciona {'un grupo' if req == 'grupo' else 'un profesor'} para generar el reporte.")

    # ---- Datos de los filtros (también valida que existan y que la materia sea del profesor) ----
    filtros = {}
    if f["grupo"]:
        g = db.una("SELECT id, clave, descripcion FROM grupos WHERE id = %s", (f["grupo"],))
        if not g:
            raise ErrorHttp(404, "El grupo seleccionado no existe.")
        filtros["grupo"] = g
    if f["profesor"]:
        p = db.una("SELECT id, nombre FROM profesores WHERE id = %s", (f["profesor"],))
        if not p:
            raise ErrorHttp(404, "El profesor seleccionado no existe.")
        filtros["profesor"] = p
    if f["materia"]:
        m = db.una("SELECT id, nombre FROM materias WHERE id = %s", (f["materia"],))
        if not m:
            raise ErrorHttp(404, "La materia seleccionada no existe.")
        if f["profesor"] and not db.una(
                "SELECT 1 AS ok FROM profesor_materia WHERE profesor_id = %s AND materia_id = %s", (f["profesor"], f["materia"])):
            raise ErrorHttp(400, "La materia no está asignada al profesor seleccionado.")
        filtros["materia"] = m

    cond, par = [], []
    for campo, col in (("grupo", "e.grupo_id"), ("profesor", "e.profesor_id"), ("materia", "e.materia_id")):
        if f[campo]:
            cond.append(f"{col} = %s")
            par.append(f[campo])
    WHERE = ("WHERE " + " AND ".join(cond)) if cond else ""

    # ---- 1) Resumen: evaluaciones, respuestas y promedio de todas las respuestas ----
    r1 = db.una(
        f"""SELECT COUNT(DISTINCT e.id) AS evaluaciones, COUNT(*) AS respuestas, AVG(r.calificacion + 0e0) AS promedio
              FROM evaluaciones e JOIN respuestas r ON r.evaluacion_id = e.id {WHERE}""", par)
    resumen = {"evaluaciones": r1["evaluaciones"], "respuestas": r1["respuestas"], "promedio": _num(r1["promedio"])}

    base = {"tipo": tipo, "filtros": filtros, "resumen": resumen, "totalPreguntas": N,
            "porPregunta": [], "porProfesorMateria": [], "porProfesor": [], "porMateria": [],
            "detalle": [], "detalleTruncado": False, "vacio": resumen["evaluaciones"] == 0}
    if base["vacio"]:
        return jsonify(base)

    # ---- 2) Promedio por pregunta ----
    pp = {x["num_pregunta"]: _num(x["promedio"]) for x in db.filas(
        f"""SELECT r.num_pregunta, AVG(r.calificacion + 0e0) AS promedio
              FROM evaluaciones e JOIN respuestas r ON r.evaluacion_id = e.id {WHERE}
             GROUP BY r.num_pregunta ORDER BY r.num_pregunta""", par)}
    base["porPregunta"] = [pp.get(i + 1) for i in range(N)]

    # ---- 3) Por grupo + profesor + materia (con el promedio de cada pregunta) ----
    pm = db.filas(
        f"""SELECT e.grupo_id, g.clave AS grupo, e.profesor_id, p.nombre AS profesor, e.materia_id, m.nombre AS materia,
                   r.num_pregunta, AVG(r.calificacion + 0e0) AS promedio
              FROM evaluaciones e
              JOIN respuestas r ON r.evaluacion_id = e.id
              JOIN grupos g ON g.id = e.grupo_id
              JOIN profesores p ON p.id = e.profesor_id
              JOIN materias m ON m.id = e.materia_id
              {WHERE}
             GROUP BY e.grupo_id, g.clave, e.profesor_id, p.nombre, e.materia_id, m.nombre, r.num_pregunta
             ORDER BY g.clave, p.nombre, m.nombre, r.num_pregunta""", par)
    totales = {(t["grupo_id"], t["profesor_id"], t["materia_id"]): t for t in db.filas(
        f"""SELECT e.grupo_id, e.profesor_id, e.materia_id, COUNT(DISTINCT e.id) AS evaluaciones, AVG(r.calificacion + 0e0) AS promedio
              FROM evaluaciones e JOIN respuestas r ON r.evaluacion_id = e.id {WHERE}
             GROUP BY e.grupo_id, e.profesor_id, e.materia_id""", par)}
    filas = {}
    for x in pm:
        k = (x["grupo_id"], x["profesor_id"], x["materia_id"])
        if k not in filas:
            t = totales[k]
            filas[k] = {"grupo_id": x["grupo_id"], "grupo": x["grupo"], "profesor_id": x["profesor_id"],
                        "profesor": x["profesor"], "materia_id": x["materia_id"], "materia": x["materia"],
                        "evaluaciones": t["evaluaciones"], "promedio": _num(t["promedio"]), "preguntas": [None] * N}
        filas[k]["preguntas"][x["num_pregunta"] - 1] = _num(x["promedio"])
    base["porProfesorMateria"] = list(filas.values())

    # ---- 4) Por profesor y 5) por materia ----
    base["porProfesor"] = [{**x, "promedio": _num(x["promedio"])} for x in db.filas(
        f"""SELECT e.profesor_id AS id, p.nombre, COUNT(DISTINCT e.id) AS evaluaciones, AVG(r.calificacion + 0e0) AS promedio
              FROM evaluaciones e JOIN respuestas r ON r.evaluacion_id = e.id JOIN profesores p ON p.id = e.profesor_id
              {WHERE} GROUP BY e.profesor_id, p.nombre ORDER BY p.nombre""", par)]
    base["porMateria"] = [{**x, "promedio": _num(x["promedio"])} for x in db.filas(
        f"""SELECT e.materia_id AS id, m.nombre, COUNT(DISTINCT e.id) AS evaluaciones, AVG(r.calificacion + 0e0) AS promedio
              FROM evaluaciones e JOIN respuestas r ON r.evaluacion_id = e.id JOIN materias m ON m.id = e.materia_id
              {WHERE} GROUP BY e.materia_id, m.nombre ORDER BY m.nombre""", par)]

    # ---- 6) Detalle por evaluación (equivale a la tabla "por alumno" original) ----
    ev = db.filas(
        f"""SELECT e.id, e.creado_en, e.comentario, g.clave AS grupo, p.nombre AS profesor, m.nombre AS materia
              FROM evaluaciones e
              JOIN grupos g ON g.id = e.grupo_id JOIN profesores p ON p.id = e.profesor_id JOIN materias m ON m.id = e.materia_id
              {WHERE} ORDER BY e.creado_en, e.id LIMIT %s""", par + [LIMITE_DETALLE + 1])
    base["detalleTruncado"] = len(ev) > LIMITE_DETALLE
    ev = ev[:LIMITE_DETALLE]
    if ev:
        ids = [e["id"] for e in ev]
        por_eval = {}
        for r in db.filas(
                f"""SELECT evaluacion_id, num_pregunta, calificacion FROM respuestas
                     WHERE evaluacion_id IN ({db.marcadores(ids)}) ORDER BY evaluacion_id, num_pregunta""", ids):
            por_eval.setdefault(r["evaluacion_id"], [None] * N)[r["num_pregunta"] - 1] = r["calificacion"]
        base["detalle"] = [{"id": e["id"], "fecha": e["creado_en"], "grupo": e["grupo"], "profesor": e["profesor"],
                            "materia": e["materia"], "comentario": e["comentario"], "respuestas": por_eval.get(e["id"], [])}
                           for e in ev]
    return jsonify(base)
