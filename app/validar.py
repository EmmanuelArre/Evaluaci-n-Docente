"""Validaciones del servidor (repiten y amplían las del navegador; nunca se confía en el cliente)."""
import re

TOTAL_PREGUNTAS = 12
MIN_CALIF = 5
MAX_CALIF = 10
MAX_COMENTARIO = 200

RE_GRUPO = re.compile(r"[A-Z]{4}[0-9]{3}")
RE_NOMBRE_PROFESOR = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s.]+")
RE_USUARIO = re.compile(r"[A-Za-z0-9_.-]{3,30}")
PUNTUACION_MATERIA = set(" .,:;()-/&'+#")


def colapsar(s):
    return " ".join(s.split())


def id_entero(v):
    """Entero positivo a partir de 5 o "5". Rechaza 5.5, "abc", True, None…"""
    if isinstance(v, bool):
        return None
    if isinstance(v, int) and v > 0:
        return v
    if isinstance(v, str) and re.fullmatch(r"[0-9]{1,10}", v) and int(v) > 0:
        return int(v)
    return None


def grupo_clave(v):
    if not isinstance(v, str) or not v.strip():
        return None, "El grupo es obligatorio."
    clave = v.strip().upper()
    if not RE_GRUPO.fullmatch(clave):
        return None, "Formato: 4 letras y 3 dígitos (ej. GTID244)."
    return clave, None


def nombre_profesor(v):
    if not isinstance(v, str) or not v.strip():
        return None, "El profesor es obligatorio."
    n = colapsar(v)
    if len(n) < 5:
        return None, "Mínimo 5 caracteres."
    if len(n) > 60:
        return None, "Máximo 60 caracteres."
    if not RE_NOMBRE_PROFESOR.fullmatch(n):
        return None, "Solo letras y espacios."
    return n, None


def nombre_materia(v):
    if not isinstance(v, str) or not v.strip():
        return None, "La materia es obligatoria."
    n = colapsar(v)
    if len(n) < 3:
        return None, "Mínimo 3 caracteres."
    if len(n) > 60:
        return None, "Máximo 60 caracteres."
    if not all(c.isalnum() or c in PUNTUACION_MATERIA for c in n):
        return None, "Contiene caracteres no permitidos."
    return n, None


def descripcion(v):
    if v is None or v == "":
        return None, None
    if not isinstance(v, str):
        return None, "Descripción no válida."
    d = colapsar(v)
    if len(d) > 100:
        return None, "Máximo 100 caracteres."
    return (d or None), None


def usuario(v):
    if not isinstance(v, str) or not RE_USUARIO.fullmatch(v.strip()):
        return None, "Usuario no válido."
    return v.strip(), None


def booleano(v, defecto=True):
    """Devuelve 1/0, o None si el valor no es un booleano."""
    if v is None:
        return 1 if defecto else 0
    if v is True or (type(v) is int and v == 1):
        return 1
    if v is False or (type(v) is int and v == 0):
        return 0
    return None


def evaluacion(body):
    """Valida el cuerpo de una evaluación. Devuelve (datos, None) o (None, {campo: mensaje})."""
    if not isinstance(body, dict):
        return None, {"general": "Solicitud no válida."}
    errores = {}

    clave, err = grupo_clave(body.get("grupo"))
    if err:
        errores["grupo"] = err

    profesor_id = id_entero(body.get("profesor_id"))
    if not profesor_id:
        errores["profesor"] = "Selecciona un profesor."

    materia_id = id_entero(body.get("materia_id"))
    if not materia_id:
        errores["materia"] = "Selecciona una materia."

    respuestas = None
    r = body.get("respuestas")
    if not isinstance(r, list) or len(r) != TOTAL_PREGUNTAS:
        errores["preguntas"] = f"Se requieren las {TOTAL_PREGUNTAS} respuestas."
    else:
        malas = [i + 1 for i, v in enumerate(r)
                 if not (isinstance(v, int) and not isinstance(v, bool) and MIN_CALIF <= v <= MAX_CALIF)]
        if malas:
            errores["preguntas"] = (f"Calificación inválida (entero de {MIN_CALIF} a {MAX_CALIF}) "
                                    f"en la(s) pregunta(s): {', '.join(map(str, malas))}.")
        else:
            respuestas = r

    comentario = None
    c = body.get("comentario")
    if c is not None:
        if not isinstance(c, str):
            errores["comentario"] = "Comentario no válido."
        elif len(c) > MAX_COMENTARIO:
            errores["comentario"] = f"Máximo {MAX_COMENTARIO} caracteres."
        else:
            comentario = c.strip() or None

    if errores:
        return None, errores
    return {"grupo": clave, "profesor_id": profesor_id, "materia_id": materia_id,
            "respuestas": respuestas, "comentario": comentario}, None
