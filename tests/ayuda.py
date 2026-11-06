"""Funciones comunes de las pruebas (clientes HTTP con cookies propias, flujo de acceso por contraseña y encuestas)."""


class Resp:
    def __init__(self, r):
        self.status = r.status_code
        self.datos = r.get_json(silent=True)
        self.headers = r.headers
        self.set_cookie = r.headers.getlist("Set-Cookie")
        self.texto = r.get_data(as_text=True)


def cliente(app):
    """Un 'navegador' con sus propias cookies: llamar(metodo, ruta, cuerpo=None, headers=None) → Resp."""
    c = app.test_client()

    def llamar(metodo, ruta, cuerpo=None, headers=None):
        kw = {"method": metodo, "headers": headers or {}}
        if cuerpo is not None:
            kw["json"] = cuerpo
        return Resp(c.open(ruta, **kw))
    llamar.http = c
    return llamar


def R(v):
    return [v] * 12


def entrar(c, gid, clave):
    return c("POST", f"/api/grupos/{gid}/acceso", {"clave": clave})


def cuestionario(c, gid):
    return c("GET", f"/api/grupos/{gid}/cuestionario")


def cuerpo_encuesta(c, gid, calif=8, comentario=None):
    """Arma el cuerpo de una encuesta COMPLETA a partir de la tabla que el servidor entrega a este navegador."""
    r = cuestionario(c, gid)
    assert r.status == 200, (r.status, r.datos)
    evs = []
    for a in r.datos["asignaciones"]:
        e = {"profesor_id": a["profesor_id"], "materia_id": a["materia_id"], "respuestas": R(calif)}
        if comentario is not None:
            e["comentario"] = comentario
        evs.append(e)
    return {"grupo_id": gid, "evaluaciones": evs}


def navegador_autorizado(app, gid, clave):
    """Navegador nuevo que ya escribió la contraseña correcta del grupo."""
    c = cliente(app)
    r = entrar(c, gid, clave)
    assert r.status == 200, (r.status, r.datos)
    return c
