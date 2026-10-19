"""Inicia el sistema:  python run.py   →  http://localhost:3000"""
import sys

from app import crear_app
from app import config as cfgmod
from app import db as dbmod


def main():
    cfg = cfgmod.leer_config()
    try:
        cfgmod.validar_config(cfg)
    except cfgmod.ConfigIncompleta as e:
        print(f"\n✖ {e}\n")
        sys.exit(1)
    try:
        dbmod.conectar(cfg).close()
    except Exception as e:  # noqa: BLE001
        codigo = e.args[0] if getattr(e, "args", None) else e
        print(f"\n✖ No se pudo conectar a MySQL ({codigo}).")
        print("  Revisa que el servidor MySQL esté activo y que DB_HOST, DB_PORT, DB_USER, DB_PASSWORD y DB_NAME del .env sean correctos.\n")
        sys.exit(1)

    app = crear_app(cfg)
    print(f"✔ Evaluación docente en http://localhost:{cfg['PORT']}")
    print(f"  Base de datos: {cfg['DB_NAME']} @ {cfg['DB_HOST']}:{cfg['DB_PORT']}   (Ctrl+C para detener)")
    from waitress import serve
    serve(app, host=cfg["HOST"], port=cfg["PORT"], threads=8)


if __name__ == "__main__":
    main()
