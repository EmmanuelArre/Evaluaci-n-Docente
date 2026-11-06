"""Los 12 escenarios del filtrado profesor–grupo (ahora detrás de la contraseña del grupo), contra MySQL real.

Datos: 15 profesores en total. El grupo GTID234 recibe clase de exactamente 7 de ellos; GTID235 de otros 4
(uno compartido con GTID234); GTID236 no tiene ninguno. Ejecutar:  pytest tests/test_escenarios.py
"""
import bcrypt
import pytest

from app import config as cfgmod
from app import crear_app
from app import db as dbmod
from app import validar
from ayuda import cuerpo_encuesta, cuestionario, entrar, navegador_autorizado

PASS = "ClaveDePrueba123"
ids = {}
estado = {}


class Resp:
    def __init__(self, r):
        self.status = r.status_code
        self.datos = r.get_json(silent=True)


def cliente(app):
    c = app.test_client()

    def llamar(metodo, ruta, cuerpo=None):
        kw = {"method": metodo}
        if cuerpo is not None:
            kw["json"] = cuerpo
        return Resp(c.open(ruta, **kw))
    return llamar


@pytest.fixture(scope="module")
def sql():
    conn = dbmod.conectar(cfgmod.leer_config())
    yield conn
    conn.close()


def q(conn, sentencia, p=()):
    with conn.cursor() as cur:
        cur.execute(sentencia, p)
        return cur.fetchall()


def n(conn, tabla):
    return q(conn, f"SELECT COUNT(*) AS n FROM {tabla}")[0]["n"]


@pytest.fixture(scope="module", autouse=True)
def preparar(sql):
    q(sql, "SET FOREIGN_KEY_CHECKS = 0")
    for t in ["respuestas", "evaluaciones", "encuestas", "asignaciones", "profesor_materia", "profesores", "materias", "grupos",
              "administradores", "sesiones"]:
        q(sql, f"DELETE FROM {t}")
    q(sql, "SET FOREIGN_KEY_CHECKS = 1")
    q(sql, "INSERT INTO administradores (usuario, nombre, password_hash) VALUES (%s, %s, %s)",
      ("admin", "Admin Pruebas", bcrypt.hashpw(PASS.encode(), bcrypt.gensalt(rounds=6)).decode()))
    estado["app"] = crear_app()
    estado["admin"] = cliente(estado["app"])
    assert estado["admin"]("POST", "/api/admin/login", {"usuario": "admin", "password": PASS}).status == 200
    estado["alumno"] = cliente(estado["app"])


def admin():
    return estado["admin"]


def alumno():
    return estado["alumno"]


def R(v):
    return [v] * 12


NOMS = ["Alma", "Beto", "Carla", "Daniel", "Elena", "Fabián", "Gloria", "Hugo", "Irene", "Jorge", "Karla", "Luis", "Marta", "Nora", "Omar"]


def nom(i):
    return f"{NOMS[i]} Pruebas"


def test_00_datos_de_prueba():
    for clave in ("GTID234", "GTID235", "GTID236"):
        ids[clave] = admin()("POST", "/api/admin/grupos", {"clave": clave, "num_alumnos": 40, "clave_acceso": "Acc-" + clave}).datos["id"]
    mat = admin()("POST", "/api/admin/materias", {"nombre": "Materia Uno"}).datos["id"]
    mat2 = admin()("POST", "/api/admin/materias", {"nombre": "Materia Dos"}).datos["id"]
    ids["mat"], ids["mat2"] = mat, mat2
    # 15 profesores, todos con la misma materia (y los 3 primeros también con la segunda)
    ids["prof"] = []
    for i in range(15):
        pid = admin()("POST", "/api/admin/profesores", {"nombres": NOMS[i], "apellido_paterno": "Pruebas"}).datos["id"]
        ids["prof"].append(pid)
        assert admin()("POST", f"/api/admin/profesores/{pid}/materias", {"materia_id": mat}).status == 201
        if i < 3:
            assert admin()("POST", f"/api/admin/profesores/{pid}/materias", {"materia_id": mat2}).status == 201
    assert n(dbmod_conn(), "profesores") == 15
    P = ids["prof"]
    for i in range(7):                                    # GTID234 ← profesores 0..6
        assert admin()("POST", f"/api/admin/grupos/{ids['GTID234']}/asignaciones", {"profesor_id": P[i], "materia_id": mat}).status == 201
    for i in (6, 7, 8, 9):                                # GTID235 ← 6 (compartido), 7, 8, 9
        assert admin()("POST", f"/api/admin/grupos/{ids['GTID235']}/asignaciones", {"profesor_id": P[i], "materia_id": mat}).status == 201


