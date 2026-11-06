"""Límite de encuestas por grupo (35 alumnos), concurrencia, anonimato y contraseña de acceso por grupo.
Ejecutar:  pytest tests/test_encuestas.py   (necesita MySQL y una base cuyo nombre termine en _test)"""
import json
import logging
import threading

import bcrypt
import pytest

from app import cifrado, crear_app
from app import config as cfgmod
from app import db as dbmod
from ayuda import R, cliente, cuerpo_encuesta, cuestionario, entrar, navegador_autorizado

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


def n(conn, tabla, donde="", p=()):
    return q(conn, f"SELECT COUNT(*) AS n FROM {tabla} {donde}", p)[0]["n"]


@pytest.fixture(scope="module", autouse=True)
def preparar(sql):
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
    A = est["admin"]
    ids["mat"] = A("POST", "/api/admin/materias", {"nombre": "Bases de Datos"}).datos["id"]
    ids["mat2"] = A("POST", "/api/admin/materias", {"nombre": "Redes"}).datos["id"]
    ids["prof"] = [A("POST", "/api/admin/profesores", {"nombres": nm, "apellido_paterno": "Prueba"}).datos["id"]
                   for nm in ("Ana", "Beto", "Carla")]
    for pid in ids["prof"]:
        A("POST", f"/api/admin/profesores/{pid}/materias", {"materia_id": ids["mat"]})
    yield


def reiniciar_limites():
    for k in ("limite_acceso_ip", "limite_acceso_grupo", "limite_envios"):
        est["app"].extensions[k].reiniciar()


def nuevo_grupo(clave, alumnos, acceso, asignar=3):
    A = est["admin"]
    cuerpo = {"clave": clave, "num_alumnos": alumnos}
    if acceso:
        cuerpo["clave_acceso"] = acceso
    r = A("POST", "/api/admin/grupos", cuerpo)
    assert r.status == 201, r.datos
    gid = r.datos["id"]
    for pid in ids["prof"][:asignar]:
        assert A("POST", f"/api/admin/grupos/{gid}/asignaciones", {"profesor_id": pid, "materia_id": ids["mat"]}).status == 201
    return gid


def enviar(gid, acceso, calif=8):
    c = navegador_autorizado(est["app"], gid, acceso)
    return c("POST", "/api/encuestas", cuerpo_encuesta(c, gid, calif))


# ───────────────────────── tabla, cuestionario y cambio de grupo ─────────────────────────
def test_01_tabla_numerada_y_preguntas_solo_tras_la_contraseña():
    reiniciar_limites()
    g1 = ids["g1"] = nuevo_grupo("GTID101", 35, "Clave-uno-1")
    g2 = ids["g2"] = nuevo_grupo("GTID102", 10, "Clave-dos-2", asignar=1)
    c = cliente(est["app"])
    assert cuestionario(c, g1).status == 403
    assert entrar(c, g1, "Clave-uno-1").status == 200
    d = cuestionario(c, g1).datos
    assert [(a["profesor"]) for a in d["asignaciones"]] == ["Ana Prueba", "Beto Prueba", "Carla Prueba"]
    assert len(d["preguntas"]) == 12 and d["disponibilidad"] == {"alumnos": 35, "encuestas": 0, "disponibles": 35}
    # al cambiar de grupo el servidor no entrega nada del anterior ni sin contraseña nueva
    assert cuestionario(c, g2).status == 403
    assert entrar(c, g2, "Clave-dos-2").status == 200
    assert len(cuestionario(c, g2).datos["asignaciones"]) == 1


def test_02_grupo_inexistente_o_manipulado():
    c = cliente(est["app"])
    assert entrar(c, 999999, "x").status == 404
    assert entrar(c, "1 OR 1=1", "x").status == 400
    assert c("GET", "/api/grupos/999999/cuestionario").status == 404


