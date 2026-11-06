"""Fábrica de la aplicación Flask de Evaluación Docente."""
from datetime import date, datetime
from decimal import Decimal

from flask import Flask, g, jsonify, redirect, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from urllib.parse import urlparse

from . import config as cfgmod
from . import db, sesion
from .errores import ErrorHttp
from .limitador import Limitador

RAIZ = cfgmod.RAIZ

CSP = ("default-src 'self'; base-uri 'self'; font-src 'self' data:; form-action 'self'; frame-ancestors 'none'; "
       "img-src 'self' data:; object-src 'none'; script-src 'self'; "
       "style-src 'self' 'unsafe-inline'")   # 'unsafe-inline' solo para estilos: la gráfica asigna height=""


class ProveedorJSON(DefaultJSONProvider):
    ensure_ascii = False
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return DefaultJSONProvider.default(o)


def crear_app(cfg=None):
    app = Flask(__name__, static_folder=None)
    app.json = ProveedorJSON(app)
    cfg = cfg or cfgmod.leer_config()
    cfgmod.validar_config(cfg)
    app.config["EVAL"] = cfg
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024          # cuerpos JSON de máximo 20 KB
    if cfg["COOKIE_SECURE"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.extensions["limite_login"] = Limitador(15 * 60, 10)       # 10 intentos fallidos / 15 min / IP
    app.extensions["limite_envios"] = Limitador(10 * 60, 300)     # 300 envíos / 10 min / IP
    # Contraseña de grupo: intentos FALLIDOS. Por IP+grupo (frena a quien adivina) y por grupo (frena ataques repartidos
    # entre varias IP). Un salón comparte IP, de ahí que los topes sean holgados para alumnos que se equivocan al teclear.
    app.extensions["limite_acceso_ip"] = Limitador(10 * 60, 8)
    app.extensions["limite_acceso_grupo"] = Limitador(15 * 60, 60)
    app.teardown_appcontext(db.cerrar)

    # ---------- Control de acceso y defensas (un único punto para TODO /api/admin) ----------
    @app.before_request
    def proteger():
        ruta = request.path
        if ruta.startswith("/api") and request.method not in ("GET", "HEAD", "OPTIONS"):
            origen = request.headers.get("Origin")
            if origen and urlparse(origen).netloc != request.host:   # CSRF: otro sitio no puede escribir
                raise ErrorHttp(403, "Origen no permitido.")
            if (request.content_length or 0) > 0 and not request.is_json:
                raise ErrorHttp(415, "Se esperaba application/json.")
        if ruta.startswith("/api/admin") and ruta not in ("/api/admin/login", "/api/admin/logout"):
            admin = sesion.cargar()
            if not admin:
                raise ErrorHttp(401, "Sesión no iniciada o expirada. Inicia sesión como administrador.")
            g.admin = admin

    @app.after_request
    def cabeceras(resp):
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if request.path.startswith("/api/admin"):
            resp.headers["Cache-Control"] = "no-store"        # los reportes no se guardan en caché
        return resp

    # ---------- API ----------
    from . import rutas_admin, rutas_auth, rutas_publico, rutas_reportes
    for modulo in (rutas_publico, rutas_auth, rutas_admin, rutas_reportes):
        app.register_blueprint(modulo.bp)

    @app.get("/api/salud")
    def salud():
        db.una("SELECT 1")
        return jsonify({"ok": True, "baseDeDatos": "conectada"})

    # ---------- Páginas y archivos estáticos (lista explícita: .env, app/, database/ y docs/ nunca se sirven) ----------
    @app.get("/")
    @app.get("/index.html")
    def inicio():
        return send_from_directory(RAIZ, "index.html")

    @app.get("/admin.html")
    def admin_html():
        return send_from_directory(RAIZ, "admin.html")

    @app.get("/reporte.html")
    def reporte_html():
        # Solo con sesión; sin ella se redirige al inicio de sesión. (La protección real está en la API.)
        if not sesion.cargar():
            return redirect("/admin.html")
        return send_from_directory(RAIZ, "reporte.html")

    @app.get("/<any(css,js,img):carpeta>/<path:archivo>")
    def estaticos(carpeta, archivo):
        return send_from_directory(RAIZ / carpeta, archivo)   # send_from_directory impide salir de la carpeta

    # ---------- Errores ----------
    @app.errorhandler(ErrorHttp)
    def error_controlado(e):
        return jsonify({"error": e.mensaje, "errores": e.errores}), e.status

    @app.errorhandler(HTTPException)
    def error_http(e):
        if request.path.startswith("/api"):
            mensajes = {400: "Solicitud no válida.", 404: "Recurso no encontrado.", 405: "Método no permitido.",
                        413: "Solicitud demasiado grande."}
            return jsonify({"error": mensajes.get(e.code, e.name)}), e.code
        return e

    @app.errorhandler(Exception)
    def error_interno(e):
        app.logger.exception("Error interno")
        return jsonify({"error": "Error interno del servidor. Inténtalo de nuevo."}), 500

    return app
