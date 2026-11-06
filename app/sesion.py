"""Sesiones del administrador guardadas en el SERVIDOR (tabla `sesiones` de MySQL).

La cookie solo contiene un identificador aleatorio e imposible de adivinar; en la base se guarda su
huella HMAC (si alguien leyera la tabla no obtendría cookies utilizables). Cerrar sesión borra la fila,
así que la cookie deja de servir de inmediato. La expiración es por inactividad (se renueva en cada uso).
"""
import hashlib
import hmac
import json
import secrets
import time

from flask import current_app, request

from . import db

COOKIE = "ed.sid"


def _huella(token):
    secreto = current_app.config["EVAL"]["SESSION_SECRET"].encode()
    return hmac.new(secreto, token.encode(), hashlib.sha256).hexdigest()


def _duracion():
    return current_app.config["EVAL"]["SESSION_MINUTOS"] * 60


def crear(admin):
    """Crea una sesión NUEVA (nunca reutiliza identificadores: evita la fijación de sesión)."""
    token = secrets.token_urlsafe(32)
    ahora = int(time.time())
    db.ejecutar("DELETE FROM sesiones WHERE expires < %s", (ahora,))  # limpieza de vencidas
    db.ejecutar("INSERT INTO sesiones (session_id, expires, data) VALUES (%s, %s, %s)",
                (_huella(token), ahora + _duracion(), json.dumps(admin)))
    return token


def cargar():
    """Devuelve los datos del administrador de la sesión actual, o None."""
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 100:
        return None
    huella = _huella(token)
    ahora = int(time.time())
    fila = db.una("SELECT data FROM sesiones WHERE session_id = %s AND expires >= %s", (huella, ahora))
    if not fila:
        return None
    try:
        datos = json.loads(fila["data"])
    except (TypeError, ValueError):
        return None
    # El administrador debe seguir existiendo y activo
    adm = db.una("SELECT activo FROM administradores WHERE id = %s", (datos.get("id"),))
    if not adm or not adm["activo"]:
        return None
    db.ejecutar("UPDATE sesiones SET expires = %s WHERE session_id = %s", (ahora + _duracion(), huella))
    return datos


def destruir():
    token = request.cookies.get(COOKIE)
    if token and len(token) <= 100:
        db.ejecutar("DELETE FROM sesiones WHERE session_id = %s", (_huella(token),))


# =====================================================================
# Autorización de ACCESO A UNA ENCUESTA (alumnos, sin identidad)
# =====================================================================
# Después de escribir la contraseña correcta del grupo, el servidor guarda en la tabla `sesiones` una fila con
# el grupo autorizado y la versión de su contraseña. El navegador solo recibe un identificador aleatorio en una
# cookie httpOnly: la contraseña NUNCA se guarda en el navegador (ni localStorage, ni sessionStorage, ni cookie).
# La cookie no identifica a ninguna persona: todos los alumnos del grupo reciben una igual en estructura.
#  · La autorización vence a los ACCESO_MINUTOS (no se renueva con el uso).
#  · Se "consume" al guardar una encuesta: para contestar otra hay que volver a escribir la contraseña.
#  · Si el administrador cambia la contraseña del grupo, su versión sube y las autorizaciones abiertas dejan de servir.
COOKIE_ACCESO = "ed.acc"


def _huella_acceso(token):
    secreto = current_app.config["EVAL"]["SESSION_SECRET"].encode()
    return hmac.new(secreto, b"acceso|" + token.encode(), hashlib.sha256).hexdigest()   # dominio distinto al del admin


def crear_acceso(grupo_id, version):
    token = secrets.token_urlsafe(32)
    ahora = int(time.time())
    vida = current_app.config["EVAL"]["ACCESO_MINUTOS"] * 60
    db.ejecutar("DELETE FROM sesiones WHERE expires < %s", (ahora,))
    db.ejecutar("INSERT INTO sesiones (session_id, expires, data) VALUES (%s, %s, %s)",
                (_huella_acceso(token), ahora + vida, json.dumps({"acceso": {"grupo": grupo_id, "version": version}})))
    return token, vida


def acceso_actual():
    """{'grupo': id, 'version': n} de la autorización vigente en esta petición, o None."""
    token = request.cookies.get(COOKIE_ACCESO)
    if not token or len(token) > 100:
        return None
    fila = db.una("SELECT data FROM sesiones WHERE session_id = %s AND expires >= %s",
                  (_huella_acceso(token), int(time.time())))
    if not fila:
        return None
    try:
        return json.loads(fila["data"]).get("acceso")
    except (TypeError, ValueError, AttributeError):
        return None


def cerrar_acceso():
    token = request.cookies.get(COOKIE_ACCESO)
    if token and len(token) <= 100:
        db.ejecutar("DELETE FROM sesiones WHERE session_id = %s", (_huella_acceso(token),))
