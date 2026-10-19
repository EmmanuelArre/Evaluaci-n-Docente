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