# ───────────────────────── calificaciones ─────────────────────────
def test_03_calificaciones_5_a_10_y_rechazo_de_invalidas(sql):
    g = ids["g1"]
    c = navegador_autorizado(est["app"], g, "Clave-uno-1")
    base = cuerpo_encuesta(c, g, 8)
    antes = n(sql, "encuestas")
    for malo in (4, 11, 7.5, "8", None, True, 0, -1, [8]):
        b = json.loads(json.dumps(base))
        b["evaluaciones"][0]["respuestas"][3] = malo
        r = c("POST", "/api/encuestas", b)
        assert r.status == 400, malo
    b = json.loads(json.dumps(base)); b["evaluaciones"][1]["respuestas"] = b["evaluaciones"][1]["respuestas"][:11]
    assert c("POST", "/api/encuestas", b).status == 400                                   # una pregunta sin contestar
    b = json.loads(json.dumps(base)); b["evaluaciones"].pop()
    assert c("POST", "/api/encuestas", b).status == 400                                   # falta un profesor
    assert n(sql, "encuestas") == antes                                                     # ninguno cuenta
    for v in (5, 10):                                                                        # los extremos válidos
        cc = navegador_autorizado(est["app"], g, "Clave-uno-1")
        assert cc("POST", "/api/encuestas", cuerpo_encuesta(cc, g, v)).status == 201


def test_04_una_encuesta_de_3_profesores_cuenta_una_vez(sql):
    g = ids["g2"]
    a = (n(sql, "encuestas", "WHERE grupo_id=%s", (g,)), n(sql, "evaluaciones", "WHERE grupo_id=%s", (g,)))
    c = navegador_autorizado(est["app"], ids["g1"], "Clave-uno-1")
    ant = (n(sql, "encuestas"), n(sql, "evaluaciones"), n(sql, "respuestas"))
    assert c("POST", "/api/encuestas", cuerpo_encuesta(c, ids["g1"], 9)).status == 201
    assert (n(sql, "encuestas"), n(sql, "evaluaciones"), n(sql, "respuestas")) == (ant[0] + 1, ant[1] + 3, ant[2] + 36)
    assert a == (0, 0)


# ───────────────────────── límite con 35 alumnos ─────────────────────────
def test_05_limite_35_alumnos_secuencial(sql):
    g = ids["g35"] = nuevo_grupo("GTID353", 35, "Clave-35-aaa")
    for i in range(34):
        assert enviar(g, "Clave-35-aaa").status == 201, i
    assert n(sql, "encuestas", "WHERE grupo_id=%s", (g,)) == 34
    c = navegador_autorizado(est["app"], g, "Clave-35-aaa")                    # 34: todavía hay 1 disponible
    d = cuestionario(c, g).datos
    assert d["disponibilidad"]["disponibles"] == 1
    assert c("POST", "/api/encuestas", cuerpo_encuesta(c, g)).status == 201     # la 35.ª entra
    r = enviar_o_acceso = entrar(cliente(est["app"]), g, "Clave-35-aaa")        # la 36.ª: con la contraseña CORRECTA no pasa
    assert r.status == 409 and "límite" in r.datos["error"].lower()
    assert n(sql, "encuestas", "WHERE grupo_id=%s", (g,)) == 35


def test_06_autorizacion_abierta_antes_del_limite_tampoco_lo_supera(sql):
    g = nuevo_grupo("GTID002", 1, "Clave-uno-solo")
    a = navegador_autorizado(est["app"], g, "Clave-uno-solo")
    b = navegador_autorizado(est["app"], g, "Clave-uno-solo")                    # ambos entraron cuando había lugar
    cuerpo = cuerpo_encuesta(a, g)
    assert a("POST", "/api/encuestas", cuerpo).status == 201
    r = b("POST", "/api/encuestas", cuerpo)
    assert r.status == 409 and n(sql, "encuestas", "WHERE grupo_id=%s", (g,)) == 1


def test_07_concurrencia_ultimo_lugar(sql):
    g = nuevo_grupo("GTID003", 5, "Clave-concurr")
    for _ in range(4):
        assert enviar(g, "Clave-concurr").status == 201
    clientes = [navegador_autorizado(est["app"], g, "Clave-concurr") for _ in range(8)]
    cuerpos = [cuerpo_encuesta(c, g) for c in clientes]
    codigos, barrera = [], threading.Barrier(8)

    def hilo(c, b):
        barrera.wait()
        codigos.append(c("POST", "/api/encuestas", b).status)
    hs = [threading.Thread(target=hilo, args=(c, b)) for c, b in zip(clientes, cuerpos)]
    [h.start() for h in hs]; [h.join() for h in hs]
    assert sorted(codigos).count(201) == 1, codigos            # exactamente UNA ocupa el último lugar
    assert all(x in (201, 409, 503) for x in codigos)
    assert n(sql, "encuestas", "WHERE grupo_id=%s", (g,)) == 5  # nunca 6


