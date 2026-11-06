"""Pruebas de integración contra una base MySQL REAL (sin simulaciones).

Preparación: ver PRUEBAS.md (sección "Cómo ejecutar las pruebas automáticas").   Ejecutar:  pytest
"""
import bcrypt
import pymysql
import pytest

from app import config as cfgmod
from app import crear_app
from app import db as dbmod
from ayuda import cuerpo_encuesta, cuestionario, entrar, navegador_autorizado

PASS = "ClaveDePrueba123"
ids = {}          # identificadores creados durante la corrida (las pruebas van en orden)
estado = {}


class Resp:
    def __init__(self, r):
        self.status = r.status_code
        self.datos = r.get_json(silent=True)
        self.headers = r.headers
        self.set_cookie = r.headers.getlist("Set-Cookie")


def cliente(app):
    c = app.test_client()

    def llamar(metodo, ruta, cuerpo=None, headers=None):
        kw = {"method": metodo, "headers": headers or {}}
        if cuerpo is not None:
            kw["json"] = cuerpo
        return Resp(c.open(ruta, **kw))
    return llamar


def R(n):
    return [n] * 12


@pytest.fixture(scope="module")
def sql():
    conn = dbmod.conectar(cfgmod.leer_config())
    yield conn
    conn.close()


def ejecutar(conn, q, p=()):
    with conn.cursor() as cur:
        cur.execute(q, p)
        return cur.fetchall()


def contar(conn, tabla):
    return ejecutar(conn, f"SELECT COUNT(*) AS n FROM {tabla}")[0]["n"]


@pytest.fixture(scope="module", autouse=True)
def preparar(sql):
    ejecutar(sql, "SET FOREIGN_KEY_CHECKS = 0")
    for t in ["respuestas", "evaluaciones", "encuestas", "asignaciones", "profesor_materia", "profesores", "materias", "grupos", "administradores", "sesiones"]:
        ejecutar(sql, f"DELETE FROM {t}")
    ejecutar(sql, "SET FOREIGN_KEY_CHECKS = 1")
    ejecutar(sql, "INSERT INTO administradores (usuario, nombre, password_hash) VALUES (%s, %s, %s)",
             ("admin", "Admin Pruebas", bcrypt.hashpw(PASS.encode(), bcrypt.gensalt(rounds=6)).decode()))
    estado["app"] = crear_app()


def anonimo():
    return cliente(estado["app"])


def admin():
    return estado["admin"]


def test_01_api_responde_y_conecta_con_mysql():
    r = anonimo()("GET", "/api/salud")
    assert r.status == 200 and r.datos["baseDeDatos"] == "conectada"


def test_02_sin_sesion_todos_los_endpoints_admin_dan_401():
    c = anonimo()
    rutas = [
        ("GET", "/api/admin/grupos", None), ("POST", "/api/admin/grupos", {"clave": "ABC1234"}), ("PUT", "/api/admin/grupos/1", {}), ("PUT", "/api/admin/grupos/1/acceso", {"clave_acceso": "abcd1234"}),
        ("DELETE", "/api/admin/grupos/1", None), ("GET", "/api/admin/profesores", None),
        ("POST", "/api/admin/profesores", {"nombres": "Persona", "apellido_paterno": "Prueba"}), ("DELETE", "/api/admin/profesores/1", None),
        ("GET", "/api/admin/profesores/1/materias", None), ("POST", "/api/admin/profesores/1/materias", {"materia_id": 1}),
        ("GET", "/api/admin/materias", None), ("POST", "/api/admin/materias", {"nombre": "Algo"}),
        ("DELETE", "/api/admin/materias/1", None), ("DELETE", "/api/admin/evaluaciones/1", None), ("GET", "/api/admin/me", None),
        ("GET", "/api/admin/reportes/grupo?grupo=1", None), ("GET", "/api/admin/reportes/profesor?profesor=1", None),
        ("GET", "/api/admin/reportes/grupo-profesor?grupo=1&profesor=1", None), ("GET", "/api/admin/reportes/general-grupo?grupo=1", None),
        ("GET", "/api/admin/grupos/1/asignaciones", None), ("POST", "/api/admin/grupos/1/asignaciones", {"profesor_id": 1, "materia_id": 1}),
        ("PUT", "/api/admin/grupos/1/asignaciones/1/1", {"activo": False}), ("DELETE", "/api/admin/grupos/1/asignaciones/1/1", None),
        ("GET", "/api/admin/ruta-inventada", None),
    ]
    for m, u, b in rutas:
        r = c(m, u, b)
        assert r.status == 401, f"{m} {u} debería ser 401 y fue {r.status}"


def test_03_reporte_html_redirige_sin_sesion():
    r = anonimo()("GET", "/reporte.html")
    assert r.status == 302 and r.headers["Location"].endswith("/admin.html")


def test_04_no_se_exponen_archivos_sensibles():
    for u in ["/.env", "/.env.example", "/app/config.py", "/run.py", "/requirements.txt", "/database/schema.sql",
              "/docs/1-requerimientos.docx", "/crear_admin.py", "/css/../.env", "/js/..%2f.env", "/js/../app/config.py",
              "/tests/test_api.py", "/.venv/pyvenv.cfg"]:
        r = anonimo()("GET", u)
        assert r.status in (404, 400), f"{u} no debe servirse (status {r.status})"
    assert anonimo()("GET", "/js/config.js").status == 200


def test_05_login_incorrecto_da_401_generico():
    c = anonimo()
    a = c("POST", "/api/admin/login", {"usuario": "admin", "password": "incorrecta"})
    b = c("POST", "/api/admin/login", {"usuario": "noexiste", "password": "incorrecta"})
    assert a.status == 401 and b.status == 401
    assert a.datos["error"] == b.datos["error"]       # no revela si el usuario existe
    assert c("POST", "/api/admin/login", {"usuario": 123, "password": {}}).status == 400
    assert c("POST", "/api/admin/login", {"usuario": "admin", "password": "ñ" * 80}).status == 401   # >72 bytes: sin error 500