def dbmod_conn():
    return estado.setdefault("conn", dbmod.conectar(cfgmod.leer_config()))


def tabla(clave):
    """Filas (una por asignación) que el servidor entrega a un alumno que escribió la contraseña del grupo."""
    c = navegador_autorizado(estado["app"], ids[clave], "Acc-" + clave)
    r = cuestionario(c, ids[clave])
    assert r.status == 200
    return [(f["profesor"], f["materia"]) for f in r.datos["asignaciones"]]


def nombres(clave):
    return [p for p, _ in tabla(clave)]


def test_01_grupo_con_7_profesores_muestra_exactamente_esos_7():
    esperado = sorted(nom(i) for i in range(7))
    assert nombres("GTID234") == esperado
    assert len(nombres("GTID234")) == 7


def test_02_profesores_de_otros_grupos_no_aparecen():
    ajenos = {nom(i) for i in range(7, 15)}
    assert not ajenos & set(nombres("GTID234"))


def test_03_cambiar_de_grupo_actualiza_la_lista():
    a, b = nombres("GTID234"), nombres("GTID235")
    assert len(b) == 4 and set(a) != set(b)
    assert set(nombres("GTID234")) == set(a)              # volver al grupo anterior da lo mismo
    # las materias también dependen del grupo: el profesor 1 solo da Materia Uno en GTID234
    assert [m for p, m in tabla("GTID234") if p == nom(1)] == ["Materia Uno"]


def test_04_grupo_sin_profesores_da_cero_resultados():
    assert nombres("GTID236") == []
    # y no se puede enviar una encuesta a un grupo sin profesores
    c = navegador_autorizado(estado["app"], ids["GTID236"], "Acc-GTID236")
    r = c("POST", "/api/encuestas", {"grupo_id": ids["GTID236"], "evaluaciones": [
        {"profesor_id": ids["prof"][0], "materia_id": ids["mat"], "respuestas": R(8)}]})
    assert r.status == 409


def test_05_profesor_en_varios_grupos_solo_aparece_en_los_suyos():
    p6 = nom(6)                                             # índice 6: GTID234 y GTID235
    assert p6 in nombres("GTID234") and p6 in nombres("GTID235") and p6 not in nombres("GTID236")
    p0 = nom(0)                                             # índice 0: solo GTID234
    assert p0 in nombres("GTID234") and p0 not in nombres("GTID235")


def test_06_no_se_puede_evaluar_a_un_profesor_ajeno_aunque_se_manipule_la_solicitud(sql):
    antes = (n(sql, "encuestas"), n(sql, "evaluaciones"), n(sql, "respuestas"))
    c = navegador_autorizado(estado["app"], ids["GTID234"], "Acc-GTID234")
    base = cuerpo_encuesta(c, ids["GTID234"])
    ajeno = ids["prof"][12]                                # no da clase a GTID234
    ev = lambda p, m: {"profesor_id": p, "materia_id": m, "respuestas": R(8)}
    for evaluaciones in (
        base["evaluaciones"] + [ev(ajeno, ids["mat"])],                                  # un profesor de otro grupo de más
        base["evaluaciones"][:-1] + [ev(ajeno, ids["mat"])],                              # uno cambiado por un ajeno
        # profesor del grupo pero con una materia que no le imparte a ese grupo
        base["evaluaciones"][1:] + [ev(ids["prof"][0], ids["mat2"])],
        base["evaluaciones"][:-1] + [ev(str(ajeno), ids["mat"])],
    ):
        r = c("POST", "/api/encuestas", {"grupo_id": ids["GTID234"], "evaluaciones": evaluaciones})
        assert r.status == 400 and r.datos["errores"], evaluaciones
    # enviar a OTRO grupo con la autorización de GTID234 tampoco funciona
    r = c("POST", "/api/encuestas", {"grupo_id": ids["GTID236"], "evaluaciones": [ev(ids["prof"][0], ids["mat"])]})
    assert r.status == 403
    assert (n(sql, "encuestas"), n(sql, "evaluaciones"), n(sql, "respuestas")) == antes


