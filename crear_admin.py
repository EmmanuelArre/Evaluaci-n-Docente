"""Crea (o restablece la contraseña de) un administrador de forma segura.

 - La contraseña se escribe en la terminal SIN mostrarse y nunca queda en archivos ni en el historial.
 - Solo se guarda su hash bcrypt (coste 12).
Uso:  python crear_admin.py
"""
import getpass
import os
import sys

import bcrypt

from app import config as cfgmod
from app import db as dbmod
from app import validar


def validar_password(p):
    if len(p) < 10:
        return "La contraseña debe tener al menos 10 caracteres."
    if len(p.encode()) > 72:
        return "La contraseña no puede pasar de 72 bytes (unos 72 caracteres)."
    if not (any(c.islower() for c in p) and any(c.isupper() for c in p) and any(c.isdigit() for c in p)):
        return "Debe incluir mayúsculas, minúsculas y números."
    return ""


def main():
    cfg = cfgmod.leer_config()
    try:
        cfgmod.validar_config(cfg)
    except cfgmod.ConfigIncompleta as e:
        print(f"\n✖ {e}\n")
        return 1
    print("\n=== Crear / restablecer administrador ===\n")
    try:
        # En automatización (pruebas) se pueden usar ADMIN_USUARIO / ADMIN_NOMBRE / ADMIN_PASSWORD;
        # en uso normal el script los pide de forma interactiva.
        usuario = os.environ.get("ADMIN_USUARIO") or input("Usuario (3-30 letras/números): ")
        usuario, err = validar.usuario(usuario)
        if err:
            raise ValueError("Usuario no válido (3 a 30 caracteres: letras, números, _ . -).")
        nombre, err = validar.nombre_persona(os.environ.get("ADMIN_NOMBRE") or input("Nombre completo: "),
                                             "El nombre", minimo=3)
        if err:
            raise ValueError(err)
        password = os.environ.get("ADMIN_PASSWORD")
        if not password:
            password = getpass.getpass("Contraseña (no se mostrará): ")
            if password != getpass.getpass("Repite la contraseña: "):
                raise ValueError("Las contraseñas no coinciden.")
        err = validar_password(password)
        if err:
            raise ValueError(err)

        hash_ = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        conn = dbmod.conectar(cfg)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM administradores WHERE usuario = %s", (usuario,))
                existe = cur.fetchone()
                if existe:
                    cur.execute("UPDATE administradores SET password_hash = %s, nombre = %s, activo = 1 WHERE id = %s",
                                (hash_, nombre, existe["id"]))
                    print(f'\n✔ Se restableció la contraseña del administrador "{usuario}".')
                else:
                    cur.execute("INSERT INTO administradores (usuario, nombre, password_hash) VALUES (%s, %s, %s)",
                                (usuario, nombre, hash_))
                    print(f'\n✔ Administrador "{usuario}" creado.')
        finally:
            conn.close()
        print(f"  Inicia sesión en http://localhost:{cfg['PORT']}/admin.html\n")
        return 0
    except ValueError as e:
        print(f"\n✖ {e}\n")
    except Exception as e:  # noqa: BLE001
        if getattr(e, "args", None) and e.args[0] == 1146:
            print("\n✖ Faltan las tablas: ejecuta primero database/schema.sql en MySQL Workbench.\n")
        else:
            print(f"\n✖ {e}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