def test_06_login_correcto_cookie_hash_y_sesion_en_mysql(sql):
    estado["admin"] = cliente(estado["app"])
    r = admin()("POST", "/api/admin/login", {"usuario": "admin", "password": PASS})
    assert r.status == 200
    ck = ";".join(r.set_cookie)
    assert "ed.sid=" in ck and "HttpOnly" in ck and "SameSite=Strict" in ck
    h = ejecutar(sql, "SELECT password_hash FROM administradores WHERE usuario='admin'")[0]["password_hash"]
    assert h.startswith("$2") and PASS not in h
    assert contar(sql, "sesiones") >= 1
    token = ck.split("ed.sid=")[1].split(";")[0]
    filas = ejecutar(sql, "SELECT session_id FROM sesiones")
    assert all(token not in f["session_id"] for f in filas)         # en la BD solo hay huellas, no la cookie
    assert admin()("GET", "/api/admin/me").status == 200


def test_07_peticion_de_otro_origen_se_rechaza():
    r = admin()("POST", "/api/admin/grupos", {"clave": "EVI0001"}, {"Origin": "http://sitio-malo.example"})
    assert r.status == 403


CLAVES = {"g1": "Clave-244", "g2": "Clave-233", "gVacio": "Clave-vac1"}


def nuevo_alumno(g):
    """Navegador nuevo que escribió la contraseña del grupo `g` (ids[g]) → listo para pedir el cuestionario y enviar."""
    return navegador_autorizado(estado["app"], ids[g], CLAVES[g])


def enviar_ok(g="g1", calif=8, comentario=None):
    c = nuevo_alumno(g)
    r = c("POST", "/api/encuestas", cuerpo_encuesta(c, ids[g], calif, comentario))
    assert r.status == 201, (r.status, r.datos)
    return r


def test_08_grupos_crear_validar_duplicar_editar():
    for clave in ["ab1234", "ABC1234", "AB12345", "GTID24", "GTID2445", "", "ABC 123", "AB1-234", "ABC12\n34"]:
        assert admin()("POST", "/api/admin/grupos", {"clave": clave, "num_alumnos": 30}).status == 400, f'clave "{clave!r}"'
    assert admin()("POST", "/api/admin/grupos", {}).status == 400
    for alumnos in [None, 0, -5, 3.5, "abc", "", True, 501, [30]]:
        r = admin()("POST", "/api/admin/grupos", {"clave": "ALUM001", "num_alumnos": alumnos})
        assert r.status == 400 and "num_alumnos" in r.datos["errores"], f"alumnos {alumnos!r}"
    r = admin()("POST", "/api/admin/grupos", {"clave": "gtid244", "descripcion": "Sistemas 5to", "num_alumnos": 50, "clave_acceso": CLAVES["g1"]})
    assert r.status == 201
    ids["g1"] = r.datos["id"]
    assert admin()("POST", "/api/admin/grupos", {"clave": "GTID244", "num_alumnos": 30}).status == 409
    ids["g2"] = admin()("POST", "/api/admin/grupos", {"clave": "GTID232", "num_alumnos": 30, "clave_acceso": CLAVES["g2"]}).datos["id"]
    ids["gVacio"] = admin()("POST", "/api/admin/grupos", {"clave": "VACI001", "num_alumnos": 5, "clave_acceso": CLAVES["gVacio"]}).datos["id"]
    ids["gSin"] = admin()("POST", "/api/admin/grupos", {"clave": "SINC001", "num_alumnos": 5}).datos["id"]   # sin contraseña
    lista = admin()("GET", "/api/admin/grupos").datos
    assert next(g for g in lista if g["id"] == ids["g1"])["clave"] == "GTID244"      # se normaliza a mayúsculas
    assert admin()("PUT", f"/api/admin/grupos/{ids['g2']}", {"clave": "GTID233", "descripcion": "Editado", "activo": True}).status == 200
    assert admin()("PUT", "/api/admin/grupos/999999", {"clave": "ZZZZ000"}).status == 404
    # editar sin mandar num_alumnos ni contraseña NO los cambia
    g2 = next(g for g in admin()("GET", "/api/admin/grupos").datos if g["id"] == ids["g2"])
    assert g2["num_alumnos"] == 30 and g2["clave_acceso"] == CLAVES["g2"]