def test_07_sin_profesores_duplicados():
    # el mismo profesor con DOS materias en el mismo grupo aparece una sola vez
    assert admin()("POST", f"/api/admin/grupos/{ids['GTID234']}/asignaciones",
                   {"profesor_id": ids["prof"][0], "materia_id": ids["mat2"]}).status == 201
    filas = tabla("GTID234")
    assert len(filas) == len(set(filas)) == 8                       # una fila por ASIGNACIÓN: ninguna repetida
    assert len(set(nombres("GTID234"))) == 7                        # el profesor con dos materias aparece en dos filas
    assert [m for p, m in filas if p == nom(0)] == ["Materia Dos", "Materia Uno"]
    # y la misma asignación no puede registrarse dos veces
    assert admin()("POST", f"/api/admin/grupos/{ids['GTID234']}/asignaciones",
                   {"profesor_id": ids["prof"][0], "materia_id": ids["mat2"]}).status == 409


def test_08_nombres_se_normalizan_al_crear_y_editar():
    P = lambda n, a, m=None, **o: {"nombres": n, "apellido_paterno": a, "apellido_materno": m, **o}
    pid = admin()("POST", "/api/admin/profesores", P("  josé emmanuel   ", "ARREDONDO", " escalante ")).datos["id"]
    lista = {p["id"]: p["nombre"] for p in admin()("GET", "/api/admin/profesores").datos}
    assert lista[pid] == "José Emmanuel Arredondo Escalante"
    assert admin()("PUT", f"/api/admin/profesores/{pid}", P("MARÍA FERNANDA", "LÓPEZ", "GARCÍA", activo=True)).status == 200
    lista = {p["id"]: p["nombre"] for p in admin()("GET", "/api/admin/profesores").datos}
    assert lista[pid] == "María Fernanda López García"
    assert admin()("PUT", f"/api/admin/profesores/{pid}", P("juan carlos", "de la cruz", None, activo=True)).status == 200
    assert {p["id"]: p["nombre"] for p in admin()("GET", "/api/admin/profesores").datos}[pid] == "Juan Carlos De la Cruz"
    assert validar.normalizar_nombre("josé emmanuel arredondo escalante") == "José Emmanuel Arredondo Escalante"
    assert validar.normalizar_nombre("MARÍA FERNANDA LÓPEZ GARCÍA") == "María Fernanda López García"
    assert validar.normalizar_nombre("juan carlos de la cruz") == "Juan Carlos de la Cruz"
    # no toca identificadores: la clave de grupo sigue en mayúsculas y el usuario del admin no se altera
    assert admin()("GET", "/api/admin/me").datos["nombre"] == "Admin Pruebas"
    admin()("DELETE", f"/api/admin/profesores/{pid}")


def test_09_campos_obligatorios_vacios_dan_error_de_validacion(sql):
    antes = n(sql, "profesores")
    for nombres_ in ("", "     ", None, "\t\n", ".....", 12345):
        r = admin()("POST", "/api/admin/profesores", {"nombres": nombres_, "apellido_paterno": "Pérez"})
        assert r.status == 400 and "nombres" in r.datos["errores"], repr(nombres_)
    for ap in ("", "     ", None, 12345):
        r = admin()("POST", "/api/admin/profesores", {"nombres": "Ana", "apellido_paterno": ap})
        assert r.status == 400 and "apellido_paterno" in r.datos["errores"], repr(ap)
    assert admin()("POST", "/api/admin/profesores", {}).status == 400
    assert n(sql, "profesores") == antes
    assert admin()("POST", "/api/admin/grupos", {"clave": "   ", "num_alumnos": 3}).status == 400
    r = alumno()("POST", "/api/encuestas", {"grupo_id": None, "evaluaciones": None})
    assert r.status == 400 and {"grupo", "evaluaciones"} <= set(r.datos["errores"])


def test_10_encuesta_valida_se_guarda(sql):
    antes = (n(sql, "encuestas"), n(sql, "evaluaciones"), n(sql, "respuestas"))
    c = navegador_autorizado(estado["app"], ids["GTID235"], "Acc-GTID235")
    r = c("POST", "/api/encuestas", cuerpo_encuesta(c, ids["GTID235"], 9, "Bien"))
    assert r.status == 201
    assert (n(sql, "encuestas"), n(sql, "evaluaciones"), n(sql, "respuestas")) == (antes[0] + 1, antes[1] + 4, antes[2] + 48)
    evs = q(sql, "SELECT grupo_id, profesor_id, materia_id FROM evaluaciones WHERE encuesta_id = %s", (r.datos["id"],))
    assert {(e["grupo_id"], e["profesor_id"], e["materia_id"]) for e in evs} == {
        (ids["GTID235"], ids["prof"][i], ids["mat"]) for i in (6, 7, 8, 9)}


