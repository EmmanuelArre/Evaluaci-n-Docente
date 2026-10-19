"use strict";
// Pantalla del administrador: inicio de sesión y gestión de grupos, profesores y materias.
// Las reglas de acceso las impone el servidor; aquí solo se arma la interfaz.

const reGrupo = /^[A-Za-z]{4}\d{3}$/;
const reNombreProfesor = /^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s.]+$/;
const colapsar = s => s.replace(/\s+/g, " ").trim();

let listaMaterias = [];     // para el combo de asignación
let profesorAsignando = null;
let turnoProfesores = 0;    // descarta respuestas viejas si se pidieron dos recargas seguidas

// Recarga materias y luego profesores (una sola pasada, en orden) para que ambas tablas y el combo de asignación coincidan
async function recargarCatalogos() { await cargarMaterias(); await cargarProfesores(); }

// ---------- utilidades de interfaz ----------
function el(tag, texto, clase) {
  const e = document.createElement(tag);
  if (texto !== undefined) e.textContent = texto;
  if (clase) e.className = clase;
  return e;
}
function celda(tr, contenido, clase) {
  const td = el("td", typeof contenido === "string" || typeof contenido === "number" ? String(contenido) : undefined, clase);
  if (contenido instanceof Node) td.appendChild(contenido);
  tr.appendChild(td);
  return td;
}
function boton(texto, fn, clase) {
  const b = el("button", texto, clase || "secundario chico");
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
}
function etiquetaEstado(activo) {
  return el("span", activo ? "Activo" : "Inactivo", activo ? "estado ok" : "estado off");
}
function setErr(id, msg) {
  $("e-" + id).textContent = msg || "";
  const campo = $(id);
  if (campo) campo.classList.toggle("invalido", !!msg);
  return !msg;
}
let temporizador;
function avisar(msg) {
  const a = $("avisoPanel");
  a.textContent = "✔ " + msg; a.hidden = false;
  clearTimeout(temporizador);
  temporizador = setTimeout(() => a.hidden = true, 4000);
}
function errorPanel(msg) { $("errorPanel").textContent = msg || ""; }

// Si la sesión caducó, vuelve a la pantalla de acceso
function sesionCaducada(r) {
  if (r.status === 401) { mostrarLogin("Tu sesión expiró. Inicia sesión de nuevo."); return true; }
  return false;
}
// Ejecuta una acción de escritura y refresca; devuelve true si salió bien
async function ejecutar(metodo, url, cuerpo, mensajeOk, recargar) {
  errorPanel("");
  const r = await api(metodo, url, cuerpo);
  if (sesionCaducada(r)) return { ok: false };
  if (!r.ok) { errorPanel(r.error); return r; }
  if (mensajeOk) avisar(mensajeOk);
  if (recargar) await recargar();
  return r;
}

// ---------- sesión ----------
function mostrarLogin(mensaje) {
  $("vistaPanel").hidden = true;
  $("vistaLogin").hidden = false;
  ["navPanel", "navReportes", "btnSalir"].forEach(i => $(i).hidden = true);
  $("quien").textContent = "";
  $("e-login").textContent = mensaje || "";
  $("password").value = "";
  $("usuario").focus();
}
function mostrarPanel(admin) {
  $("vistaLogin").hidden = true;
  $("vistaPanel").hidden = false;
  ["navPanel", "navReportes", "btnSalir"].forEach(i => $(i).hidden = false);
  $("quien").textContent = "👤 " + admin.nombre;
  cargarGrupos(); recargarCatalogos();
}

$("formLogin").addEventListener("submit", async e => {
  e.preventDefault();
  const usuario = $("usuario").value.trim(), password = $("password").value;
  let ok = true;
  ok = setErr("usuario", !usuario ? "Escribe tu usuario." : usuario.length < 3 ? "Mínimo 3 caracteres." : "") && ok;
  ok = setErr("password", !password ? "Escribe tu contraseña." : "") && ok;
  $("e-login").textContent = "";
  if (!ok) return;
  $("btnLogin").disabled = true;
  const r = await api("POST", "/api/admin/login", { usuario, password });
  $("btnLogin").disabled = false;
  if (!r.ok) { $("e-login").textContent = r.error; $("password").value = ""; return; }
  $("password").value = "";
  mostrarPanel(r.datos);
});
$("btnSalir").addEventListener("click", cerrarSesion);

