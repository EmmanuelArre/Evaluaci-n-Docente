"""Autenticación del administrador: contraseñas con bcrypt, sesión en servidor, cookie httpOnly."""
import bcrypt
from flask import Blueprint, current_app, g, jsonify, request

from . import db, sesion
from .errores import ErrorHttp

bp = Blueprint("auth", __name__, url_prefix="/api/admin")

# Hash falso para igualar tiempos de respuesta cuando el usuario no existe
_HASH_FALSO = bcrypt.hashpw(b"no-existe-nunca", bcrypt.gensalt(rounds=12))


def _cookie_sesion(resp, token):
    resp.set_cookie(sesion.COOKIE, token, httponly=True, samesite="Strict",
                    secure=current_app.config["EVAL"]["COOKIE_SECURE"], path="/")
    return resp


@bp.post("/login")
def login():
    lim = current_app.extensions["limite_login"]
    if lim.excedido(request.remote_addr):
        raise ErrorHttp(429, "Demasiados intentos fallidos. Espera 15 minutos e inténtalo de nuevo.")

    cuerpo = request.get_json(silent=True) or {}
    usuario, password = cuerpo.get("usuario"), cuerpo.get("password")
    if (not isinstance(usuario, str) or not isinstance(password, str)
            or not usuario or not password or len(password) > 200):
        raise ErrorHttp(400, "Escribe usuario y contraseña.")

    admin = db.una("SELECT id, usuario, nombre, password_hash, activo FROM administradores WHERE usuario = %s",
                   (usuario.strip(),))
    hash_bd = admin["password_hash"].encode() if admin else _HASH_FALSO
    clave = password.encode()
    try:
        coincide = len(clave) <= 72 and bcrypt.checkpw(clave, hash_bd)   # bcrypt solo admite 72 bytes
    except ValueError:
        coincide = False
    if not admin or not admin["activo"] or not coincide:
        lim.registrar(request.remote_addr)
        raise ErrorHttp(401, "Usuario o contraseña incorrectos.")

    datos = {"id": admin["id"], "usuario": admin["usuario"], "nombre": admin["nombre"]}
    token = sesion.crear(datos)   # identificador nuevo en cada inicio de sesión
    db.ejecutar("UPDATE administradores SET ultimo_acceso = NOW() WHERE id = %s", (admin["id"],))
    return _cookie_sesion(jsonify({"ok": True, "usuario": admin["usuario"], "nombre": admin["nombre"]}), token)


@bp.post("/logout")
def logout():
    sesion.destruir()
    resp = jsonify({"ok": True})
    resp.delete_cookie(sesion.COOKIE, path="/")
    return resp


@bp.get("/me")
def me():
    # El control de acceso (401) lo aplica app.before_request para TODO /api/admin/*
    return jsonify({"usuario": g.admin["usuario"], "nombre": g.admin["nombre"]})