def test_09_profesores_y_materias_validaciones_y_asignacion():
    P = lambda n, a, m=None, **o: {"nombres": n, "apellido_paterno": a, "apellido_materno": m, **o}
    malos = [P("Ana", ""), P("", "Pérez"), P(None, "Pérez"), P("Juan123", "Pérez"), P("Ana", "<script>alert(1)</script>"),
             P("x" * 61, "Pérez"), P("Ana", "x" * 29), P("   ", "Pérez"), P(".....", "Pérez"), P("Ana", "Pérez", "123"), {"nombre": "Ana Pérez"}]
    for cuerpo in malos:
        assert admin()("POST", "/api/admin/profesores", cuerpo).status == 400, f"profesor {cuerpo}"
    r = admin()("POST", "/api/admin/profesores", P("  vERÓNICA ", "hernández", " MONZÓN "))
    assert r.status == 201
    ids["p1"] = r.datos["id"]
    assert admin()("POST", "/api/admin/profesores", P("Verónica", "Hernández", "Monzón")).status == 409
    assert admin()("POST", "/api/admin/profesores", P("VERÓNICA", "HERNÁNDEZ", "MONZÓN")).status == 409   # mismo nombre, otra escritura
    ids["p2"] = admin()("POST", "/api/admin/profesores", P("Carlos", "Ramírez", "Soto")).datos["id"]
    ids["p3"] = admin()("POST", "/api/admin/profesores", P("Sin", "Materias", "Prueba")).datos["id"]
    ids["p4"] = admin()("POST", "/api/admin/profesores", P("Profesor", "Inactivo", "Prueba", activo=False)).datos["id"]

    for nombre in ["ab", "", "x" * 61, "<b>mal</b>"]:
        assert admin()("POST", "/api/admin/materias", {"nombre": nombre}).status == 400
    ids["m1"] = admin()("POST", "/api/admin/materias", {"nombre": "Aplicaciones Web"}).datos["id"]
    ids["m2"] = admin()("POST", "/api/admin/materias", {"nombre": "Bases de Datos"}).datos["id"]
    ids["m3"] = admin()("POST", "/api/admin/materias", {"nombre": "Idioma Extranjero"}).datos["id"]
    assert admin()("POST", "/api/admin/materias", {"nombre": "aplicaciones web"}).status == 409

    A = lambda p, m: admin()("POST", f"/api/admin/profesores/{ids[p]}/materias", {"materia_id": ids[m]}).status
    assert A("p1", "m1") == 201 and A("p1", "m1") == 409
    assert A("p2", "m1") == 201 and A("p2", "m2") == 201 and A("p4", "m3") == 201
    assert admin()("POST", f"/api/admin/profesores/{ids['p1']}/materias", {"materia_id": 999999}).status == 404
    assert admin()("POST", f"/api/admin/profesores/{ids['p1']}/materias", {"materia_id": "abc"}).status == 400

    m = [x["nombre"] for x in admin()("GET", f"/api/admin/profesores/{ids['p2']}/materias").datos]
    assert m == ["Aplicaciones Web", "Bases de Datos"]
    profs = admin()("GET", "/api/admin/profesores").datos
    p1 = next(p for p in profs if p["id"] == ids["p1"])
    assert p1["nombre"] == "Verónica Hernández Monzón"   # mayúsculas y espacios normalizados
    assert (p1["nombres"], p1["apellido_paterno"], p1["apellido_materno"]) == ("Verónica", "Hernández", "Monzón")
    assert len(next(p for p in profs if p["id"] == ids["p3"])["materias"]) == 0


def test_09b_asignaciones_grupo_profesor_materia(sql):
    G = lambda g: f"/api/admin/grupos/{ids[g]}/asignaciones"
    A = lambda g, p, m: admin()("POST", G(g), {"profesor_id": ids[p], "materia_id": ids[m]})
    assert A("g1", "p1", "m1").status == 201
    assert A("g1", "p1", "m1").status == 409                      # sin duplicados
    assert A("g1", "p2", "m1").status == 201 and A("g1", "p2", "m2").status == 201
    assert A("g2", "p2", "m1").status == 201                      # un profesor puede dar clase a varios grupos
    assert A("g1", "p4", "m3").status == 201                      # (profesor inactivo: no se ofrecerá a los alumnos)
    assert A("g1", "p1", "m2").status == 400                      # p1 no imparte m2: no se puede asignar
    assert admin()("POST", G("g1"), {"profesor_id": 999999, "materia_id": ids["m1"]}).status == 404
    assert admin()("POST", G("g1"), {"profesor_id": ids["p1"], "materia_id": 999999}).status == 404
    assert admin()("POST", G("g1"), {"profesor_id": "abc", "materia_id": ids["m1"]}).status == 400
    assert admin()("POST", G("g1"), {}).status == 400
    assert admin()("POST", "/api/admin/grupos/999999/asignaciones", {"profesor_id": ids["p1"], "materia_id": ids["m1"]}).status == 404
    assert admin()("GET", "/api/admin/grupos/999999/asignaciones").status == 404
    lista = admin()("GET", G("g1")).datos
    assert sorted((x["profesor_id"], x["materia_id"]) for x in lista) == sorted(
        [(ids["p1"], ids["m1"]), (ids["p2"], ids["m1"]), (ids["p2"], ids["m2"]), (ids["p4"], ids["m3"])])
    profs = {p["id"]: p for p in admin()("GET", "/api/admin/profesores").datos}
    assert [g["clave"] for g in profs[ids["p2"]]["grupos"]] == ["GTID233", "GTID244"]
    assert profs[ids["p3"]]["grupos"] == []                       # sin grupos → la interfaz lo advierte