// ---------- pestañas ----------
document.querySelectorAll(".pestana").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll(".pestana").forEach(x => x.classList.toggle("activa", x === b));
  document.querySelectorAll(".panel-tab").forEach(s => s.hidden = s.id !== "tab-" + b.dataset.tab);
  errorPanel("");
}));

// =====================================================================
// GRUPOS
// =====================================================================
async function cargarGrupos() {
  const r = await api("GET", "/api/admin/grupos");
  if (sesionCaducada(r)) return;
  if (!r.ok) return errorPanel(r.error);
  const tb = $("tablaGrupos").tBodies[0]; tb.innerHTML = "";
  if (!r.datos.length) {
    const tr = el("tr"); const td = celda(tr, "Aún no hay grupos registrados.", "vacio"); td.colSpan = 5; tb.appendChild(tr);
  }
  r.datos.forEach(g => {
    const tr = el("tr");
    celda(tr, g.clave); celda(tr, g.descripcion || "–"); celda(tr, etiquetaEstado(g.activo)); celda(tr, g.evaluaciones);
    const acc = el("div", undefined, "acciones");
    acc.append(
      boton("Editar", () => editarGrupo(g)),
      boton(g.activo ? "Desactivar" : "Activar", () => ejecutar("PUT", `/api/admin/grupos/${g.id}`,
        { clave: g.clave, descripcion: g.descripcion, activo: !g.activo }, g.activo ? "Grupo desactivado." : "Grupo activado.", cargarGrupos)),
      boton("Eliminar", async () => {
        if (!confirm(`¿Eliminar el grupo ${g.clave}? Esta acción no se puede deshacer.`)) return;
        await ejecutar("DELETE", `/api/admin/grupos/${g.id}`, undefined, "Grupo eliminado.", cargarGrupos);
      }, "peligro chico"));
    celda(tr, acc);
    tb.appendChild(tr);
  });
}
function resetGrupo() {
  $("g-id").value = ""; $("g-clave").value = ""; $("g-desc").value = ""; $("g-activo").checked = true;
  $("tit-grupo").textContent = "Nuevo grupo"; $("g-cancelar").hidden = true;
  setErr("g-clave"); setErr("g-desc");
}
function editarGrupo(g) {
  $("g-id").value = g.id; $("g-clave").value = g.clave; $("g-desc").value = g.descripcion || ""; $("g-activo").checked = !!g.activo;
  $("tit-grupo").textContent = "Editar grupo " + g.clave; $("g-cancelar").hidden = false;
  $("g-clave").focus(); window.scrollTo({ top: 0, behavior: "smooth" });
}
$("g-clave").addEventListener("input", e => { e.target.value = e.target.value.toUpperCase(); });
$("g-cancelar").addEventListener("click", resetGrupo);
$("formGrupo").addEventListener("submit", async e => {
  e.preventDefault();
  const clave = $("g-clave").value.trim().toUpperCase(), desc = colapsar($("g-desc").value);
  let ok = true;
  ok = setErr("g-clave", !clave ? "La clave es obligatoria." : !reGrupo.test(clave) ? "Formato: 4 letras y 3 dígitos (ej. GTID244)." : "") && ok;
  ok = setErr("g-desc", desc.length > 100 ? "Máximo 100 caracteres." : "") && ok;
  if (!ok) return;
  const id = $("g-id").value;
  const cuerpo = { clave, descripcion: desc || null, activo: $("g-activo").checked };
  const r = await ejecutar(id ? "PUT" : "POST", id ? `/api/admin/grupos/${id}` : "/api/admin/grupos", cuerpo,
    id ? "Grupo actualizado." : "Grupo creado.");
  if (r.ok) { resetGrupo(); await cargarGrupos(); }   // primero se limpia el formulario, luego se recarga la tabla
  else if (r.errores) { if (r.errores.clave) setErr("g-clave", r.errores.clave); if (r.errores.descripcion) setErr("g-desc", r.errores.descripcion); }
});

