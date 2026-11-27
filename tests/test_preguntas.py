"""CRUD de preguntas (/api/admin/preguntas) contra MySQL REAL. Ejecutar:  pytest tests/test_preguntas.py
Necesita haber corrido database/migracion_preguntas.sql (o un esquema nuevo) y una base cuyo nombre termine en _test.
Al terminar deja la tabla `preguntas` como la encontró."""
import bcrypt
import pytest

from app import cifrado, crear_app
from app import config as cfgmod
from app import db as dbmod
from ayuda import cliente, cuestionario, entrar, navegador_autorizado

PASS = "ClaveDePrueba123"
est, ids = {}, {}


@pytest.fixture(scope="module")
def sql():
    conn = dbmod.conectar(cfgmod.leer_config())
    yield conn
    conn.close()


def q(conn, s, p=()):
    with conn.cursor() as cur:
        cur.execute(s, p)
        return cur.fetchall()


@pytest.fixture(scope="module", autouse=True)
def preparar(sql):
    originales = q(sql, "SELECT num_pregunta, texto FROM preguntas ORDER BY num_pregunta")
    q(sql, "SET FOREIGN_KEY_CHECKS = 0")
    for t in ["respuestas", "evaluaciones", "encuestas", "asignaciones", "profesor_materia", "profesores", "materias", "grupos",
              "administradores", "sesiones"]:
        q(sql, f"DELETE FROM {t}")
    q(sql, "SET FOREIGN_KEY_CHECKS = 1")
    q(sql, "INSERT INTO administradores (usuario, nombre, password_hash) VALUES (%s, %s, %s)",
      ("admin", "Admin Pruebas", bcrypt.hashpw(PASS.encode(), bcrypt.gensalt(rounds=6)).decode()))
    est["app"] = crear_app()
    est["admin"] = cliente(est["app"])
    assert est["admin"]("POST", "/api/admin/login", {"usuario": "admin", "password": PASS}).status == 200
    yield
    q(sql, "SET FOREIGN_KEY_CHECKS = 0")
    for t in ["respuestas", "evaluaciones", "encuestas", "asignaciones", "profesor_materia", "profesores", "materias", "grupos", "preguntas"]:
        q(sql, f"DELETE FROM {t}")
    q(sql, "SET FOREIGN_KEY_CHECKS = 1")
    for f in originales:
        q(sql, "INSERT INTO preguntas (num_pregunta, texto) VALUES (%s, %s)", (f["num_pregunta"], f["texto"]))


def A():
    return est["admin"]


def test_01_sin_sesion_da_401():
    c = cliente(est["app"])
    for metodo, ruta in (("GET", "/api/admin/preguntas"), ("POST", "/api/admin/preguntas"),
                         ("PUT", "/api/admin/preguntas/1"), ("DELETE", "/api/admin/preguntas/1")):
        assert c(metodo, ruta, {"texto": "x" * 20} if metodo != "GET" else None).status == 401


def test_02_lista_en_orden_con_conteo_de_respuestas():
    r = A()("GET", "/api/admin/preguntas")
    assert r.status == 200
    d = r.datos
    assert d["total"] == len(d["preguntas"]) >= 1
    assert [p["orden"] for p in d["preguntas"]] == list(range(1, d["total"] + 1))
    assert all(p["respuestas"] == 0 for p in d["preguntas"])
    est["total0"] = d["total"]


def test_03_busqueda_por_texto_y_comodines_literales():
    r = A()("GET", "/api/admin/preguntas?q=a%20tiempo")
    assert r.status == 200 and any("tiempo" in p["texto"] for p in r.datos["preguntas"])
    assert all(p["orden"] is not None for p in r.datos["preguntas"])
    assert A()("GET", "/api/admin/preguntas?q=%25").datos["preguntas"] == []          # «%» se busca como carácter, no como comodín
    assert A()("GET", "/api/admin/preguntas?q=" + "x" * 300).status == 400


def test_04_agregar_va_al_final_y_valida():
    r = A()("POST", "/api/admin/preguntas", {"texto": "  El profesor    comparte el material a tiempo.  "})
    assert r.status == 201
    est["nueva"] = r.datos["num"]
    lista = A()("GET", "/api/admin/preguntas").datos["preguntas"]
    assert lista[-1]["num"] == est["nueva"] and lista[-1]["texto"] == "El profesor comparte el material a tiempo."
    assert len(lista) == est["total0"] + 1
    assert A()("POST", "/api/admin/preguntas", {"texto": "el PROFESOR comparte el material a tiempo."}).status == 409   # repetida
    for malo in ("", "corta", None, 123, "x" * 256, "con\x00control texto largo"):
        assert A()("POST", "/api/admin/preguntas", {"texto": malo}).status == 400, malo