def test_08_grupo_con_cero_alumnos_no_recibe_encuestas(sql):
    g = nuevo_grupo("GTID004", 1, "Clave-cero-00")
    c = navegador_autorizado(est["app"], g, "Clave-cero-00")
    q(sql, "UPDATE grupos SET num_alumnos = 0 WHERE id = %s", (g,))             # (el panel no permite 0; así queda un grupo migrado)
    assert entrar(cliente(est["app"]), g, "Clave-cero-00").status == 409
    assert cuestionario(c, g).status == 409
    assert c("POST", "/api/encuestas", cuerpo_encuesta.__call__(c, g) if False else {"grupo_id": g, "evaluaciones": [
        {"profesor_id": ids["prof"][0], "materia_id": ids["mat"], "respuestas": R(8)}]}).status in (400, 409)
    assert n(sql, "encuestas", "WHERE grupo_id=%s", (g,)) == 0


def test_09_inconsistencia_mas_encuestas_que_alumnos_bloquea(sql):
    g = nuevo_grupo("GTID005", 3, "Clave-incons-")
    for _ in range(3):
        assert enviar(g, "Clave-incons-").status == 201
    q(sql, "UPDATE grupos SET num_alumnos = 2 WHERE id = %s", (g,))             # forzado fuera de la aplicación
    r = entrar(cliente(est["app"]), g, "Clave-incons-")
    assert r.status == 409 and "inconsistencia" in r.datos["error"].lower()
    fila = next(x for x in est["admin"]("GET", "/api/admin/grupos").datos if x["id"] == g)
    assert fila["disponibles"] == 0 and fila["inconsistente"] is True           # nunca negativo


def test_10_reducir_alumnos_por_debajo_de_las_encuestas_da_409(sql):
    g = nuevo_grupo("GTID006", 10, "Clave-reduc-0")
    for _ in range(4):
        enviar(g, "Clave-reduc-0")
    A = est["admin"]
    r = A("PUT", f"/api/admin/grupos/{g}", {"clave": "GTID006", "num_alumnos": 3, "activo": True})
    assert r.status == 409 and "4" in r.datos["error"]
    assert n(sql, "encuestas", "WHERE grupo_id=%s", (g,)) == 4                  # nada se borró
    assert A("PUT", f"/api/admin/grupos/{g}", {"clave": "GTID006", "num_alumnos": 4, "activo": True}).status == 200


def test_11_validacion_de_grupos():
    A = est["admin"]
    assert A("POST", "/api/admin/grupos", {"clave": "GTID353", "num_alumnos": 5}).status == 409           # clave duplicada
    for malo in (0, -3, 2.5, "abc", None, True, 501, ""):
        assert A("POST", "/api/admin/grupos", {"clave": "GTID999", "num_alumnos": malo}).status == 400, malo
    for clave in ("gti", "ABC1234", "GTI12", "GTI12345", "", "  "):
        assert A("POST", "/api/admin/grupos", {"clave": clave, "num_alumnos": 5}).status == 400, clave
    assert A("POST", "/api/admin/grupos", {"clave": "gtid777", "num_alumnos": "12"}).status == 201       # normaliza y acepta dígitos


# ───────────────────────── anonimato ─────────────────────────
def test_12_anonimato(sql):
    prohibidas = ("nombre", "matricula", "correo", "email", "ip", "usuario", "alumno", "token", "user_agent", "sesion", "cookie")
    for tabla in ("encuestas", "evaluaciones", "respuestas"):
        cols = [r["COLUMN_NAME"].lower() for r in q(sql, "SELECT COLUMN_NAME FROM information_schema.columns "
                                                   "WHERE table_schema = DATABASE() AND table_name = %s", (tabla,))]
        assert not [c for c in cols if any(p == c or c.startswith(p + "_") for p in prohibidas)], (tabla, cols)
    assert sorted(r["COLUMN_NAME"] for r in q(sql, "SELECT COLUMN_NAME FROM information_schema.columns "
                                                  "WHERE table_schema = DATABASE() AND table_name = 'encuestas'")) == ["creado_en", "grupo_id", "id"]
    # la fila de autorización no guarda quién es el alumno, y se borra al enviar
    c = navegador_autorizado(est["app"], ids["g1"], "Clave-uno-1")
    datos = [r["data"] for r in q(sql, "SELECT data FROM sesiones WHERE data LIKE %s", ('%"grupo"%',))]
    assert datos and all(set(json.loads(d)) == {"acceso"} and set(json.loads(d)["acceso"]) == {"grupo", "version"} for d in datos)
    assert c("POST", "/api/encuestas", cuerpo_encuesta(c, ids["g1"])).status == 201


