"""Validaciones del servidor (repiten y amplían las del navegador; nunca se confía en el cliente)."""
import re
import unicodedata

TOTAL_PREGUNTAS = 12
MIN_CALIF = 5
MAX_CALIF = 10
MAX_COMENTARIO = 200
MAX_ALUMNOS = 99
MAX_EVALUACIONES_POR_ENCUESTA = 40

RE_GRUPO = re.compile(r"[A-Z]{4}[0-9]{3}")
LETRAS = "A-Za-zÀ-ÖØ-öø-ÿ"
# Cada palabra: letras, con guion o apóstrofo internos (María-José, O'Connor) y punto opcional al final (J.)
RE_PALABRA_NOMBRE = re.compile(rf"[{LETRAS}]+(?:[-'’][{LETRAS}]+)*\.?")
# Partículas que van en minúscula dentro de un nombre ("Juan Carlos de la Cruz")
PARTICULAS_MATERIA = {"de", "del", "la", "las", "los", "el", "y", "e", "o", "u", "a", "al", "en", "con", "para", "por"}
RE_ROMANO = re.compile(r"\(?(?:I{1,3}|IV|V|VI{1,3}|IX|X)\)?")   # I a X, solo si ya vienen en mayúsculas
PARTICULAS = {"de", "del", "la", "las", "los", "y", "van", "von", "der", "den", "da", "das", "do", "dos", "di", "du"}
RE_USUARIO = re.compile(r"[A-Za-z0-9_.-]{3,30}")
PUNTUACION_MATERIA = set(" .,:;()-/&'+#")


def colapsar(s):
    return " ".join(s.split())


def normalizar_nombre(s, materia=False):
    """Formato uniforme: sin espacios sobrantes, Cada Palabra Con Inicial Mayúscula y el resto en minúscula;
    las partículas (de, del, la, los, y…) quedan en minúscula salvo al inicio.
    "MARÍA FERNANDA LÓPEZ GARCÍA" → "María Fernanda López García"; "juan carlos de la cruz" → "Juan Carlos de la Cruz".
    Con materia=True se aplica la misma regla a nombres de materia: además se capitaliza tras ( / , : ; & + #
    y se respetan los números romanos escritos en mayúsculas ("PROGRAMACIÓN II" → "Programación II").
    Normaliza también las tildes escritas como letra + acento suelto (típico de macOS)."""
    s = colapsar(unicodedata.normalize("NFC", s))
    separadores = r"-'’(/.,:;&+#" if materia else r"-'’"
    patron = rf"(^|[{re.escape(separadores)}])([^{re.escape(separadores)}])"
    palabras = []
    for i, palabra in enumerate(s.split(" ")):
        bajo = palabra.lower()
        if materia and RE_ROMANO.fullmatch(palabra):
            palabras.append(palabra)
            continue
        if i > 0 and bajo in (PARTICULAS_MATERIA if materia else PARTICULAS):
            palabras.append(bajo)
            continue
        palabras.append(re.sub(patron, lambda m: m.group(1) + m.group(2).upper(), bajo))
    return " ".join(palabras)


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


def nombre_persona(v, etiqueta="El nombre", minimo=5, maximo=60, min_palabras=1):
    """Valida y NORMALIZA el nombre de una persona. Devuelve (nombre_normalizado, None) o (None, mensaje)."""
    if not isinstance(v, str) or not v.strip():
        return None, f"{etiqueta} es obligatorio."
    n = normalizar_nombre(v)
    if len(n) < minimo:
        return None, f"Mínimo {minimo} caracteres."
    if len(n) > maximo:
        return None, f"Máximo {maximo} caracteres."
    if len(n.split(" ")) < min_palabras:
        return None, "Escribe al menos un nombre y un apellido."
    if not all(RE_PALABRA_NOMBRE.fullmatch(p) for p in n.split(" ")):
        return None, "Solo letras, espacios, guion, apóstrofo y punto después de una inicial (ej. J.)."
    return n, None


MAX_NOMBRES_PILA = 5          # un profesor puede tener de 1 a 5 nombres de pila
MAX_PALABRAS_APELLIDO = 3     # "García", "De la Cruz", "Pérez Gil"… (las partículas no cuentan)
MAX_LARGO_NOMBRES = 60
MAX_LARGO_APELLIDO = 28       # 60 + 28 + 28 + 2 espacios = 118 <= 120 (columna profesores.nombre)