def test_10_acceso_y_tabla_del_alumno():
    c = anonimo()
    grupos = c("GET", "/api/grupos").datos
    assert "GTID244" in [g["clave"] for g in grupos] and "GTID233" in [g["clave"] for g in grupos]
    assert all(set(g) == {"id", "clave", "descripcion"} for g in grupos)        # sin contraseñas ni datos internos
    # SIN contraseña no hay cuestionario (ni con el id de grupo correcto)
    assert c("GET", f"/api/grupos/{ids['g1']}/cuestionario").status == 403
    # contraseña incorrecta / de otro grupo / grupo sin contraseña
    assert entrar(c, ids["g1"], "incorrecta").status == 401
    assert entrar(c, ids["g1"], CLAVES["g2"]).status == 401                      # la de OTRO grupo no sirve
    assert entrar(c, ids["gSin"], "lo-que-sea").status == 409
    assert entrar(c, ids["g1"], "").status == 400
    assert entrar(c, 999999, "x").status == 404
    assert entrar(c, "abc", "x").status == 400
    assert c("GET", f"/api/grupos/{ids['g1']}/cuestionario").status == 403       # los intentos fallidos no autorizan nada
    estado["app"].extensions["limite_acceso_ip"].reiniciar()
    estado["app"].extensions["limite_acceso_grupo"].reiniciar()

    a1 = nuevo_alumno("g1")
    d = cuestionario(a1, ids["g1"]).datos
    filas = [(x["profesor"], x["materia"]) for x in d["asignaciones"]]
    assert filas == [("Carlos Ramírez Soto", "Aplicaciones Web"), ("Carlos Ramírez Soto", "Bases de Datos"),
                     ("Verónica Hernández Monzón", "Aplicaciones Web")]          # solo asignados a g1 y activos; sin duplicados
    assert [p["num"] for p in d["preguntas"]] == list(range(1, 13))
    assert d["disponibilidad"] == {"alumnos": 50, "encuestas": 0, "disponibles": 50}
    # la autorización de g1 NO sirve para pedir el cuestionario de otro grupo
    assert cuestionario(a1, ids["g2"]).status == 403
    a2 = nuevo_alumno("g2")
    assert [(x["profesor"], x["materia"]) for x in cuestionario(a2, ids["g2"]).datos["asignaciones"]] == [("Carlos Ramírez Soto", "Aplicaciones Web")]
    assert cuestionario(nuevo_alumno("gVacio"), ids["gVacio"]).datos["asignaciones"] == []      # grupo sin profesores
    # ya no existe ningún endpoint público que devuelva profesores sin contraseña
    for u in (f"/api/grupos/{ids['g1']}/profesores", "/api/profesores", f"/api/profesores/{ids['p1']}/materias"):
        assert c("GET", u).status == 404
    import json
    txt = json.dumps(d).lower()
    assert not any(x in txt for x in ("promedio", "password", "clave_acceso", CLAVES["g1"].lower()))


def test_11_encuesta_valida_guarda_1_encuesta_mas_evaluaciones_y_respuestas(sql):
    antes = {t: contar(sql, t) for t in ("encuestas", "evaluaciones", "respuestas")}
    c = nuevo_alumno("g1")
    body = cuerpo_encuesta(c, ids["g1"])
    for e in body["evaluaciones"]:
        e["respuestas"] = [5, 6, 7, 8, 9, 10, 5, 6, 7, 8, 9, 10]
    body["evaluaciones"][0]["comentario"] = "Muy bien"
    r = c("POST", "/api/encuestas", body)
    assert r.status == 201 and r.datos["disponibles"] == 49
    assert contar(sql, "encuestas") == antes["encuestas"] + 1                 # UNA encuesta…
    assert contar(sql, "evaluaciones") == antes["evaluaciones"] + 3           # …con tres profesores-materia…
    assert contar(sql, "respuestas") == antes["respuestas"] + 36              # …y 3 × 12 respuestas
    evs = ejecutar(sql, "SELECT * FROM evaluaciones WHERE encuesta_id=%s ORDER BY id", (r.datos["id"],))
    assert len(evs) == 3 and {(e["grupo_id"], e["profesor_id"], e["materia_id"]) for e in evs} == {
        (ids["g1"], ids["p2"], ids["m1"]), (ids["g1"], ids["p2"], ids["m2"]), (ids["g1"], ids["p1"], ids["m1"])}
    for e in evs:
        rs = ejecutar(sql, "SELECT num_pregunta, calificacion FROM respuestas WHERE evaluacion_id=%s ORDER BY num_pregunta", (e["id"],))
        assert [x["num_pregunta"] for x in rs] == list(range(1, 13))
        assert [x["calificacion"] for x in rs] == [5, 6, 7, 8, 9, 10, 5, 6, 7, 8, 9, 10]
    assert evs[0]["comentario"] == "Muy bien"
    # anónima: ninguna columna identifica a la persona
    assert [x["Field"] for x in ejecutar(sql, "SHOW COLUMNS FROM encuestas")] == ["id", "grupo_id", "creado_en"]
    assert [x["Field"] for x in ejecutar(sql, "SHOW COLUMNS FROM evaluaciones")] == [
        "id", "encuesta_id", "grupo_id", "profesor_id", "materia_id", "comentario", "creado_en"]
    # la autorización se consume: sin volver a escribir la contraseña no se puede enviar otra
    assert c("POST", "/api/encuestas", body).status == 403
    assert cuestionario(c, ids["g1"]).status == 403


def test_12_comentario_vacio_es_null_y_200_caracteres_valido(sql):
    r = enviar_ok("g1", 8, "")
    assert all(e["comentario"] is None for e in ejecutar(sql, "SELECT comentario FROM evaluaciones WHERE encuesta_id=%s", (r.datos["id"],)))
    enviar_ok("g1", 8, None)
    r = enviar_ok("g1", 8, "ñ" * 200)
    assert all(e["comentario"] == "ñ" * 200 for e in ejecutar(sql, "SELECT comentario FROM evaluaciones WHERE encuesta_id=%s", (r.datos["id"],)))


