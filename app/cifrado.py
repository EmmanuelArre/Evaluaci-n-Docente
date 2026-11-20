"""Cifrado reversible de las contraseñas de acceso de los grupos (el administrador debe poder verlas).

· Algoritmo: Fernet (AES-128-CBC + HMAC-SHA256, con vector de inicialización aleatorio y marca de tiempo).
  Dos cifrados de la misma contraseña dan resultados distintos; si alguien altera el texto cifrado, el
  descifrado falla en lugar de devolver basura.
· La CLAVE no está en el código ni en la base de datos: se lee de la variable de entorno
  CLAVE_CIFRADO_ACCESO (archivo .env, que está en .gitignore). Quien lea solo la base de datos NO puede
  recuperar las contraseñas.
· Rotación: CLAVE_CIFRADO_ACCESO admite varias claves separadas por coma; la primera cifra y todas descifran.
· Este módulo nunca escribe contraseñas en logs ni en mensajes de error.
"""
import hmac

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from flask import current_app


def _fernet():
    claves = [k.strip() for k in current_app.config["EVAL"]["CLAVE_CIFRADO_ACCESO"].split(",") if k.strip()]
    return MultiFernet([Fernet(k.encode()) for k in claves])


def cifrar(texto):
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(token):
    """Devuelve la contraseña, o None si no hay token o no se pudo descifrar (clave equivocada / dato alterado)."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        current_app.logger.error("No se pudo descifrar una contraseña de acceso (¿cambió CLAVE_CIFRADO_ACCESO?).")
        return None


def coincide(token, candidata):
    """Compara en tiempo constante la contraseña guardada (cifrada) con la escrita. Solo devuelve un booleano."""
    real = descifrar(token)
    if real is None or not isinstance(candidata, str):
        return False
    return hmac.compare_digest(real.encode("utf-8"), candidata.encode("utf-8"))
