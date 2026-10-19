"""Pruebas de integración contra una base MySQL REAL (sin simulaciones).

Preparación: ver PRUEBAS.md (sección "Cómo ejecutar las pruebas automáticas").   Ejecutar:  pytest
"""
import bcrypt
import pymysql
import pytest

from app import config as cfgmod
from app import crear_app
from app import db as dbmod

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
    for t in ["respuestas", "evaluaciones", "profesor_materia", "profesores", "materias", "grupos", "administradores", "sesiones"]:
        ejecutar(sql, f"DELETE FROM {t}")
    ejecutar(sql, "SET FOREIGN_KEY_CHECKS = 1")
    ejecutar(sql, "INSERT INTO administradores (usuario, nombre, password_hash) VALUES (%s, %s, %s)",
             ("admin", "Admin Pruebas", bcrypt.hashpw(PASS.encode(), bcrypt.gensalt(rounds=6)).decode()))
    estado["app"] = crear_app()


def anonimo():
    return cliente(estado["app"])


def admin():
    return estado["admin"]


def ev_ok(**o):
    base = {"grupo": "GSI0252", "profesor_id": ids["p1"], "materia_id": ids["m1"], "respuestas": R(9), "comentario": "Muy bien"}
    base.update(o)
    return {k: v for k, v in base.items() if v is not Ellipsis}


def test_01_api_responde_y_conecta_con_mysql():
    r = anonimo()("GET", "/api/salud")
    assert r.status == 200 and r.datos["baseDeDatos"] == "conectada"