def test_11_encuestas_invalidas_se_rechazan_sin_tocar_datos(sql):
    antes = (n(sql, "encuestas"), n(sql, "evaluaciones"), n(sql, "respuestas"))
    c = navegador_autorizado(estado["app"], ids["GTID235"], "Acc-GTID235")
    base = cuerpo_encuesta(c, ids["GTID235"], 9)

    def con(**cambio):
        b = {"grupo_id": base["grupo_id"], "evaluaciones": [dict(e) for e in base["evaluaciones"]]}
        for k, v in cambio.items():
            if k in ("respuestas", "comentario", "profesor_id", "materia_id"):
                b["evaluaciones"][0][k] = v
            else:
                b[k] = v
        return b
    for cambio, esperado in (({"respuestas": R(4)}, 400), ({"respuestas": R(9)[:11]}, 400), ({"respuestas": [7.5] + R(9)[1:]}, 400),
                             ({"grupo_id": 999999}, 403), ({"profesor_id": 999999}, 400), ({"materia_id": 999999}, 400),
                             ({"comentario": "x" * 201}, 400)):
        assert c("POST", "/api/encuestas", con(**cambio)).status == esperado, cambio
    assert (n(sql, "encuestas"), n(sql, "evaluaciones"), n(sql, "respuestas")) == antes


def test_12_si_falla_la_consulta_no_se_devuelve_nada_de_otro_grupo(monkeypatch):
    # Simula una caída de la base: la API debe responder error y NO una lista (ni la de otro grupo ni "todos").
    app = estado["app"]
    original = dbmod.filas

    def rota(*a, **k):
        raise RuntimeError("base de datos caída")
    c = navegador_autorizado(app, ids["GTID234"], "Acc-GTID234")       # (la autorización se abre antes de simular la caída)
    monkeypatch.setattr(dbmod, "filas", rota)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = c.http.get(f"/api/grupos/{ids['GTID234']}/cuestionario")
    assert r.status_code == 500
    cuerpo = r.get_json()
    assert isinstance(cuerpo, dict) and "error" in cuerpo and not isinstance(cuerpo, list)
    monkeypatch.setattr(dbmod, "filas", original)
    assert len(set(nombres("GTID234"))) == 7                 # recuperada: vuelve a funcionar sin datos de reemplazo


def test_13_quitar_o_desactivar_una_asignacion_se_refleja_de_inmediato():
    gid, pid = ids["GTID234"], ids["prof"][5]
    ruta = f"/api/admin/grupos/{gid}/asignaciones/{pid}/{ids['mat']}"
    assert nom(5) in nombres("GTID234")
    assert admin()("PUT", ruta, {"activo": False}).status == 200
    assert nom(5) not in nombres("GTID234") and len(set(nombres("GTID234"))) == 6
    assert admin()("PUT", ruta, {"activo": True}).status == 200
    assert len(set(nombres("GTID234"))) == 7
    assert admin()("DELETE", ruta).status == 200            # sin evaluaciones: sí se puede quitar
    assert nom(5) not in nombres("GTID234")
    # un profesor desactivado deja de ofrecerse aunque conserve la asignación
    pid0 = ids["prof"][0]
    assert admin()("PUT", f"/api/admin/profesores/{pid0}", {"activo": False}).status == 200
    assert nom(0) not in nombres("GTID234")
    assert admin()("PUT", f"/api/admin/profesores/{pid0}", {"activo": True}).status == 200
    # el profesor sin grupos no aparece en ninguno
    sin_grupo = ids["prof"][14]
    ficha = next(p for p in admin()("GET", "/api/admin/profesores").datos if p["id"] == sin_grupo)
    assert ficha["grupos"] == []