# ───────────────────────── contraseñas ─────────────────────────
def test_20_admin_asigna_consulta_y_modifica_contrasena(sql):
    A = est["admin"]
    g = nuevo_grupo("GTID200", 20, None)
    assert next(x for x in A("GET", "/api/admin/grupos").datos if x["id"] == g)["tiene_clave"] is False
    assert entrar(cliente(est["app"]), g, "cualquiera").status == 409          # sin contraseña: acceso no disponible
    assert A("PUT", f"/api/admin/grupos/{g}/acceso", {"clave_acceso": "Primera-clave"}).status == 200
    fila = next(x for x in A("GET", "/api/admin/grupos").datos if x["id"] == g)
    assert fila["clave_acceso"] == "Primera-clave"                              # visible de forma permanente
    abierto = navegador_autorizado(est["app"], g, "Primera-clave")
    assert A("PUT", f"/api/admin/grupos/{g}/acceso", {"clave_acceso": "Segunda-clave"}).status == 200
    assert next(x for x in A("GET", "/api/admin/grupos").datos if x["id"] == g)["clave_acceso"] == "Segunda-clave"
    reiniciar_limites()
    assert entrar(cliente(est["app"]), g, "Primera-clave").status == 401        # la anterior deja de servir
    assert entrar(cliente(est["app"]), g, "Segunda-clave").status == 200
    assert cuestionario(abierto, g).status == 403                                # y la autorización ya abierta se revoca
    assert abierto("POST", "/api/encuestas", {"grupo_id": g, "evaluaciones": [
        {"profesor_id": ids["prof"][0], "materia_id": ids["mat"], "respuestas": R(8)}]}).status == 403
    ids["g_pw"] = g


def test_21_contrasena_de_otro_grupo_y_unicidad():
    A = est["admin"]
    reiniciar_limites()
    assert entrar(cliente(est["app"]), ids["g_pw"], "Clave-uno-1").status == 401          # la de GTID101 no abre GTID200
    assert A("PUT", f"/api/admin/grupos/{ids['g_pw']}/acceso", {"clave_acceso": "Clave-uno-1"}).status == 409
    assert A("PUT", f"/api/admin/grupos/{ids['g_pw']}/acceso", {"clave_acceso": ""}).status == 400
    assert A("PUT", f"/api/admin/grupos/{ids['g_pw']}/acceso", {"clave_acceso": "  "}).status == 400
    assert A("PUT", f"/api/admin/grupos/{ids['g_pw']}/acceso", {"clave_acceso": "con espacio"}).status == 400
    assert A("PUT", f"/api/admin/grupos/{ids['g_pw']}/acceso", {"clave_acceso": "abc"}).status == 400
    assert next(x for x in A("GET", "/api/admin/grupos").datos if x["clave"] == "GTID101")["clave_acceso"] == "Clave-uno-1"   # el otro no cambió


def test_22_sin_sesion_admin_no_hay_contrasenas():
    anon = cliente(est["app"])
    for m, u, b in (("GET", "/api/admin/grupos", None), ("PUT", f"/api/admin/grupos/{ids['g1']}/acceso", {"clave_acceso": "Hackeada-1"}),
                    ("PUT", f"/api/admin/grupos/{ids['g1']}", {"clave": "GTID101", "clave_acceso": "Hackeada-1"})):
        r = anon(m, u, b)
        assert r.status == 401 and "Clave-uno-1" not in r.texto and "clave_acceso" not in r.texto
    # un alumno autorizado tampoco es administrador
    alu = navegador_autorizado(est["app"], ids["g1"], "Clave-uno-1")
    assert alu("GET", "/api/admin/grupos").status == 401
    assert next(x for x in est["admin"]("GET", "/api/admin/grupos").datos if x["clave"] == "GTID101")["clave_acceso"] == "Clave-uno-1"