def test_02_sin_sesion_todos_los_endpoints_admin_dan_401():
    c = anonimo()
    rutas = [
        ("GET", "/api/admin/grupos", None), ("POST", "/api/admin/grupos", {"clave": "ABC1234"}), ("PUT", "/api/admin/grupos/1", {}),
        ("DELETE", "/api/admin/grupos/1", None), ("GET", "/api/admin/profesores", None),
        ("POST", "/api/admin/profesores", {"nombre": "Persona Prueba"}), ("DELETE", "/api/admin/profesores/1", None),
        ("GET", "/api/admin/profesores/1/materias", None), ("POST", "/api/admin/profesores/1/materias", {"materia_id": 1}),
        ("GET", "/api/admin/materias", None), ("POST", "/api/admin/materias", {"nombre": "Algo"}),
        ("DELETE", "/api/admin/materias/1", None), ("DELETE", "/api/admin/evaluaciones/1", None), ("GET", "/api/admin/me", None),
        ("GET", "/api/admin/reportes/grupo?grupo=1", None), ("GET", "/api/admin/reportes/profesor?profesor=1", None),
        ("GET", "/api/admin/reportes/grupo-profesor?grupo=1&profesor=1", None), ("GET", "/api/admin/reportes/general-grupo?grupo=1", None),
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


def test_08_grupos_crear_validar_duplicar_editar():
    for clave in ["GTID244", "ab1234", "ABCD123", "AB12345", "", "ABC 123", "AB1-234", "ABC12\n34"]:
        assert admin()("POST", "/api/admin/grupos", {"clave": clave}).status == 400, f'clave "{clave!r}"'
    assert admin()("POST", "/api/admin/grupos", {}).status == 400
    r = admin()("POST", "/api/admin/grupos", {"clave": "gsi0252", "descripcion": "Sistemas 5to"})
    assert r.status == 201
    ids["g1"] = r.datos["id"]
    assert admin()("POST", "/api/admin/grupos", {"clave": "GSI0252"}).status == 409
    ids["g2"] = admin()("POST", "/api/admin/grupos", {"clave": "GTI0100"}).datos["id"]
    ids["gVacio"] = admin()("POST", "/api/admin/grupos", {"clave": "VAC0001"}).datos["id"]
    lista = admin()("GET", "/api/admin/grupos").datos
    assert next(g for g in lista if g["id"] == ids["g1"])["clave"] == "GSI0252"      # se normaliza a mayúsculas
    assert admin()("PUT", f"/api/admin/grupos/{ids['g2']}", {"clave": "GTI0101", "descripcion": "Editado", "activo": True}).status == 200
    assert admin()("PUT", "/api/admin/grupos/999999", {"clave": "ZZZ0000"}).status == 404


def test_09_profesores_y_materias_validaciones_y_asignacion():
    for nombre in ["Ana", "Juan123 Pérez", "<script>alert(1)</script>", "x" * 61, "", None]:
        assert admin()("POST", "/api/admin/profesores", {"nombre": nombre}).status == 400, f"profesor {nombre}"
    r = admin()("POST", "/api/admin/profesores", {"nombre": "  Verónica   Hernández  Monzón "})
    assert r.status == 201
    ids["p1"] = r.datos["id"]
    assert admin()("POST", "/api/admin/profesores", {"nombre": "Verónica Hernández Monzón"}).status == 409
    ids["p2"] = admin()("POST", "/api/admin/profesores", {"nombre": "Carlos Ramírez Soto"}).datos["id"]
    ids["p3"] = admin()("POST", "/api/admin/profesores", {"nombre": "Sin Materias Prueba"}).datos["id"]
    ids["p4"] = admin()("POST", "/api/admin/profesores", {"nombre": "Profesor Inactivo Prueba", "activo": False}).datos["id"]

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
    assert next(p for p in profs if p["id"] == ids["p1"])["nombre"] == "Verónica Hernández Monzón"   # espacios normalizados
    assert len(next(p for p in profs if p["id"] == ids["p3"])["materias"]) == 0


def test_10_catalogo_del_alumno():
    c = anonimo()
    profs = c("GET", "/api/profesores").datos
    nombres = [p["nombre"] for p in profs]
    assert "Carlos Ramírez Soto" in nombres
    assert "Profesor Inactivo Prueba" not in nombres, "no debe listar profesores inactivos"
    assert [m["nombre"] for m in c("GET", f"/api/profesores/{ids['p1']}/materias").datos] == ["Aplicaciones Web"]
    assert len(c("GET", f"/api/profesores/{ids['p2']}/materias").datos) == 2
    assert c("GET", f"/api/profesores/{ids['p3']}/materias").datos == []
    assert c("GET", f"/api/profesores/{ids['p4']}/materias").datos == []
    assert c("GET", "/api/profesores/abc/materias").status == 400
    assert c("GET", "/api/profesores/1%20OR%201=1/materias").status == 400
    import json
    txt = json.dumps(profs).lower()
    assert not any(x in txt for x in ("promedio", "evaluaciones", "password"))   # sin datos sensibles


def test_11_evaluacion_valida_guarda_1_mas_12_respuestas(sql):
    c = anonimo()
    antes_e, antes_r = contar(sql, "evaluaciones"), contar(sql, "respuestas")
    r = c("POST", "/api/evaluaciones", ev_ok(grupo="gsi0252", respuestas=[5, 6, 7, 8, 9, 10, 5, 6, 7, 8, 9, 10]))
    assert r.status == 201
    assert contar(sql, "evaluaciones") == antes_e + 1 and contar(sql, "respuestas") == antes_r + 12
    e = ejecutar(sql, "SELECT * FROM evaluaciones WHERE id=%s", (r.datos["id"],))[0]
    assert (e["grupo_id"], e["profesor_id"], e["materia_id"]) == (ids["g1"], ids["p1"], ids["m1"])
    rs = ejecutar(sql, "SELECT num_pregunta, calificacion FROM respuestas WHERE evaluacion_id=%s ORDER BY num_pregunta", (r.datos["id"],))
    assert [x["num_pregunta"] for x in rs] == list(range(1, 13))
    assert [x["calificacion"] for x in rs] == [5, 6, 7, 8, 9, 10, 5, 6, 7, 8, 9, 10]
    cols = [x["Field"] for x in ejecutar(sql, "SHOW COLUMNS FROM evaluaciones")]
    assert cols == ["id", "grupo_id", "profesor_id", "materia_id", "comentario", "creado_en"]   # anónima


def test_12_comentario_vacio_es_null_y_200_caracteres_valido(sql):
    c = anonimo()
    r = c("POST", "/api/evaluaciones", ev_ok(comentario=""))
    assert r.status == 201
    assert ejecutar(sql, "SELECT comentario FROM evaluaciones WHERE id=%s", (r.datos["id"],))[0]["comentario"] is None
    assert c("POST", "/api/evaluaciones", ev_ok(comentario=Ellipsis)).status == 201
    assert c("POST", "/api/evaluaciones", ev_ok(comentario="ñ" * 200)).status == 201


def test_13_servidor_rechaza_datos_manipulados_y_no_guarda_nada(sql):
    c = anonimo()
    e0, r0 = contar(sql, "evaluaciones"), contar(sql, "respuestas")
    casos = [
        ("grupo inexistente", ev_ok(grupo="ZZZ9999"), "grupo"),
        ("grupo con formato inválido", ev_ok(grupo="GTID244"), "grupo"),
        ("grupo vacío", ev_ok(grupo=""), "grupo"),
        ("grupo no es texto", ev_ok(grupo=1234567), "grupo"),
        ("inyección SQL en grupo", ev_ok(grupo="A'; DROP TABLE grupos;--"), "grupo"),
        ("profesor inexistente", ev_ok(profesor_id=999999), "profesor"),
        ("profesor inactivo", ev_ok(profesor_id=ids["p4"], materia_id=ids["m3"]), "profesor"),
        ("profesor no numérico", ev_ok(profesor_id="1 OR 1=1"), "profesor"),
        ("profesor booleano", ev_ok(profesor_id=True), "profesor"),
        ("sin profesor", ev_ok(profesor_id=Ellipsis), "profesor"),
        ("materia que NO es del profesor", ev_ok(profesor_id=ids["p1"], materia_id=ids["m2"]), "materia"),
        ("materia inexistente", ev_ok(materia_id=999999), "materia"),
        ("sin materia", ev_ok(materia_id=Ellipsis), "materia"),
        ("calificación 4", ev_ok(respuestas=[4] + R(9)[1:] + [9, 9]), "preguntas"),
        ("calificación 11", ev_ok(respuestas=[11] + R(11)), "preguntas"),
        ("calificación decimal", ev_ok(respuestas=[7.5] + R(11)), "preguntas"),
        ("calificación como texto", ev_ok(respuestas=["8"] + R(11)), "preguntas"),
        ("calificación booleana", ev_ok(respuestas=[True] + R(11)), "preguntas"),
        ("calificación nula", ev_ok(respuestas=[None] + R(11)), "preguntas"),
        ("11 respuestas", ev_ok(respuestas=R(11)), "preguntas"),
        ("13 respuestas", ev_ok(respuestas=R(13)), "preguntas"),
        ("respuestas no es arreglo", ev_ok(respuestas="999999999999"), "preguntas"),
        ("sin respuestas", ev_ok(respuestas=Ellipsis), "preguntas"),
        ("comentario de 201 caracteres", ev_ok(comentario="a" * 201), "comentario"),
        ("comentario no es texto", ev_ok(comentario={"a": 1}), "comentario"),
    ]
    for nombre, cuerpo, campo in casos:
        r = c("POST", "/api/evaluaciones", cuerpo)
        assert r.status == 400, f"{nombre}: esperaba 400 y fue {r.status}"
        assert r.datos["errores"] and campo in r.datos["errores"], f"{nombre}: falta mensaje en '{campo}' → {r.datos['errores']}"
    assert c("POST", "/api/evaluaciones", [1, 2, 3]).status == 400
    assert c("POST", "/api/evaluaciones", "texto").status == 400
    assert contar(sql, "evaluaciones") == e0 and contar(sql, "respuestas") == r0
    malo = estado["app"].test_client().post("/api/evaluaciones", data="{malo", content_type="application/json")
    assert malo.status_code == 400
    assert contar(sql, "grupos") >= 3     # la inyección no hizo nada


def test_14_mysql_impide_datos_inconsistentes(sql):
    def falla(q, p, codigos):
        with pytest.raises(pymysql.err.MySQLError) as exc:
            ejecutar(sql, q, p)
        assert exc.value.args[0] in codigos, str(exc.value)

    FK, CHECK, DUP = (1216, 1452), (3819,), (1062,)
    ev = ejecutar(sql, "SELECT id FROM evaluaciones LIMIT 1")[0]["id"]
    falla("INSERT INTO respuestas (evaluacion_id,num_pregunta,calificacion) VALUES (%s,%s,%s)", (ev, 99, 8), FK)
    falla("UPDATE respuestas SET calificacion = 4 WHERE evaluacion_id = %s AND num_pregunta = 1", (ev,), CHECK)
    falla("UPDATE respuestas SET calificacion = 11 WHERE evaluacion_id = %s AND num_pregunta = 1", (ev,), CHECK)
    falla("INSERT INTO respuestas (evaluacion_id,num_pregunta,calificacion) VALUES (%s,1,8)", (ev,), DUP)
    falla("INSERT INTO evaluaciones (grupo_id,profesor_id,materia_id) VALUES (%s,%s,%s)", (ids["g1"], ids["p1"], ids["m2"]), FK)
    falla("INSERT INTO evaluaciones (grupo_id,profesor_id,materia_id) VALUES (%s,%s,%s)", (999999, ids["p1"], ids["m1"]), FK)
    falla("INSERT INTO grupos (clave) VALUES ('abc1234')", (), CHECK)
    falla("INSERT INTO grupos (clave) VALUES ('GSI0252')", (), DUP)


def test_15_historial_protegido_y_desactivar_conserva(sql):
    E0 = contar(sql, "evaluaciones")
    r = admin()("DELETE", f"/api/admin/grupos/{ids['g1']}")
    assert r.status == 409 and "Desactívalo" in r.datos["error"]
    assert admin()("DELETE", f"/api/admin/profesores/{ids['p1']}").status == 409
    assert admin()("DELETE", f"/api/admin/materias/{ids['m1']}").status == 409
    assert admin()("DELETE", f"/api/admin/profesores/{ids['p1']}/materias/{ids['m1']}").status == 409
    assert contar(sql, "evaluaciones") == E0

    P1 = {"nombre": "Verónica Hernández Monzón", "activo": False}
    assert admin()("PUT", f"/api/admin/profesores/{ids['p1']}", P1).status == 200
    assert contar(sql, "evaluaciones") == E0
    assert "Verónica Hernández Monzón" not in [p["nombre"] for p in anonimo()("GET", "/api/profesores").datos]
    assert anonimo()("POST", "/api/evaluaciones", ev_ok()).status == 400
    assert admin()("PUT", f"/api/admin/profesores/{ids['p1']}", {**P1, "activo": True}).status == 200

    M1 = {"nombre": "Aplicaciones Web", "activo": False}
    assert admin()("PUT", f"/api/admin/materias/{ids['m1']}", M1).status == 200
    assert anonimo()("GET", f"/api/profesores/{ids['p1']}/materias").datos == []
    assert anonimo()("POST", "/api/evaluaciones", ev_ok()).status == 400
    assert admin()("PUT", f"/api/admin/materias/{ids['m1']}", {**M1, "activo": True}).status == 200
    assert anonimo()("POST", "/api/evaluaciones", ev_ok()).status == 201

    G1 = {"clave": "GSI0252", "activo": False}
    assert admin()("PUT", f"/api/admin/grupos/{ids['g1']}", G1).status == 200
    assert anonimo()("POST", "/api/evaluaciones", ev_ok()).status == 400
    assert admin()("PUT", f"/api/admin/grupos/{ids['g1']}", {**G1, "activo": True}).status == 200

    assert admin()("DELETE", f"/api/admin/grupos/{ids['gVacio']}").status == 200
    assert admin()("DELETE", f"/api/admin/profesores/{ids['p3']}").status == 200


def test_16_reportes_calculos_filtros_y_sin_duplicar(sql):
    ejecutar(sql, "DELETE FROM evaluaciones")
    c = anonimo()

    def enviar(grupo, prof, mat, resp, com=None):
        body = {"grupo": grupo, "profesor_id": prof, "materia_id": mat, "respuestas": resp}
        if com:
            body["comentario"] = com
        assert c("POST", "/api/evaluaciones", body).status == 201

    enviar("GSI0252", ids["p1"], ids["m1"], R(10), "Excelente")
    enviar("GSI0252", ids["p1"], ids["m1"], R(6))
    enviar("GSI0252", ids["p2"], ids["m1"], [5, 6, 7, 8, 9, 10, 5, 6, 7, 8, 9, 10])
    enviar("GSI0252", ids["p2"], ids["m2"], R(9))
    enviar("GTI0101", ids["p2"], ids["m1"], R(5))

    A = lambda url: admin()("GET", url)
    approx = pytest.approx

    d = A(f"/api/admin/reportes/grupo?grupo={ids['g1']}").datos
    assert d["resumen"]["evaluaciones"] == 4
    assert d["resumen"]["respuestas"] == 48                        # 4 × 12: ninguna duplicada
    assert d["resumen"]["promedio"] == approx((10 + 6 + 7.5 + 9) / 4)
    assert len(d["porProfesorMateria"]) == 3
    f = lambda p, m: next(x for x in d["porProfesorMateria"] if x["profesor_id"] == ids[p] and x["materia_id"] == ids[m])
    assert f("p1", "m1")["evaluaciones"] == 2 and f("p1", "m1")["promedio"] == approx(8)
    assert f("p2", "m1")["evaluaciones"] == 1 and f("p2", "m1")["promedio"] == approx(7.5)
    assert f("p2", "m2")["promedio"] == approx(9)
    pp2 = next(x for x in d["porProfesor"] if x["id"] == ids["p2"])
    assert pp2["evaluaciones"] == 2 and pp2["promedio"] == approx((7.5 + 9) / 2)
    pm1 = next(x for x in d["porMateria"] if x["id"] == ids["m1"])
    assert pm1["evaluaciones"] == 3 and pm1["promedio"] == approx((10 + 6 + 7.5) / 3)
    assert len(d["porPregunta"]) == 12
    assert d["porPregunta"][0] == approx((10 + 6 + 5 + 9) / 4) and d["porPregunta"][1] == approx((10 + 6 + 6 + 9) / 4)
    assert len(d["detalle"]) == 4 and d["detalle"][0]["comentario"] == "Excelente"
    assert all(x["grupo"] == "GSI0252" and len(x["respuestas"]) == 12 for x in d["detalle"])
    assert isinstance(d["detalle"][0]["fecha"], str) and "T" in d["detalle"][0]["fecha"]

    r = A(f"/api/admin/reportes/general-grupo?grupo={ids['g1']}")
    assert r.status == 200 and r.datos["filtros"]["grupo"]["clave"] == "GSI0252"
    assert r.datos["resumen"]["promedio"] == approx(8.125)
    fila = next(x for x in r.datos["porProfesorMateria"] if x["profesor_id"] == ids["p2"] and x["materia_id"] == ids["m1"])
    assert fila["preguntas"] == [5, 6, 7, 8, 9, 10, 5, 6, 7, 8, 9, 10]

    d = A(f"/api/admin/reportes/profesor?profesor={ids['p2']}").datos
    assert d["resumen"]["evaluaciones"] == 3 and d["resumen"]["respuestas"] == 36
    assert d["resumen"]["promedio"] == approx((7.5 + 9 + 5) / 3)
    d = A(f"/api/admin/reportes/profesor?profesor={ids['p2']}&materia={ids['m1']}").datos
    assert d["resumen"]["evaluaciones"] == 2 and d["resumen"]["promedio"] == approx((7.5 + 5) / 2)
    d = A(f"/api/admin/reportes/profesor?profesor={ids['p2']}&grupo={ids['g2']}").datos
    assert d["resumen"]["evaluaciones"] == 1 and d["resumen"]["promedio"] == approx(5)
    d = A(f"/api/admin/reportes/profesor?profesor={ids['p2']}&grupo={ids['g2']}&materia={ids['m2']}").datos
    assert d["vacio"] is True and d["detalle"] == []

    d = A(f"/api/admin/reportes/grupo-profesor?grupo={ids['g1']}&profesor={ids['p2']}").datos
    assert d["resumen"]["evaluaciones"] == 2
    assert all(x["grupo"] == "GSI0252" and x["profesor"] == "Carlos Ramírez Soto" for x in d["detalle"])
    d = A(f"/api/admin/reportes/grupo-profesor?grupo={ids['g1']}&profesor={ids['p2']}&materia={ids['m2']}").datos
    assert d["resumen"]["evaluaciones"] == 1 and d["resumen"]["promedio"] == approx(9)
    assert all(x["materia"] == "Bases de Datos" for x in d["detalle"])

    assert A("/api/admin/reportes/grupo").status == 400
    assert A(f"/api/admin/reportes/grupo-profesor?grupo={ids['g1']}").status == 400
    assert A("/api/admin/reportes/profesor").status == 400
    assert A("/api/admin/reportes/grupo?grupo=abc").status == 400
    assert A("/api/admin/reportes/grupo?grupo=999999").status == 404
    assert A(f"/api/admin/reportes/grupo-profesor?grupo={ids['g1']}&profesor={ids['p1']}&materia={ids['m2']}").status == 400
    assert A("/api/admin/reportes/inventado?grupo=1").status == 404
    assert A("/api/admin/reportes/grupo?grupo=1%20OR%201=1").status == 400


def test_17_reportes_sin_registros_mensaje_vacio(sql):
    ejecutar(sql, "DELETE FROM evaluaciones WHERE grupo_id = %s", (ids["g2"],))
    for t in ("grupo", "general-grupo"):
        d = admin()("GET", f"/api/admin/reportes/{t}?grupo={ids['g2']}").datos
        assert d["vacio"] is True and d["resumen"]["evaluaciones"] == 0
        assert d["resumen"]["promedio"] is None and d["detalle"] == []


def test_18_eliminar_evaluacion_borra_respuestas_en_cascada(sql):
    e = ejecutar(sql, "SELECT id FROM evaluaciones LIMIT 1")[0]["id"]
    antes = contar(sql, "respuestas")
    assert admin()("DELETE", f"/api/admin/evaluaciones/{e}").status == 200
    assert contar(sql, "respuestas") == antes - 12
    assert admin()("DELETE", f"/api/admin/evaluaciones/{e}").status == 404
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
