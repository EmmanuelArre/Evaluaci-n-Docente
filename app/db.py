"""Acceso a MySQL con PyMySQL. Solo el backend se conecta a la base; el navegador nunca."""
import pymysql
import pymysql.cursors
from flask import current_app, g


def conectar(cfg):
    return pymysql.connect(
        host=cfg["DB_HOST"], port=cfg["DB_PORT"], user=cfg["DB_USER"], password=cfg["DB_PASSWORD"],
        database=cfg["DB_NAME"], charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=True, connect_timeout=10,
    )


def conexion():
    """Una conexión por petición (se cierra al terminar)."""
    if "db" not in g:
        g.db = conectar(current_app.config["EVAL"])
    return g.db


def cerrar(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def filas(sql, params=None):
    with conexion().cursor() as cur:
        cur.execute(sql, params or ())
        return list(cur.fetchall())


def una(sql, params=None):
    with conexion().cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def ejecutar(sql, params=None):
    """Devuelve (filas_afectadas, ultimo_id)."""
    with conexion().cursor() as cur:
        n = cur.execute(sql, params or ())
        return n, cur.lastrowid


def marcadores(lista):
    """'%s,%s,%s' para cláusulas IN (...) parametrizadas."""
    return ",".join(["%s"] * len(lista))


# Códigos de error de MySQL que se traducen a mensajes amigables
ER_DUP_ENTRY = 1062
ER_ROW_IS_REFERENCED = (1217, 1451)
ER_NO_REFERENCED_ROW = (1216, 1452)