// =====================================================================
// PROFESORES
// =====================================================================
async function cargarProfesores() {
  const turno = ++turnoProfesores;
  const r = await api("GET", "/api/admin/profesores");
  if (turno !== turnoProfesores) return; // llegó una recarga más reciente
  if (sesionCaducada(r)) return;
  if (!r.ok) return errorPanel(r.error);
  const tb = $("tablaProfesores").tBodies[0]; tb.innerHTML = "";
  if (!r.datos.length) {
    const tr = el("tr"); const td = celda(tr, "Aún no hay profesores registrados.", "vacio"); td.colSpan = 5; tb.appendChild(tr);
  }
  r.datos.forEach(p => {
    const tr = el("tr");
    celda(tr, p.nombre);
    celda(tr, p.materias.length ? p.materias.map(m => m.nombre + (m.activo ? "" : " (inactiva)")).join(", ") : "Sin materias");
    celda(tr, etiquetaEstado(p.activo)); celda(tr, p.evaluaciones);
    const acc = el("div", undefined, "acciones");
    acc.append(
      boton("Editar", () => editarProfesor(p)),
      boton("Materias", () => abrirAsignacion(p)),
      boton(p.activo ? "Desactivar" : "Activar", () => ejecutar("PUT", `/api/admin/profesores/${p.id}`,
        { nombre: p.nombre, activo: !p.activo }, p.activo ? "Profesor desactivado." : "Profesor activado.", recargarCatalogos)),
      boton("Eliminar", async () => {
        if (!confirm(`¿Eliminar al profesor ${p.nombre}? Solo es posible si no tiene evaluaciones; de lo contrario desactívalo.`)) return;
        const r2 = await ejecutar("DELETE", `/api/admin/profesores/${p.id}`, undefined, "Profesor eliminado.", recargarCatalogos);
        if (r2.ok && profesorAsignando === p.id) $("cajaAsignar").hidden = true;
      }, "peligro chico"));
    celda(tr, acc);
    tb.appendChild(tr);
  });
  if (profesorAsignando) {
    const p = r.datos.find(x => x.id === profesorAsignando);
    if (p) pintarAsignadas(p); else { profesorAsignando = null; $("cajaAsignar").hidden = true; }
  }
}
function resetProfesor() {
  $("p-id").value = ""; $("p-nombre").value = ""; $("p-activo").checked = true;
  $("tit-profesor").textContent = "Nuevo profesor"; $("p-cancelar").hidden = true; setErr("p-nombre");
}
function editarProfesor(p) {
  $("p-id").value = p.id; $("p-nombre").value = p.nombre; $("p-activo").checked = !!p.activo;
  $("tit-profesor").textContent = "Editar profesor"; $("p-cancelar").hidden = false;
  $("p-nombre").focus(); window.scrollTo({ top: 0, behavior: "smooth" });
}
$("p-cancelar").addEventListener("click", resetProfesor);
$("formProfesor").addEventListener("submit", async e => {
  e.preventDefault();
  const nombre = colapsar($("p-nombre").value);
  const msg = !nombre ? "El profesor es obligatorio." : nombre.length < 5 ? "Mínimo 5 caracteres." :
    nombre.length > 60 ? "Máximo 60 caracteres." : !reNombreProfesor.test(nombre) ? "Solo letras y espacios." : "";
  if (!setErr("p-nombre", msg)) return;
  const id = $("p-id").value;
  const r = await ejecutar(id ? "PUT" : "POST", id ? `/api/admin/profesores/${id}` : "/api/admin/profesores",
    { nombre, activo: $("p-activo").checked }, id ? "Profesor actualizado." : "Profesor registrado.");
  if (r.ok) { resetProfesor(); await recargarCatalogos(); }
  else if (r.errores && r.errores.nombre) setErr("p-nombre", r.errores.nombre);
});

// ---- Asignación de materias a un profesor ----
function abrirAsignacion(p) {
  profesorAsignando = p.id;
  $("cajaAsignar").hidden = false;
  pintarAsignadas(p);
  $("cajaAsignar").scrollIntoView({ behavior: "smooth", block: "center" });
}
function pintarAsignadas(p) {
  $("tit-asignar").textContent = "Materias de " + p.nombre;
  const asignadas = new Set(p.materias.map(m => m.id));
  const libres = listaMaterias.filter(m => !asignadas.has(m.id));
  const previo = $("a-materia").value;      // se conserva lo que el administrador ya eligió
  llenarSelect($("a-materia"), libres, libres.length ? "Selecciona una materia" : "No hay más materias para asignar",
    m => m.nombre + (m.activo ? "" : " (inactiva)"));
  if (previo && libres.some(m => String(m.id) === previo)) $("a-materia").value = previo;
  setErr("a-materia");
  const ul = $("listaAsignadas"); ul.innerHTML = "";
  if (!p.materias.length) ul.appendChild(el("li", "Este profesor aún no tiene materias asignadas.", "vacio"));
  p.materias.forEach(m => {
    const li = el("li");
    li.appendChild(el("span", m.nombre + (m.activo ? "" : " (inactiva)")));
    li.appendChild(boton("Quitar", async () => {
      if (!confirm(`¿Quitar "${m.nombre}" a ${p.nombre}?`)) return;
      await ejecutar("DELETE", `/api/admin/profesores/${p.id}/materias/${m.id}`, undefined, "Materia quitada.", recargarCatalogos);
    }, "peligro chico"));
    ul.appendChild(li);
  });
}
$("a-cerrar").addEventListener("click", () => { profesorAsignando = null; $("cajaAsignar").hidden = true; });
$("formAsignar").addEventListener("submit", async e => {
  e.preventDefault();
  const materiaId = Number($("a-materia").value);
  if (!setErr("a-materia", materiaId ? "" : "Selecciona una materia.")) return;
  await ejecutar("POST", `/api/admin/profesores/${profesorAsignando}/materias`, { materia_id: materiaId }, "Materia asignada.",
    recargarCatalogos);
});