def test_14_materias_usan_la_misma_normalizacion_y_validacion(sql):
    antes = n(sql, "materias")
    casos = {"  aplicaciones   WEB ": "Aplicaciones Web", "BASES DE DATOS": "Bases de Datos",
             "programación II": "Programación II", "inglés 2": "Inglés 2", "introducción A LA programación": "Introducción a la Programación"}
    creadas = {}
    for entrada, esperado in casos.items():
        r = admin()("POST", "/api/admin/materias", {"nombre": entrada})
        assert r.status == 201, entrada
        creadas[r.datos["id"]] = esperado
    lista = {m["id"]: m["nombre"] for m in admin()("GET", "/api/admin/materias").datos}
    assert all(lista[i] == e for i, e in creadas.items())
    # misma escritura con otro formato = duplicado
    assert admin()("POST", "/api/admin/materias", {"nombre": "APLICACIONES WEB"}).status == 409
    # al editar también se normaliza
    mid = next(iter(creadas))
    assert admin()("PUT", f"/api/admin/materias/{mid}", {"nombre": "sistemas OPERATIVOS", "activo": True}).status == 200
    assert {m["id"]: m["nombre"] for m in admin()("GET", "/api/admin/materias").datos}[mid] == "Sistemas Operativos"
    # vacíos e inválidos
    for malo in ("", "     ", None, "....", "12", "ab", "x" * 61, "<b>mal</b>", 123):
        assert admin()("POST", "/api/admin/materias", {"nombre": malo}).status == 400, repr(malo)
    assert n(sql, "materias") == antes + len(casos)


def test_15_profesor_requiere_nombre_y_apellido_paterno_y_materno_es_opcional(sql):
    P = lambda n, a, m=None, **o: {"nombres": n, "apellido_paterno": a, "apellido_materno": m, **o}
    # válido: José Emmanuel Arredondo, sin apellido materno (None, "" y omitido)
    for materno in (None, "", "   ", Ellipsis):
        cuerpo = P("José Emmanuel", "Arredondo", materno if materno is not Ellipsis else None)
        if materno is Ellipsis:
            cuerpo.pop("apellido_materno")
        r = admin()("POST", "/api/admin/profesores", cuerpo)
        assert r.status == 201, (materno, r.datos)
        fila = q(sql, "SELECT nombre, apellido_materno FROM profesores WHERE id = %s", (r.datos["id"],))[0]
        assert fila["nombre"] == "José Emmanuel Arredondo" and fila["apellido_materno"] is None
        admin()("DELETE", f"/api/admin/profesores/{r.datos['id']}")
    # válido: cinco nombres de pila y ambos apellidos; acentos, diéresis y ñ; guion
    ok = [P("Juan Luis Ángel María José", "Peña", "Güemes"), P("Ana-Karen", "Núñez-Ibáñez", "Muñoz"), P("Ñandú", "Cüeto")]
    for cuerpo in ok:
        r = admin()("POST", "/api/admin/profesores", cuerpo)
        assert r.status == 201, (cuerpo, r.datos)
        admin()("DELETE", f"/api/admin/profesores/{r.datos['id']}")
    # inválido
    malos = {"nombre vacío": P("", "Pérez"), "apellido paterno vacío": P("Ana", ""), "seis nombres": P("Ana Luis Pedro Rosa Juan Marta", "Pérez"),
             "números en el nombre": P("Ana2", "Pérez"), "números en el apellido": P("Ana", "Pérez3"), "símbolos": P("Ana", "Pé@rez"),
             "materno inválido si viene": P("Ana", "Pérez", "Gó_mez")}
    for caso, cuerpo in malos.items():
        r = admin()("POST", "/api/admin/profesores", cuerpo)
        assert r.status == 400, caso
    # editar un profesor sin apellido materno, y quitárselo a uno que lo tenía
    pid = admin()("POST", "/api/admin/profesores", P("Verónica", "Monzón", "Hernández")).datos["id"]
    assert admin()("PUT", f"/api/admin/profesores/{pid}", P("Verónica", "Monzón", None, activo=True)).status == 200
    ficha = next(p for p in admin()("GET", "/api/admin/profesores").datos if p["id"] == pid)
    assert ficha["nombre"] == "Verónica Monzón" and ficha["apellido_materno"] is None
    assert admin()("PUT", f"/api/admin/profesores/{pid}", P("Verónica", "", None, activo=True)).status == 400
    assert admin()("PUT", f"/api/admin/profesores/{pid}", {"nombre": "Verónica", "activo": True}).status == 400   # el formato anterior ya no basta
    assert admin()("DELETE", f"/api/admin/profesores/{pid}").status == 200
