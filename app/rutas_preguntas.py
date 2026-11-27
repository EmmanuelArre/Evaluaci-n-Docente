"""CRUD de preguntas de la encuesta (solo administrador: app.before_request exige la sesión en todo /api/admin).

Reglas:
  · El número de pregunta (num_pregunta) es el identificador interno. Una pregunta nueva recibe el siguiente al mayor
    que exista; al eliminar una no se renumeran las demás. Para el alumno y para los reportes las preguntas se muestran
    en orden (1, 2, 3, …) sin importar los huecos.
  · Eliminar una pregunta BORRA también todas sus respuestas (los promedios históricos cambian). Siempre debe quedar
    al menos una pregunta.
  · Editar el texto no toca las respuestas ya guardadas.
  · Cada cambio ocurre en una transacción con la tabla de preguntas bloqueada (FOR UPDATE), igual que el resto del CRUD."""
import re

from flask import Blueprint, jsonify, request

from . import db, validar
from .errores import ErrorHttp

bp = Blueprint("preguntas", __name__, url_prefix="/api/admin/preguntas")

MAX_PREGUNTAS = 50          # tope práctico: el formulario del alumno repite todas las preguntas por cada profesor
MIN_TEXTO = 10
MAX_TEXTO = 255
_RE_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _cuerpo():
    c = request.get_json(silent=True)
    return c if isinstance(c, dict) else {}


def _num(valor):
    n = validar.id_entero(valor)
    if not n or n > 255:                         # num_pregunta es TINYINT UNSIGNED
        raise ErrorHttp(400, "Número de pregunta no válido.")
    return n


def _leer_texto(body):
    t = body.get("texto")
    if not isinstance(t, str):
        raise ErrorHttp(400, "Revisa la pregunta.", {"texto": "La pregunta es obligatoria."})
    t = re.sub(r"\s+", " ", t).strip()
    if _RE_CONTROL.search(t):
        raise ErrorHttp(400, "Revisa la pregunta.", {"texto": "Contiene caracteres no permitidos."})
    if len(t) < MIN_TEXTO:
        raise ErrorHttp(400, "Revisa la pregunta.", {"texto": f"Mínimo {MIN_TEXTO} caracteres."})
    if len(t) > MAX_TEXTO:
        raise ErrorHttp(400, "Revisa la pregunta.", {"texto": f"Máximo {MAX_TEXTO} caracteres."})
    return t


def _repetida(texto, filas, excepto=None):
    """¿Ya existe otra pregunta con el mismo texto (sin distinguir mayúsculas)?"""
    c = texto.casefold()
    return any(f["num_pregunta"] != excepto and f["texto"].casefold() == c for f in filas)


def _escapar_like(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@bp.get("")
def listar():
    """Lista las preguntas en orden, con cuántas respuestas tiene cada una. ?q= busca dentro del texto."""
    q = re.sub(r"\s+", " ", (request.args.get("q") or "")).strip()
    if len(q) > MAX_TEXTO:
        raise ErrorHttp(400, "La búsqueda es demasiado larga.")
    total = db.una("SELECT COUNT(*) AS n FROM preguntas")["n"]
    sql = ("SELECT p.num_pregunta AS num, p.texto, "
           "(SELECT COUNT(*) FROM respuestas r WHERE r.num_pregunta = p.num_pregunta) AS respuestas "
           "FROM preguntas p")
    par = []
    if q:
        sql += " WHERE p.texto LIKE %s"
        par.append("%" + _escapar_like(q) + "%")
    sql += " ORDER BY p.num_pregunta"
    filas = db.filas(sql, par)
    # «orden» = lugar que ocupa entre TODAS las preguntas (el que ve el alumno), aunque la búsqueda filtre
    todas = [f["num_pregunta"] for f in db.filas("SELECT num_pregunta FROM preguntas ORDER BY num_pregunta")]
    lugar = {n: i + 1 for i, n in enumerate(todas)}
    for f in filas:
        f["orden"] = lugar.get(f["num"])
    return jsonify({"preguntas": filas, "total": total, "maximo": MAX_PREGUNTAS, "busqueda": q})


def _bloquear(cur):
    cur.execute("SELECT num_pregunta, texto FROM preguntas ORDER BY num_pregunta FOR UPDATE")
    return cur.fetchall()


@bp.post("")
def crear():
    texto = _leer_texto(_cuerpo())
    conn = db.conexion()
    conn.begin()
    try:
        with conn.cursor() as cur:
            filas = _bloquear(cur)
            if len(filas) >= MAX_PREGUNTAS:
                raise ErrorHttp(409, f"Ya hay {MAX_PREGUNTAS} preguntas, que es el máximo permitido.")
            if _repetida(texto, filas):
                raise ErrorHttp(409, "Ya existe una pregunta con ese texto.", {"texto": "Ya existe una pregunta con ese texto."})
            nuevo = (filas[-1]["num_pregunta"] + 1) if filas else 1
            if nuevo > 255:
                raise ErrorHttp(409, "Se agotaron los números de pregunta disponibles. Avisa al responsable del sistema.")
            cur.execute("INSERT INTO preguntas (num_pregunta, texto) VALUES (%s, %s)", (nuevo, texto))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return jsonify({"ok": True, "num": nuevo}), 201


@bp.put("/<num_texto>")
def editar(num_texto):
    num = _num(num_texto)
    texto = _leer_texto(_cuerpo())
    conn = db.conexion()
    conn.begin()
    try:
        with conn.cursor() as cur:
            filas = _bloquear(cur)
            if not any(f["num_pregunta"] == num for f in filas):
                raise ErrorHttp(404, "La pregunta no existe.")
            if _repetida(texto, filas, excepto=num):
                raise ErrorHttp(409, "Ya existe una pregunta con ese texto.", {"texto": "Ya existe una pregunta con ese texto."})
            cur.execute("UPDATE preguntas SET texto = %s WHERE num_pregunta = %s", (texto, num))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return jsonify({"ok": True})


@bp.delete("/<num_texto>")
def eliminar(num_texto):
    """Borra la pregunta y todas sus respuestas, en una sola transacción (o se hace todo o no se hace nada)."""
    num = _num(num_texto)
    conn = db.conexion()
    conn.begin()
    try:
        with conn.cursor() as cur:
            filas = _bloquear(cur)
            if not any(f["num_pregunta"] == num for f in filas):
                raise ErrorHttp(404, "La pregunta no existe.")
            if len(filas) <= 1:
                raise ErrorHttp(409, "Debe quedar al menos una pregunta en la encuesta.")
            cur.execute("DELETE FROM respuestas WHERE num_pregunta = %s", (num,))
            borradas = cur.rowcount
            cur.execute("DELETE FROM preguntas WHERE num_pregunta = %s", (num,))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return jsonify({"ok": True, "respuestas_borradas": borradas})