def test_05_editar():
    n = est["nueva"]
    assert A()("PUT", f"/api/admin/preguntas/{n}", {"texto": "El profesor comparte el material con anticipación."}).status == 200
    textos = {p["num"]: p["texto"] for p in A()("GET", "/api/admin/preguntas").datos["preguntas"]}
    assert textos[n] == "El profesor comparte el material con anticipación."
    otra = next(k for k in textos if k != n)
    assert A()("PUT", f"/api/admin/preguntas/{n}", {"texto": textos[otra]}).status == 409
    assert A()("PUT", "/api/admin/preguntas/250", {"texto": "Texto válido de prueba."}).status == 404
    for malo in ("abc", "0", "-1", "999"):
        assert A()("PUT", f"/api/admin/preguntas/{malo}", {"texto": "Texto válido de prueba."}).status == 400


def test_06_eliminar_sin_respuestas():
    n = est["nueva"]
    r = A()("DELETE", f"/api/admin/preguntas/{n}")
    assert r.status == 200 and r.datos["respuestas_borradas"] == 0
    assert A()("DELETE", f"/api/admin/preguntas/{n}").status == 404
    assert A()("GET", "/api/admin/preguntas").datos["total"] == est["total0"]


def _preparar_encuesta():
    a = A()
    ids["mat"] = a("POST", "/api/admin/materias", {"nombre": "Bases de Datos"}).datos["id"]
    ids["prof"] = a("POST", "/api/admin/profesores", {"nombres": "Ana", "apellido_paterno": "Prueba"}).datos["id"]
    assert a("POST", f"/api/admin/profesores/{ids['prof']}/materias", {"materia_id": ids["mat"]}).status in (200, 201)
    r = a("POST", "/api/admin/grupos", {"clave": "GTID244", "num_alumnos": 35, "clave_acceso": "Clave-pruebas-1"})
    ids["grupo"] = r.datos["id"]
    assert a("POST", f"/api/admin/grupos/{ids['grupo']}/asignaciones", {"profesor_id": ids["prof"], "materia_id": ids["mat"]}).status == 201


def _contestar(calificaciones):
    est["app"].extensions["limite_acceso_ip"].reiniciar(); est["app"].extensions["limite_acceso_grupo"].reiniciar()
    c = navegador_autorizado(est["app"], ids["grupo"], "Clave-pruebas-1")
    d = cuestionario(c, ids["grupo"]).datos
    cuerpo = {"grupo_id": ids["grupo"], "evaluaciones": [
        {"profesor_id": a["profesor_id"], "materia_id": a["materia_id"], "respuestas": calificaciones} for a in d["asignaciones"]]}
    return c("POST", "/api/encuestas", cuerpo), len(d["preguntas"])


def test_07_eliminar_con_respuestas_borra_todo_y_la_encuesta_se_adapta(sql):
    _preparar_encuesta()
    total = est["total0"]
    r, n_preg = _contestar([8] * total)
    assert r.status == 201 and n_preg == total
    victima = A()("GET", "/api/admin/preguntas").datos["preguntas"][2]          # la tercera
    assert victima["respuestas"] == 1
    r = A()("DELETE", f"/api/admin/preguntas/{victima['num']}")
    assert r.status == 200 and r.datos["respuestas_borradas"] == 1
    assert q(sql, "SELECT COUNT(*) AS n FROM respuestas WHERE num_pregunta = %s", (victima["num"],))[0]["n"] == 0
    assert q(sql, "SELECT COUNT(*) AS n FROM respuestas")[0]["n"] == total - 1
    # Con 12 respuestas ya no se acepta; con las vigentes sí
    est["app"].extensions["limite_envios"].reiniciar()
    r, n_preg = _contestar([9] * total)
    assert r.status == 400 and n_preg == total - 1
    r, _ = _contestar([9] * (total - 1))
    assert r.status == 201


def test_08_reporte_usa_las_preguntas_vigentes():
    r = A()("GET", f"/api/admin/reportes/grupo?grupo={ids['grupo']}")
    assert r.status == 200
    d = r.datos
    assert d["totalPreguntas"] == est["total0"] - 1 == len(d["preguntas"]) == len(d["porPregunta"])
    assert all(len(x["respuestas"]) == d["totalPreguntas"] for x in d["detalle"])


def test_09_pregunta_nueva_no_altera_respuestas_viejas(sql):
    r = A()("POST", "/api/admin/preguntas", {"texto": "Pregunta agregada después de contestar."})
    assert r.status == 201
    d = A()("GET", f"/api/admin/reportes/grupo?grupo={ids['grupo']}").datos
    assert d["totalPreguntas"] == est["total0"] and d["porPregunta"][-1] is None       # nadie la ha contestado todavía
    assert all(x["respuestas"][-1] is None for x in d["detalle"])


def test_10_siempre_debe_quedar_una_pregunta():
    while True:
        lista = A()("GET", "/api/admin/preguntas").datos["preguntas"]
        if len(lista) == 1:
            break
        assert A()("DELETE", f"/api/admin/preguntas/{lista[0]['num']}").status == 200
    assert A()("DELETE", f"/api/admin/preguntas/{lista[0]['num']}").status == 409