def _parte_nombre(v, etiqueta, maximo, max_palabras, requerido, plural=False):
    """Valida y normaliza UNA parte del nombre. Devuelve (texto | None, mensaje | None).
    Si no es obligatoria y viene vacía devuelve (None, None)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return (None, f"{etiqueta} es obligatorio.") if requerido else (None, None)
    if not isinstance(v, str):
        return None, f"{etiqueta} no es válido."
    n = normalizar_nombre(v)
    if len(n) < 2:
        return None, "Mínimo 2 caracteres."
    if len(n) > maximo:
        return None, f"Máximo {maximo} caracteres."
    palabras = n.split(" ")
    if not all(RE_PALABRA_NOMBRE.fullmatch(p) for p in palabras):
        return None, "Solo letras (con acentos, diéresis y ñ), espacios y guiones; sin números ni otros símbolos."
    cuenta = sum(1 for p in palabras if p.lower() not in PARTICULAS)
    if cuenta == 0:
        return None, f"{etiqueta} no es válido."
    if cuenta > max_palabras:
        return None, (f"Máximo {max_palabras} nombres de pila." if plural else f"Máximo {max_palabras} palabras.")
    return n, None


def datos_profesor(body):
    """Valida los datos de un profesor: nombre(s) de pila (1 a 5), apellido paterno (obligatorio) y apellido materno
    (opcional). Devuelve ({nombres, apellido_paterno, apellido_materno, nombre}, None) o (None, {campo: mensaje}).
    `nombre` es el nombre completo ya armado, que es el que se muestra y se compara."""
    errores = {}
    nombres, e = _parte_nombre(body.get("nombres"), "El nombre", MAX_LARGO_NOMBRES, MAX_NOMBRES_PILA, True, plural=True)
    if e:
        errores["nombres"] = e
    paterno, e = _parte_nombre(body.get("apellido_paterno"), "El apellido paterno", MAX_LARGO_APELLIDO,
                               MAX_PALABRAS_APELLIDO, True)
    if e:
        errores["apellido_paterno"] = e
    materno, e = _parte_nombre(body.get("apellido_materno"), "El apellido materno", MAX_LARGO_APELLIDO,
                               MAX_PALABRAS_APELLIDO, False)
    if e:
        errores["apellido_materno"] = e
    if errores:
        return None, errores
    completo = " ".join(x for x in (nombres, paterno, materno) if x)
    return {"nombres": nombres, "apellido_paterno": paterno, "apellido_materno": materno, "nombre": completo}, None


def num_alumnos(v):
    """Entero positivo (1 a 500). Rechaza negativos, decimales (35.5), letras, booleanos y vacíos."""
    if isinstance(v, bool) or v is None:
        return None, "El número de alumnos es obligatorio."
    if isinstance(v, str):
        if not re.fullmatch(r"[0-9]{1,5}", v.strip()):
            return None, "Escribe un número entero positivo."
        v = int(v.strip())
    if not isinstance(v, int):
        return None, "Escribe un número entero positivo."
    if v < 1:
        return None, "Debe ser un entero positivo (mínimo 1)."
    if v > MAX_ALUMNOS:
        return None, f"Máximo {MAX_ALUMNOS} alumnos."
    return v, None


def clave_acceso(v):
    """Contraseña de acceso de un grupo: 4 a 40 caracteres visibles, sin espacios ni caracteres de control."""
    if not isinstance(v, str) or not v:
        return None, "La contraseña es obligatoria."
    if len(v) < 4:
        return None, "Mínimo 4 caracteres."
    if len(v) > 40:
        return None, "Máximo 40 caracteres."
    if any(c.isspace() or not c.isprintable() for c in v):
        return None, "No puede contener espacios ni caracteres de control."
    return v, None


def nombre_materia(v):
    """Misma validación y normalización que el nombre de un profesor (obligatorio, sin espacios sobrantes,
    Cada Palabra Con Inicial Mayúscula, 3 a 60 caracteres). Conserva los dígitos y la puntuación habituales
    en materias (Inglés 2, Cálculo (I), Matemáticas y Física)."""
    if not isinstance(v, str) or not v.strip():
        return None, "La materia es obligatoria."
    n = normalizar_nombre(v, materia=True)
    if len(n) < 3:
        return None, "Mínimo 3 caracteres."
    if len(n) > 60:
        return None, "Máximo 60 caracteres."
    if not all(c.isalnum() or c in PUNTUACION_MATERIA for c in n):
        return None, "Contiene caracteres no permitidos."
    if not any(c.isalpha() for c in n):
        return None, "Debe contener letras."
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


def _evaluacion(item):
    """Valida UNA evaluación (un profesor-materia) dentro de la encuesta. Devuelve (datos | None, {campo: mensaje})."""
    errores = {}
    if not isinstance(item, dict):
        return None, {"general": "Evaluación no válida."}
    profesor_id = id_entero(item.get("profesor_id"))
    materia_id = id_entero(item.get("materia_id"))
    if not profesor_id or not materia_id:
        return None, {"general": "Identificador de profesor o materia no válido."}

    respuestas = None
    r = item.get("respuestas")
    if not isinstance(r, list) or len(r) != TOTAL_PREGUNTAS:
        errores["respuestas"] = f"Se requieren las {TOTAL_PREGUNTAS} respuestas."
    else:
        malas = [i + 1 for i, v in enumerate(r)
                 if not (isinstance(v, int) and not isinstance(v, bool) and MIN_CALIF <= v <= MAX_CALIF)]
        if malas:
            errores["respuestas"] = (f"Calificación inválida (entero de {MIN_CALIF} a {MAX_CALIF}) "
                                     f"en la(s) pregunta(s): {', '.join(map(str, malas))}.")
        else:
            respuestas = r

    comentario = None
    c = item.get("comentario")
    if c is not None:
        if not isinstance(c, str):
            errores["comentario"] = "Comentario no válido."
        elif len(c) > MAX_COMENTARIO:
            errores["comentario"] = f"Máximo {MAX_COMENTARIO} caracteres."
        else:
            comentario = c.strip() or None
    if errores:
        return {"profesor_id": profesor_id, "materia_id": materia_id}, errores
    return {"profesor_id": profesor_id, "materia_id": materia_id, "respuestas": respuestas, "comentario": comentario}, None


def encuesta(body):
    """Valida el cuerpo de una ENCUESTA completa: {grupo_id, evaluaciones: [{profesor_id, materia_id, respuestas[12], comentario?}]}.
    Devuelve (datos, None) o (None, {campo: mensaje}). Los errores de una evaluación llevan la llave
    "r_<profesor_id>_<materia_id>" (calificaciones) o "c_<profesor_id>_<materia_id>" (comentario).
    La comprobación contra la base (existencia, asignación, límite) la hace rutas_publico dentro de la transacción."""
    if not isinstance(body, dict):
        return None, {"general": "Solicitud no válida."}
    errores = {}
    grupo_id = id_entero(body.get("grupo_id"))
    if not grupo_id:
        errores["grupo"] = "Selecciona un grupo."

    items = body.get("evaluaciones")
    evaluaciones = []
    if not isinstance(items, list) or not items:
        errores["evaluaciones"] = "La encuesta no contiene evaluaciones."
    elif len(items) > MAX_EVALUACIONES_POR_ENCUESTA:
        errores["evaluaciones"] = "La encuesta contiene demasiadas evaluaciones."
    else:
        vistos = set()
        for it in items:
            datos, e = _evaluacion(it)
            if e and "general" in e:
                errores["evaluaciones"] = e["general"]
                continue
            clave = (datos["profesor_id"], datos["materia_id"])
            if clave in vistos:
                errores["evaluaciones"] = "Hay un profesor-materia repetido en la encuesta."
                continue
            vistos.add(clave)
            if e:
                for campo, msg in e.items():
                    errores[f"{'r' if campo == 'respuestas' else 'c'}_{clave[0]}_{clave[1]}"] = msg
            else:
                evaluaciones.append(datos)
    if errores:
        return None, errores
    return {"grupo_id": grupo_id, "evaluaciones": evaluaciones}, None
