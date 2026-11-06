"""Configuración leída de variables de entorno (archivo .env). Nunca hay credenciales en el código."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
# No pisa variables que ya estén definidas en el entorno (útil para las pruebas)
load_dotenv(RAIZ / ".env")


class ConfigIncompleta(Exception):
    pass


def _entero(nombre, defecto):
    try:
        return int(os.environ.get(nombre, defecto))
    except ValueError:
        return defecto


def leer_config():
    env = os.environ
    return {
        "PORT": _entero("PORT", 3000),
        "HOST": env.get("HOST", "127.0.0.1"),
        "DB_HOST": env.get("DB_HOST", "127.0.0.1"),
        "DB_PORT": _entero("DB_PORT", 3306),
        "DB_USER": env.get("DB_USER", ""),
        "DB_PASSWORD": env.get("DB_PASSWORD", ""),
        "DB_NAME": env.get("DB_NAME", "evaluacion_docente"),
        "SESSION_SECRET": env.get("SESSION_SECRET", ""),
        "SESSION_MINUTOS": _entero("SESSION_MINUTOS", 120),
        # Clave(s) Fernet con las que se cifran las contraseñas de acceso de los grupos. Se separan por coma si hay
        # más de una (la primera cifra; todas descifran: sirve para rotar la clave sin perder las contraseñas).
        "CLAVE_CIFRADO_ACCESO": env.get("CLAVE_CIFRADO_ACCESO", ""),
        # Minutos que dura la autorización de un alumno después de escribir la contraseña del grupo
        "ACCESO_MINUTOS": _entero("ACCESO_MINUTOS", 60),
        # true solo si el sistema se publica detrás de HTTPS
        "COOKIE_SECURE": env.get("COOKIE_SECURE", "false").lower() == "true",
    }


def validar_config(cfg):
    faltan = []
    if not cfg["DB_USER"]:
        faltan.append("DB_USER")
    if len(cfg["SESSION_SECRET"]) < 32:
        faltan.append("SESSION_SECRET (mínimo 32 caracteres)")
    claves = [k.strip() for k in cfg["CLAVE_CIFRADO_ACCESO"].split(",") if k.strip()]
    if not claves:
        faltan.append("CLAVE_CIFRADO_ACCESO (genérala con: python generar_clave.py)")
    else:
        from cryptography.fernet import Fernet
        try:
            for k in claves:
                Fernet(k.encode())
        except (ValueError, TypeError):
            faltan.append("CLAVE_CIFRADO_ACCESO (no es una clave Fernet válida; genérala con: python generar_clave.py)")
    if faltan:
        raise ConfigIncompleta(
            "Configuración incompleta en el archivo .env: " + ", ".join(faltan)
            + ". Copia .env.example a .env y complétalo."
        )