def test_13_servidor_rechaza_datos_manipulados_y_no_guarda_nada(sql):
    c = nuevo_alumno("g1")
    base = cuerpo_encuesta(c, ids["g1"])
    e0, r0, n0 = contar(sql, "evaluaciones"), contar(sql, "respuestas"), contar(sql, "encuestas")
    import copy

    def con(f):
        b = copy.deepcopy(base)
        f(b)
        return b

    ev = lambda b, i=0: b["evaluaciones"][i]
    casos = [
        ("grupo sin enviar", con(lambda b: b.pop("grupo_id")), 400, "grupo"),
        ("grupo no numérico", con(lambda b: b.update(grupo_id="abc")), 400, "grupo"),
        ("grupo booleano", con(lambda b: b.update(grupo_id=True)), 400, "grupo"),
        ("inyección SQL en grupo", con(lambda b: b.update(grupo_id="1 OR 1=1; DROP TABLE grupos;--")), 400, "grupo"),
        ("grupo inexistente", con(lambda b: b.update(grupo_id=999999)), 403, None),
        ("OTRO grupo (autorizado solo para g1)", con(lambda b: b.update(grupo_id=ids["g2"])), 403, None),
        ("sin evaluaciones", con(lambda b: b.update(evaluaciones=[])), 400, "evaluaciones"),
        ("evaluaciones no es arreglo", con(lambda b: b.update(evaluaciones="x")), 400, "evaluaciones"),
        ("profesor ajeno al grupo agregado", con(lambda b: b["evaluaciones"].append(
            {"profesor_id": ids["p3"], "materia_id": ids["m1"], "respuestas": R(8)})), 400, "evaluaciones"),
        ("profesor inventado", con(lambda b: b["evaluaciones"].append(
            {"profesor_id": 999999, "materia_id": ids["m1"], "respuestas": R(8)})), 400, "evaluaciones"),
        ("profesor inactivo agregado", con(lambda b: b["evaluaciones"].append(
            {"profesor_id": ids["p4"], "materia_id": ids["m3"], "respuestas": R(8)})), 400, "evaluaciones"),
        ("materia que el profesor no imparte a g1", con(lambda b: ev(b).update(materia_id=ids["m3"])), 400, "evaluaciones"),
        ("falta evaluar a un profesor", con(lambda b: b["evaluaciones"].pop()), 400, "evaluaciones"),
        ("profesor-materia repetido", con(lambda b: b["evaluaciones"].append(copy.deepcopy(ev(b)))), 400, "evaluaciones"),
        ("profesor con id texto", con(lambda b: ev(b).update(profesor_id=str(ids["p2"]) + " OR 1=1")), 400, "evaluaciones"),
        ("profesor booleano", con(lambda b: ev(b).update(profesor_id=True)), 400, "evaluaciones"),
        ("calificación 4", con(lambda b: ev(b).update(respuestas=[4] + R(8)[1:])), 400, "r_"),
        ("calificación 11", con(lambda b: ev(b).update(respuestas=[11] + R(8)[1:])), 400, "r_"),
        ("calificación decimal", con(lambda b: ev(b).update(respuestas=[7.5] + R(8)[1:])), 400, "r_"),
        ("calificación texto", con(lambda b: ev(b).update(respuestas=["8"] + R(8)[1:])), 400, "r_"),
        ("calificación booleana", con(lambda b: ev(b).update(respuestas=[True] + R(8)[1:])), 400, "r_"),
        ("calificación nula (selector vacío)", con(lambda b: ev(b).update(respuestas=[None] + R(8)[1:])), 400, "r_"),
        ("calificación 0", con(lambda b: ev(b).update(respuestas=[0] + R(8)[1:])), 400, "r_"),
        ("11 respuestas", con(lambda b: ev(b).update(respuestas=R(8)[:11])), 400, "r_"),
        ("13 respuestas", con(lambda b: ev(b).update(respuestas=R(13))), 400, "r_"),
        ("sin respuestas", con(lambda b: ev(b).pop("respuestas")), 400, "r_"),
        ("comentario de 201 caracteres", con(lambda b: ev(b).update(comentario="a" * 201)), 400, "c_"),
        ("comentario no es texto", con(lambda b: ev(b).update(comentario={"a": 1})), 400, "c_"),
    ]
    for nombre, cuerpo, status, campo in casos:
        r = c("POST", "/api/encuestas", cuerpo)
        assert r.status == status, f"{nombre}: esperaba {status} y fue {r.status} {r.datos}"
        if campo:
            assert r.datos["errores"] and any(k.startswith(campo) for k in r.datos["errores"]), f"{nombre}: {r.datos['errores']}"
    assert c("POST", "/api/encuestas", [1, 2, 3]).status == 400
    assert c("POST", "/api/encuestas", "texto").status == 400
    assert (contar(sql, "evaluaciones"), contar(sql, "respuestas"), contar(sql, "encuestas")) == (e0, r0, n0)   # nada quedó a medias
    malo = estado["app"].test_client().post("/api/encuestas", data="{malo", content_type="application/json")
    assert malo.status_code == 400
    assert contar(sql, "grupos") >= 3     # la inyección no hizo nada
    # tras tantos rechazos, la autorización sigue vigente y la encuesta correcta sí se guarda
    assert c("POST", "/api/encuestas", base).status == 201


