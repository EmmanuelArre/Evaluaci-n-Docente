"""Preparación de las pruebas. Seguridad: se niegan a correr si DB_NAME no termina en "_test",
porque BORRAN el contenido de las tablas."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "evaluacion_docente_test")
os.environ.setdefault("SESSION_SECRET", "pruebas_pruebas_pruebas_pruebas_pruebas_123456")

if not os.environ["DB_NAME"].endswith("_test"):
    raise SystemExit("Las pruebas solo corren en una base cuyo nombre termina en _test")