// =====================================================================
// MATERIAS
// =====================================================================
async function cargarMaterias() {
  const r = await api("GET", "/api/admin/materias");
  if (sesionCaducada(r)) return;
  if (!r.ok) return errorPanel(r.error);
  listaMaterias = r.datos;
  const tb = $("tablaMaterias").tBodies[0]; tb.innerHTML = "";
  if (!r.datos.length) {
    const tr = el("tr"); const td = celda(tr, "Aún no hay materias registradas.", "vacio"); td.colSpan = 5; tb.appendChild(tr);
  }
  r.datos.forEach(m => {
    const tr = el("tr");
    celda(tr, m.nombre);
    celda(tr, m.profesores.length ? m.profesores.map(p => p.nombre).join(", ") : "Sin profesores");
    celda(tr, etiquetaEstado(m.activo)); celda(tr, m.evaluaciones);
    const acc = el("div", undefined, "acciones");
    acc.append(
      boton("Editar", () => editarMateria(m)),
      boton(m.activo ? "Desactivar" : "Activar", () => ejecutar("PUT", `/api/admin/materias/${m.id}`,
        { nombre: m.nombre, activo: !m.activo }, m.activo ? "Materia desactivada." : "Materia activada.", recargarCatalogos)),
      boton("Eliminar", async () => {
        if (!confirm(`¿Eliminar la materia "${m.nombre}"? Solo es posible si no tiene evaluaciones; de lo contrario desactívala.`)) return;
        await ejecutar("DELETE", `/api/admin/materias/${m.id}`, undefined, "Materia eliminada.", recargarCatalogos);
      }, "peligro chico"));
    celda(tr, acc);
    tb.appendChild(tr);
  });
}
function resetMateria() {
  $("m-id").value = ""; $("m-nombre").value = ""; $("m-activo").checked = true;
  $("tit-materia").textContent = "Nueva materia"; $("m-cancelar").hidden = true; setErr("m-nombre");
}
function editarMateria(m) {
  $("m-id").value = m.id; $("m-nombre").value = m.nombre; $("m-activo").checked = !!m.activo;
  $("tit-materia").textContent = "Editar materia"; $("m-cancelar").hidden = false;
  $("m-nombre").focus(); window.scrollTo({ top: 0, behavior: "smooth" });
}
$("m-cancelar").addEventListener("click", resetMateria);
$("formMateria").addEventListener("submit", async e => {
  e.preventDefault();
  const nombre = colapsar($("m-nombre").value);
  const msg = !nombre ? "La materia es obligatoria." : nombre.length < 3 ? "Mínimo 3 caracteres." : nombre.length > 60 ? "Máximo 60 caracteres." : "";
  if (!setErr("m-nombre", msg)) return;
  const id = $("m-id").value;
  const r = await ejecutar(id ? "PUT" : "POST", id ? `/api/admin/materias/${id}` : "/api/admin/materias",
    { nombre, activo: $("m-activo").checked }, id ? "Materia actualizada." : "Materia registrada.");
  if (r.ok) { resetMateria(); await recargarCatalogos(); }
  else if (r.errores && r.errores.nombre) setErr("m-nombre", r.errores.nombre);
});

// ---------- arranque ----------
(async function init() {
  $("fecha").textContent = hoy();
  const r = await api("GET", "/api/admin/me");
  if (r.ok) mostrarPanel(r.datos); else mostrarLogin("");
})();