def test_14_mysql_impide_datos_inconsistentes(sql):
    def falla(q, p, codigos):
        with pytest.raises(pymysql.err.MySQLError) as exc:
            ejecutar(sql, q, p)
        assert exc.value.args[0] in codigos, str(exc.value)

    FK, CHECK, DUP = (1216, 1452), (3819, 4025), (1062,)   # 4025 = mismo CHECK en MariaDB
    enc = ejecutar(sql, "SELECT id FROM encuestas WHERE grupo_id=%s LIMIT 1", (ids["g1"],))[0]["id"]
    ev = ejecutar(sql, "SELECT id FROM evaluaciones LIMIT 1")[0]["id"]
    INS = "INSERT INTO evaluaciones (encuesta_id,grupo_id,profesor_id,materia_id) VALUES (%s,%s,%s,%s)"
    falla("INSERT INTO respuestas (evaluacion_id,num_pregunta,calificacion) VALUES (%s,%s,%s)", (ev, 99, 8), FK)
    falla("UPDATE respuestas SET calificacion = 4 WHERE evaluacion_id = %s AND num_pregunta = 1", (ev,), CHECK)
    falla("UPDATE respuestas SET calificacion = 11 WHERE evaluacion_id = %s AND num_pregunta = 1", (ev,), CHECK)
    falla("INSERT INTO respuestas (evaluacion_id,num_pregunta,calificacion) VALUES (%s,1,8)", (ev,), DUP)
    ejecutar(sql, "INSERT INTO encuestas (grupo_id) VALUES (%s)", (ids["g1"],))
    vacia = ejecutar(sql, "SELECT MAX(id) AS id FROM encuestas")[0]["id"]            # encuesta de g1 sin evaluaciones
    falla(INS, (vacia, ids["g1"], ids["p1"], ids["m2"]), FK)               # p1 no imparte m2
    falla(INS, (vacia, 999999, ids["p1"], ids["m1"]), FK)
    falla(INS, (vacia, ids["g2"], ids["p2"], ids["m1"]), FK)               # la encuesta es de g1: no admite evaluaciones de g2
    falla(INS, (999999, ids["g1"], ids["p1"], ids["m1"]), FK)              # encuesta inexistente
    ejecutar(sql, "DELETE FROM encuestas WHERE id = %s", (vacia,))
    falla(INS, (enc, ids["g1"], ids["p1"], ids["m1"]), DUP)                # el mismo profesor-materia dos veces en una encuesta
    falla("INSERT INTO asignaciones (grupo_id,profesor_id,materia_id) VALUES (%s,%s,%s)", (ids["g1"], ids["p1"], ids["m3"]), FK)   # p1 no imparte m3
    falla("INSERT INTO asignaciones (grupo_id,profesor_id,materia_id) VALUES (%s,%s,%s)", (ids["g1"], ids["p1"], ids["m1"]), DUP)
    falla("INSERT INTO asignaciones (grupo_id,profesor_id,materia_id) VALUES (%s,%s,%s)", (999999, ids["p1"], ids["m1"]), FK)
    falla("INSERT INTO encuestas (grupo_id) VALUES (999999)", (), FK)
    falla("INSERT INTO grupos (clave) VALUES ('abc1234')", (), CHECK)
    falla("INSERT INTO grupos (clave) VALUES ('GSI0252')", (), CHECK)      # formato anterior (3 letras + 4 dígitos)
    falla("INSERT INTO grupos (clave, num_alumnos) VALUES ('ZZZZ999', 501)", (), CHECK)
    falla("INSERT INTO grupos (clave) VALUES ('GTID244')", (), DUP)


def test_15_historial_protegido_y_desactivar_conserva(sql):
    E0 = contar(sql, "evaluaciones")
    r = admin()("DELETE", f"/api/admin/grupos/{ids['g1']}")
    assert r.status == 409 and "Desactívalo" in r.datos["error"]
    assert admin()("DELETE", f"/api/admin/profesores/{ids['p1']}").status == 409
    assert admin()("DELETE", f"/api/admin/materias/{ids['m1']}").status == 409
    assert admin()("DELETE", f"/api/admin/profesores/{ids['p1']}/materias/{ids['m1']}").status == 409
    assert contar(sql, "evaluaciones") == E0

    c = nuevo_alumno("g1")
    base = cuerpo_encuesta(c, ids["g1"])                    # tabla completa con p1 activo
    nombres = lambda: [x["profesor"] for x in cuestionario(c, ids["g1"]).datos["asignaciones"]]
    P1 = {"activo": False}
    assert admin()("PUT", f"/api/admin/profesores/{ids['p1']}", P1).status == 200      # activar/desactivar sin tocar el nombre
    assert contar(sql, "evaluaciones") == E0
    assert "Verónica Hernández Monzón" not in nombres()
    assert c("POST", "/api/encuestas", base).status == 400                              # lista vieja con el profesor ya inactivo
    assert admin()("PUT", f"/api/admin/profesores/{ids['p1']}", {"activo": True}).status == 200
    assert "Verónica Hernández Monzón" in nombres()
    # editar el nombre completo exige nombre y apellido
    assert admin()("PUT", f"/api/admin/profesores/{ids['p1']}", {"nombre": "Otro Nombre", "activo": True}).status == 400
    assert admin()("PUT", f"/api/admin/profesores/{ids['p1']}", {"nombres": "Verónica", "apellido_paterno": "Hernández",
                                                                 "apellido_materno": "Monzón", "activo": True}).status == 200

    M1 = {"nombre": "Aplicaciones Web", "activo": False}
    assert admin()("PUT", f"/api/admin/materias/{ids['m1']}", M1).status == 200
    assert all(x["materia"] != "Aplicaciones Web" for x in cuestionario(c, ids["g1"]).datos["asignaciones"])
    assert c("POST", "/api/encuestas", base).status == 400
    assert admin()("PUT", f"/api/admin/materias/{ids['m1']}", {**M1, "activo": True}).status == 200

    G1 = {"clave": "GTID244", "activo": False}
    assert admin()("PUT", f"/api/admin/grupos/{ids['g1']}", G1).status == 200
    assert c("POST", "/api/encuestas", base).status == 404                              # grupo inactivo
    assert entrar(anonimo(), ids["g1"], CLAVES["g1"]).status == 404
    assert admin()("PUT", f"/api/admin/grupos/{ids['g1']}", {**G1, "activo": True}).status == 200

    # una asignación con evaluaciones no se borra: se desactiva y los alumnos dejan de verla
    ruta = f"/api/admin/grupos/{ids['g1']}/asignaciones/{ids['p1']}/{ids['m1']}"
    assert admin()("DELETE", ruta).status == 409
    assert admin()("PUT", ruta, {"activo": False}).status == 200
    assert "Verónica Hernández Monzón" not in nombres()
    assert c("POST", "/api/encuestas", base).status == 400
    assert admin()("PUT", ruta, {"activo": "no"}).status == 400
    assert admin()("PUT", ruta + "9", {"activo": True}).status == 404
    assert admin()("PUT", ruta, {"activo": True}).status == 200
    assert c("POST", "/api/encuestas", base).status == 201
    assert contar(sql, "evaluaciones") == E0 + 3

    assert admin()("DELETE", f"/api/admin/grupos/{ids['gVacio']}").status == 200
    assert admin()("DELETE", f"/api/admin/profesores/{ids['p3']}").status == 200


