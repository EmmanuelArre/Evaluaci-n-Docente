"""Errores HTTP controlados y traducción de errores de MySQL."""
import pymysql

from . import db


class ErrorHttp(Exception):
    def __init__(self, status, mensaje, errores=None):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje
        self.errores = errores


def traducir_mysql(e, duplicado=None, referencia=None):
    """Convierte errores conocidos de MySQL en ErrorHttp; si no los conoce devuelve la misma excepción."""
    if isinstance(e, pymysql.err.MySQLError) and e.args:
        codigo = e.args[0]
        if codigo == db.ER_DUP_ENTRY:
            return ErrorHttp(409, duplicado or "El registro ya existe.")
        if codigo in db.ER_ROW_IS_REFERENCED:
            return ErrorHttp(409, referencia or "No se puede eliminar: existen registros que dependen de este.")
    return e


def es_fk_inexistente(e):
    return isinstance(e, pymysql.err.MySQLError) and e.args and e.args[0] in db.ER_NO_REFERENCED_ROW