def test_23_guardar_sin_acceso_da_403(sql):
    g = ids["g1"]
    ant = n(sql, "encuestas")
    base = cuerpo_encuesta(navegador_autorizado(est["app"], g, "Clave-uno-1"), g)
    assert cliente(est["app"])("POST", "/api/encuestas", base).status == 403                 # llamada directa, sin contraseña
    otro = navegador_autorizado(est["app"], ids["g2"], "Clave-dos-2")                          # autorizado, pero para OTRO grupo
    assert otro("POST", "/api/encuestas", base).status == 403
    falso = cliente(est["app"])
    falso.http.set_cookie("ed.acc", "token-inventado-123")
    assert falso("POST", "/api/encuestas", base).status == 403
    assert n(sql, "encuestas") == ant


def test_24_la_autorizacion_se_consume_al_enviar():
    g = ids["g1"]
    c = navegador_autorizado(est["app"], g, "Clave-uno-1")
    cuerpo = cuerpo_encuesta(c, g)
    assert c("POST", "/api/encuestas", cuerpo).status == 201
    assert c("POST", "/api/encuestas", cuerpo).status == 403            # reenviar (doble clic / replay) no cuenta otra vez


def test_25_fuerza_bruta_429_y_el_acierto_no_pasa_mientras_dure():
    reiniciar_limites()
    g = ids["g1"]
    c = cliente(est["app"])
    codigos = [entrar(c, g, f"intento-{i}").status for i in range(10)]
    assert codigos[:8] == [401] * 8 and 429 in codigos[8:]
    assert entrar(c, g, "Clave-uno-1").status == 429                       # ni la correcta mientras esté bloqueado
    reiniciar_limites()


def test_26_la_contrasena_no_se_filtra(sql, caplog):
    reiniciar_limites()
    secretos = ["Clave-uno-1", "Clave-dos-2", "Segunda-clave"]
    caplog.set_level(logging.DEBUG)
    c = cliente(est["app"])
    r1 = entrar(c, ids["g1"], "Clave-uno-1")
    r2 = entrar(cliente(est["app"]), ids["g1"], "Equivocada-99")
    pub = [r1, r2, cuestionario(c, ids["g1"]), c("GET", "/api/grupos")]
    # cookie: httpOnly, SameSite, sin la contraseña
    ck = [x for x in r1.set_cookie if x.startswith("ed.acc=")][0]
    assert "HttpOnly" in ck and "SameSite=Strict" in ck and "Clave-uno-1" not in ck
    for r in pub:
        assert not any(s in r.texto for s in secretos)
    # reportes
    for tipo, f in (("grupo", {"grupo": ids["g1"]}), ("general-grupo", {"grupo": ids["g1"]})):
        r = est["admin"]("GET", f"/api/admin/reportes/{tipo}?" + "&".join(f"{k}={v}" for k, v in f.items()))
        assert r.status == 200 and not any(s in r.texto for s in secretos) and "clave_acceso" not in r.texto
    # logs
    assert not any(s in caplog.text for s in secretos)
    # en la base solo hay texto cifrado y sesiones sin contraseña
    for fila in q(sql, "SELECT acceso_cifrado FROM grupos WHERE acceso_cifrado IS NOT NULL"):
        assert not any(s in fila["acceso_cifrado"] for s in secretos) and fila["acceso_cifrado"].startswith("gAAAA")
    with est["app"].app_context():
        assert cifrado.descifrar(q(sql, "SELECT acceso_cifrado FROM grupos WHERE id = %s", (ids["g1"],))[0]["acceso_cifrado"]) == "Clave-uno-1"
    assert not q(sql, "SELECT 1 FROM sesiones WHERE data LIKE %s", ("%Clave-uno-1%",))


def test_27_reportes_distinguen_encuestas_evaluaciones_y_respuestas(sql):
    r = est["admin"]("GET", f"/api/admin/reportes/grupo?grupo={ids['g1']}")
    assert r.status == 200
    enc = n(sql, "encuestas", "WHERE grupo_id=%s", (ids["g1"],))
    ev = n(sql, "evaluaciones", "WHERE grupo_id=%s", (ids["g1"],))
    assert r.datos["resumen"]["encuestas"] == enc and r.datos["resumen"]["evaluaciones"] == ev and ev == enc * 3