def test_16_reportes_calculos_filtros_y_sin_duplicar(sql):
    ejecutar(sql, "DELETE FROM evaluaciones")
    ejecutar(sql, "DELETE FROM encuestas")
    k = [5, 6, 7, 8, 9, 10, 5, 6, 7, 8, 9, 10]

    def enviar(g, calif, comentario=None):
        c = nuevo_alumno(g)
        body = cuerpo_encuesta(c, ids[g])
        for e in body["evaluaciones"]:
            e["respuestas"] = calif[(e["profesor_id"], e["materia_id"])]
        if comentario:
            body["evaluaciones"][0]["comentario"] = comentario
        assert c("POST", "/api/encuestas", body).status == 201

    p1m1, p2m1, p2m2 = (ids["p1"], ids["m1"]), (ids["p2"], ids["m1"]), (ids["p2"], ids["m2"])
    enviar("g1", {p1m1: R(10), p2m1: k, p2m2: R(9)}, "Excelente")     # primera en la lista: Carlos–Aplicaciones Web (p2m1)
    enviar("g1", {p1m1: R(6), p2m1: R(8), p2m2: R(7)})
    enviar("g2", {p2m1: R(5)})

    A = lambda url: admin()("GET", url)
    approx = pytest.approx

    d = A(f"/api/admin/reportes/grupo?grupo={ids['g1']}").datos
    assert d["resumen"]["encuestas"] == 2                          # dos envíos…
    assert d["resumen"]["evaluaciones"] == 6                       # …de tres profesores-materia cada uno…
    assert d["resumen"]["respuestas"] == 72                        # …y 6 × 12 calificaciones
    assert d["resumen"]["promedio"] == approx((10 + 6 + 7.5 + 8 + 9 + 7) / 6)
    assert len(d["porProfesorMateria"]) == 3
    f = lambda p, m: next(x for x in d["porProfesorMateria"] if x["profesor_id"] == ids[p] and x["materia_id"] == ids[m])
    assert f("p1", "m1")["evaluaciones"] == 2 and f("p1", "m1")["promedio"] == approx(8)
    assert f("p2", "m1")["evaluaciones"] == 2 and f("p2", "m1")["promedio"] == approx(7.75)
    assert f("p2", "m2")["promedio"] == approx(8)
    pp2 = next(x for x in d["porProfesor"] if x["id"] == ids["p2"])
    assert pp2["evaluaciones"] == 4 and pp2["promedio"] == approx((7.5 + 8 + 9 + 7) / 4)
    pm1 = next(x for x in d["porMateria"] if x["id"] == ids["m1"])
    assert pm1["evaluaciones"] == 4 and pm1["promedio"] == approx((10 + 6 + 7.5 + 8) / 4)
    assert len(d["porPregunta"]) == 12
    assert d["porPregunta"][0] == approx((10 + 6 + 5 + 8 + 9 + 7) / 6) and d["porPregunta"][1] == approx((10 + 6 + 6 + 8 + 9 + 7) / 6)
    assert len(d["detalle"]) == 6 and any(x["comentario"] == "Excelente" for x in d["detalle"])
    assert all(x["grupo"] == "GTID244" and len(x["respuestas"]) == 12 for x in d["detalle"])
    assert len({x["encuesta"] for x in d["detalle"]}) == 2
    assert isinstance(d["detalle"][0]["fecha"], str) and "T" in d["detalle"][0]["fecha"]

    r = A(f"/api/admin/reportes/general-grupo?grupo={ids['g1']}")
    assert r.status == 200 and r.datos["filtros"]["grupo"]["clave"] == "GTID244"
    assert r.datos["resumen"]["promedio"] == approx(47.5 / 6)
    fila = next(x for x in r.datos["porProfesorMateria"] if x["profesor_id"] == ids["p2"] and x["materia_id"] == ids["m1"])
    assert fila["preguntas"] == [(a + 8) / 2 for a in k]

    d = A(f"/api/admin/reportes/profesor?profesor={ids['p2']}").datos
    assert d["resumen"]["encuestas"] == 3 and d["resumen"]["evaluaciones"] == 5 and d["resumen"]["respuestas"] == 60
    assert d["resumen"]["promedio"] == approx((7.5 + 8 + 9 + 7 + 5) / 5)
    d = A(f"/api/admin/reportes/profesor?profesor={ids['p2']}&materia={ids['m1']}").datos
    assert d["resumen"]["evaluaciones"] == 3 and d["resumen"]["promedio"] == approx((7.5 + 8 + 5) / 3)
    d = A(f"/api/admin/reportes/profesor?profesor={ids['p2']}&grupo={ids['g2']}").datos
    assert d["resumen"]["encuestas"] == 1 and d["resumen"]["evaluaciones"] == 1 and d["resumen"]["promedio"] == approx(5)
    d = A(f"/api/admin/reportes/profesor?profesor={ids['p2']}&grupo={ids['g2']}&materia={ids['m2']}").datos
    assert d["vacio"] is True and d["detalle"] == []

    d = A(f"/api/admin/reportes/grupo-profesor?grupo={ids['g1']}&profesor={ids['p2']}").datos
    assert d["resumen"]["encuestas"] == 2 and d["resumen"]["evaluaciones"] == 4
    assert all(x["grupo"] == "GTID244" and x["profesor"] == "Carlos Ramírez Soto" for x in d["detalle"])
    d = A(f"/api/admin/reportes/grupo-profesor?grupo={ids['g1']}&profesor={ids['p2']}&materia={ids['m2']}").datos
    assert d["resumen"]["evaluaciones"] == 2 and d["resumen"]["promedio"] == approx(8)
    assert all(x["materia"] == "Bases de Datos" for x in d["detalle"])

    assert A("/api/admin/reportes/grupo").status == 400
    assert A(f"/api/admin/reportes/grupo-profesor?grupo={ids['g1']}").status == 400
    assert A("/api/admin/reportes/profesor").status == 400
    assert A("/api/admin/reportes/grupo?grupo=abc").status == 400
    assert A("/api/admin/reportes/grupo?grupo=999999").status == 404
    assert A(f"/api/admin/reportes/grupo-profesor?grupo={ids['g1']}&profesor={ids['p1']}&materia={ids['m2']}").status == 400
    assert A(f"/api/admin/reportes/grupo-profesor?grupo={ids['g2']}&profesor={ids['p1']}").status == 400   # p1 no da clase a g2
    assert A("/api/admin/reportes/inventado?grupo=1").status == 404
    assert A("/api/admin/reportes/grupo?grupo=1%20OR%201=1").status == 400


def test_17_reportes_sin_registros_mensaje_vacio(sql):
    ejecutar(sql, "DELETE FROM evaluaciones WHERE grupo_id = %s", (ids["g2"],))
    ejecutar(sql, "DELETE FROM encuestas WHERE grupo_id = %s", (ids["g2"],))
    for t in ("grupo", "general-grupo"):
        d = admin()("GET", f"/api/admin/reportes/{t}?grupo={ids['g2']}").datos
        assert d["vacio"] is True and d["resumen"]["evaluaciones"] == 0 and d["resumen"]["encuestas"] == 0
        assert d["resumen"]["promedio"] is None and d["detalle"] == []


def test_18_eliminar_evaluacion_borra_respuestas_en_cascada_y_encuesta_vacia(sql):
    evs = ejecutar(sql, "SELECT id, encuesta_id FROM evaluaciones WHERE encuesta_id = (SELECT MIN(id) FROM encuestas)")
    assert len(evs) == 3
    antes_r, antes_n = contar(sql, "respuestas"), contar(sql, "encuestas")
    assert admin()("DELETE", f"/api/admin/evaluaciones/{evs[0]['id']}").status == 200
    assert contar(sql, "respuestas") == antes_r - 12
    assert contar(sql, "encuestas") == antes_n                      # la encuesta conserva las otras dos evaluaciones
    assert admin()("DELETE", f"/api/admin/evaluaciones/{evs[0]['id']}").status == 404
    assert admin()("DELETE", f"/api/admin/evaluaciones/{evs[1]['id']}").status == 200
    assert admin()("DELETE", f"/api/admin/evaluaciones/{evs[2]['id']}").status == 200
    assert contar(sql, "encuestas") == antes_n - 1                  # sin evaluaciones, la encuesta vacía no ocupa un lugar
    assert admin()("DELETE", "/api/admin/evaluaciones/abc").status == 400


def test_19_cerrar_sesion_invalida_en_el_servidor():
    otro = cliente(estado["app"])
    otro("POST", "/api/admin/login", {"usuario": "admin", "password": PASS})
    assert otro("GET", "/api/admin/me").status == 200
    assert otro("POST", "/api/admin/logout", {}).status == 200
    assert otro("GET", "/api/admin/me").status == 401
    assert otro("GET", "/api/admin/reportes/grupo?grupo=1").status == 401
    assert anonimo()("GET", "/api/admin/me", headers={"Cookie": "ed.sid=inventada"}).status == 401


def test_20_sesion_vieja_no_sirve_tras_nuevo_login_y_expira_por_inactividad(sql):
    # Cookie robada de una sesión cerrada
    a = estado["app"].test_client()
    r = a.post("/api/admin/login", json={"usuario": "admin", "password": PASS})
    token = a.get_cookie("ed.sid").value
    a.post("/api/admin/logout", json={})
    b = estado["app"].test_client()
    assert b.get("/api/admin/me", headers={"Cookie": f"ed.sid={token}"}).status_code == 401
    # Expiración: se fuerza `expires` al pasado
    c = estado["app"].test_client()
    c.post("/api/admin/login", json={"usuario": "admin", "password": PASS})
    assert c.get("/api/admin/me").status_code == 200
    ejecutar(sql, "UPDATE sesiones SET expires = 1")
    assert c.get("/api/admin/me").status_code == 401


def test_21_admin_desactivado_no_entra_ni_conserva_sesion(sql):
    ejecutar(sql, "INSERT INTO administradores (usuario, nombre, password_hash, activo) VALUES ('baja','Baja',%s,0)",
             (bcrypt.hashpw(b"OtraClave12345", bcrypt.gensalt(rounds=6)).decode(),))
    assert anonimo()("POST", "/api/admin/login", {"usuario": "baja", "password": "OtraClave12345"}).status == 401
    # un administrador activo con sesión abierta pierde acceso en cuanto se desactiva
    c = cliente(estado["app"])
    ejecutar(sql, "INSERT INTO administradores (usuario, nombre, password_hash) VALUES ('temporal','Temp',%s)",
             (bcrypt.hashpw(b"TempClave12345", bcrypt.gensalt(rounds=6)).decode(),))
    assert c("POST", "/api/admin/login", {"usuario": "temporal", "password": "TempClave12345"}).status == 200
    assert c("GET", "/api/admin/me").status == 200
    ejecutar(sql, "UPDATE administradores SET activo = 0 WHERE usuario = 'temporal'")
    assert c("GET", "/api/admin/me").status == 401


def test_22_fuerza_bruta_responde_429_al_final():
    estado["app"].extensions["limite_login"].reiniciar()
    c = anonimo()
    ultimo = None
    for i in range(12):
        ultimo = c("POST", "/api/admin/login", {"usuario": "admin", "password": f"mala{i}"})
    assert ultimo.status == 429
    # aun con la clave correcta, durante el bloqueo no se entra
    assert c("POST", "/api/admin/login", {"usuario": "admin", "password": PASS}).status == 429
