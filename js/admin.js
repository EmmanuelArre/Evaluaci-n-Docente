"use strict";
// Pantalla del administrador: inicio de sesión y gestión de grupos, profesores y materias.
// Las reglas de acceso las impone el servidor; aquí solo se arma la interfaz.

const reGrupo = /^[A-Za-z]{4}\d{3}$/;
const colapsar = s => s.replace(/\s+/g, " ").trim();

let listaMaterias = [];     // para el combo de asignación
let profesorAsignando = null;
let turnoProfesores = 0;    // descarta respuestas viejas si se pidieron dos recargas seguidas

// Recarga materias y luego profesores (una sola pasada, en orden) para que ambas tablas y el combo de asignación coincidan
async function recargarCatalogos() { await cargarMaterias(); await cargarProfesores(); await cargarCombosAsignacion(); }

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
  if (b.dataset.tab === "asignaciones") cargarCombosAsignacion();   // los grupos/profesores pudieron cambiar en otra pestaña
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
    const tr = el("tr"); const td = celda(tr, "Aún no hay grupos registrados.", "vacio"); td.colSpan = 8; tb.appendChild(tr);
  }
  r.datos.forEach(g => {
    const tr = el("tr");
    celda(tr, g.clave); celda(tr, g.descripcion || "–");
    celda(tr, g.num_alumnos ? g.num_alumnos : "⚠ sin capturar", g.num_alumnos ? undefined : "advertencia");
    celda(tr, g.encuestas);
    celda(tr, g.inconsistente ? "⚠ 0 (hay más encuestas que alumnos)" : g.disponibles, g.inconsistente ? "advertencia" : undefined);
    const clave = g.clave_ilegible ? "⚠ no se puede descifrar (revisa CLAVE_CIFRADO_ACCESO)" : g.tiene_clave ? g.clave_acceso : "⚠ sin contraseña: no hay acceso";
    celda(tr, clave, g.tiene_clave && !g.clave_ilegible ? "clave-acceso" : "advertencia");
    celda(tr, etiquetaEstado(g.activo));
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
let encuestasGrupoEditado = 0;
function resetGrupo() {
  $("g-id").value = ""; $("g-clave").value = ""; $("g-desc").value = ""; $("g-activo").checked = true;
  $("g-alumnos").value = ""; $("g-acceso").value = ""; encuestasGrupoEditado = 0;
  $("tit-grupo").textContent = "Nuevo grupo"; $("g-cancelar").hidden = true;
  setErr("g-clave"); setErr("g-desc"); setErr("g-alumnos"); setErr("g-acceso");
}
function editarGrupo(g) {
  $("g-id").value = g.id; $("g-clave").value = g.clave; $("g-desc").value = g.descripcion || ""; $("g-activo").checked = !!g.activo;
  $("g-alumnos").value = g.num_alumnos || ""; $("g-acceso").value = g.clave_acceso || ""; encuestasGrupoEditado = g.encuestas;
  $("tit-grupo").textContent = "Editar grupo " + g.clave; $("g-cancelar").hidden = false;
  $("g-clave").focus(); window.scrollTo({ top: 0, behavior: "smooth" });
}
$("g-clave").addEventListener("input", e => { e.target.value = e.target.value.toUpperCase(); });
$("g-cancelar").addEventListener("click", resetGrupo);
$("g-generar").addEventListener("click", () => { $("g-acceso").value = generarClaveAcceso(); setErr("g-acceso"); });

function validarAlumnosFront(texto) {
  const t = String(texto).trim();
  if (!t) return { valor: null, error: "El número de alumnos es obligatorio." };
  if (!/^\d+$/.test(t)) return { valor: null, error: "Escribe un número entero positivo (sin decimales, letras ni signos)." };
  const v = Number(t);
  if (v < 1) return { valor: null, error: "Debe ser un entero positivo (mínimo 1)." };
  if (v > 99) return { valor: null, error: "Máximo 99 alumnos." };
  if (encuestasGrupoEditado && v < encuestasGrupoEditado)
    return { valor: v, error: `Este grupo ya tiene ${encuestasGrupoEditado} encuestas válidas: el mínimo es ${encuestasGrupoEditado}. Las encuestas no se eliminan automáticamente.` };
  return { valor: v, error: "" };
}
function validarClaveAccesoFront(t) {
  if (!t) return "";                                   // opcional al guardar; sin ella el grupo no tiene acceso
  if (t.length < 4) return "Mínimo 4 caracteres.";
  if (t.length > 40) return "Máximo 40 caracteres.";
  if (/\s/.test(t)) return "No puede contener espacios.";
  return "";
}
$("formGrupo").addEventListener("submit", async e => {
  e.preventDefault();
  const clave = $("g-clave").value.trim().toUpperCase(), desc = colapsar($("g-desc").value), acceso = $("g-acceso").value;
  let ok = true;
  ok = setErr("g-clave", !clave ? "La clave es obligatoria." : !reGrupo.test(clave) ? "Formato: 4 letras y 3 dígitos (ej. GTID244)." : "") && ok;
  ok = setErr("g-desc", desc.length > 100 ? "Máximo 100 caracteres." : "") && ok;
  const al = validarAlumnosFront($("g-alumnos").value);
  ok = setErr("g-alumnos", al.error) && ok;
  ok = setErr("g-acceso", validarClaveAccesoFront(acceso)) && ok;
  if (!ok) return;
  const id = $("g-id").value;
  const cuerpo = { clave, descripcion: desc || null, activo: $("g-activo").checked, num_alumnos: al.valor };
  if (acceso) cuerpo.clave_acceso = acceso;
  const r = await ejecutar(id ? "PUT" : "POST", id ? `/api/admin/grupos/${id}` : "/api/admin/grupos", cuerpo,
    id ? "Grupo actualizado." : "Grupo creado.");
  if (r.ok) { resetGrupo(); await cargarGrupos(); }   // primero se limpia el formulario, luego se recarga la tabla
  else if (r.errores) {
    [["clave", "g-clave"], ["descripcion", "g-desc"], ["num_alumnos", "g-alumnos"], ["clave_acceso", "g-acceso"]]
      .forEach(([k, c]) => { if (r.errores[k]) setErr(c, r.errores[k]); });
  }
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

  const tb = $("tablaProfesores").tBodies[0];
  tb.innerHTML = "";

  if (!r.datos.length) {
    const tr = el("tr");
    const td = celda(tr, "Aún no hay profesores registrados.", "vacio");
    td.colSpan = 6;
    tb.appendChild(tr);
  }

  r.datos.forEach(p => {
    const tr = el("tr");

    celda(tr, p.nombre);

    celda(
      tr,
      p.materias.length
        ? p.materias.map(m => m.nombre + (m.activo ? "" : " (inactiva)")).join(", ")
        : "Sin materias"
    );

    celda(
      tr,
      p.grupos.length
        ? p.grupos.map(g => g.clave + (g.activo ? "" : " (inactivo)")).join(", ")
        : "⚠ Sin grupos: no aparece para ningún alumno",
      p.grupos.length ? undefined : "advertencia"
    );
    celda(tr, etiquetaEstado(p.activo));
    celda(tr, p.evaluaciones);

    const acc = el("div", undefined, "acciones");

    acc.append(
      boton("Editar", () => editarProfesor(p)),

      boton("Materias", () => abrirAsignacion(p)),

      boton(
        p.activo ? "Desactivar" : "Activar",
        () => ejecutar(
          "PUT",
          `/api/admin/profesores/${p.id}`,
          { activo: !p.activo },
          p.activo ? "Profesor desactivado." : "Profesor activado.",
          recargarCatalogos
        )
      ),

      boton("Eliminar", async () => {
        if (!confirm(
          `¿Eliminar al profesor ${p.nombre}? Solo es posible si no tiene evaluaciones; de lo contrario desactívalo.`
        )) return;

        const r2 = await ejecutar(
          "DELETE",
          `/api/admin/profesores/${p.id}`,
          undefined,
          "Profesor eliminado.",
          recargarCatalogos
        );

        if (r2.ok && profesorAsignando === p.id) {
          $("cajaAsignar").hidden = true;
        }
      }, "peligro chico")
    );

    celda(tr, acc);
    tb.appendChild(tr);
  });

  if (profesorAsignando) {
    const p = r.datos.find(x => x.id === profesorAsignando);

    if (p) {
      pintarAsignadas(p);
    } else {
      profesorAsignando = null;
      $("cajaAsignar").hidden = true;
    }
  }
}

function resetProfesor() {
  $("p-id").value = "";
  ["p-nombres", "p-paterno", "p-materno"].forEach(c => { $(c).value = ""; setErr(c); });
  $("p-activo").checked = true;

  $("tit-profesor").textContent = "Nuevo profesor";
  $("p-cancelar").hidden = true;
}

function editarProfesor(p) {
  $("p-id").value = p.id;
  // Profesores registrados antes de separar el nombre: se propone la separación para que el administrador la confirme
  const partes = p.nombres ? p : separarNombre(p.nombre);
  $("p-nombres").value = partes.nombres || "";
  $("p-paterno").value = partes.apellido_paterno || "";
  $("p-materno").value = partes.apellido_materno || "";
  $("p-activo").checked = !!p.activo;

  $("tit-profesor").textContent = "Editar profesor";
  $("p-cancelar").hidden = false;

  $("p-nombres").focus();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("p-cancelar").addEventListener("click", resetProfesor);
["p-nombres", "p-paterno", "p-materno"].forEach(c =>
  $(c).addEventListener("blur", e => { if (e.target.value.trim()) e.target.value = normalizarNombre(e.target.value); }));

$("formProfesor").addEventListener("submit", async e => {
  e.preventDefault();

  // Se normaliza aquí (se ve al instante) y otra vez en el servidor, que es quien decide
  const n = validarParteNombre($("p-nombres").value, "El nombre", MAX_LARGO_NOMBRES, MAX_NOMBRES_PILA, true, true);
  const pa = validarParteNombre($("p-paterno").value, "El apellido paterno", MAX_LARGO_APELLIDO, MAX_PALABRAS_APELLIDO, true);
  const ma = validarParteNombre($("p-materno").value, "El apellido materno", MAX_LARGO_APELLIDO, MAX_PALABRAS_APELLIDO, false);
  if (n.valor) $("p-nombres").value = n.valor;
  if (pa.valor) $("p-paterno").value = pa.valor;
  $("p-materno").value = ma.valor;
  let ok = setErr("p-nombres", n.error);
  ok = setErr("p-paterno", pa.error) && ok;
  ok = setErr("p-materno", ma.error) && ok;
  if (!ok) return;

  const id = $("p-id").value;

  const r = await ejecutar(
    id ? "PUT" : "POST",
    id ? `/api/admin/profesores/${id}` : "/api/admin/profesores",
    { nombres: n.valor, apellido_paterno: pa.valor, apellido_materno: ma.valor || null, activo: $("p-activo").checked },
    id ? "Profesor actualizado." : "Profesor registrado."
  );

  if (r.ok) {
    resetProfesor();
    await recargarCatalogos();
  } else if (r.errores) {
    if (r.errores.nombres) setErr("p-nombres", r.errores.nombres);
    if (r.errores.apellido_paterno) setErr("p-paterno", r.errores.apellido_paterno);
    if (r.errores.apellido_materno) setErr("p-materno", r.errores.apellido_materno);
  }
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
$("m-nombre").addEventListener("blur", e => { if (e.target.value.trim()) e.target.value = normalizarNombre(e.target.value, true); });
$("formMateria").addEventListener("submit", async e => {
  e.preventDefault();
  const { nombre, error } = validarNombreMateria($("m-nombre").value);
  if (nombre) $("m-nombre").value = nombre;
  if (!setErr("m-nombre", error)) return;
  const id = $("m-id").value;
  const r = await ejecutar(id ? "PUT" : "POST", id ? `/api/admin/materias/${id}` : "/api/admin/materias",
    { nombre, activo: $("m-activo").checked }, id ? "Materia actualizada." : "Materia registrada.");
  if (r.ok) { resetMateria(); await recargarCatalogos(); }
  else if (r.errores && r.errores.nombre) setErr("m-nombre", r.errores.nombre);
});

// =====================================================================
// ASIGNACIONES  (grupo ↔ profesor ↔ materia)
// =====================================================================
let turnoAsig = 0;
let profesoresAsig = [];   // catálogo de profesores (con sus materias) para el formulario de asignación
let asignacionesGrupo = []; // asignaciones del grupo seleccionado

// Rellena el combo de grupos de la pestaña (se llama cada vez que cambian los catálogos)
async function cargarCombosAsignacion() {
  const gr = await api("GET", "/api/admin/grupos");
  if (sesionCaducada(gr)) return;
  if (!gr.ok) return errorPanel(gr.error);
  const previo = $("as-grupo").value;
  llenarSelect($("as-grupo"), gr.datos, gr.datos.length ? "Selecciona un grupo" : "No hay grupos registrados",
    g => g.clave + (g.activo ? "" : " (inactivo)"));
  if (previo && gr.datos.some(g => String(g.id) === previo)) $("as-grupo").value = previo;
  await cargarAsignaciones();
}

async function cargarAsignaciones() {
  const gid = $("as-grupo").value;
  const turno = ++turnoAsig;
  $("cajaAsigGrupo").hidden = !gid;
  if (!gid) return;
  const [pr, as] = await Promise.all([api("GET", "/api/admin/profesores"), api("GET", `/api/admin/grupos/${gid}/asignaciones`)]);
  if (turno !== turnoAsig) return;
  if (sesionCaducada(as) || sesionCaducada(pr)) return;
  if (!as.ok || !pr.ok) return errorPanel((as.ok ? pr : as).error);

  const clave = $("as-grupo").selectedOptions[0].textContent;
  $("tit-asig-grupo").textContent = "Profesores de " + clave;
  const prev = $("as-profesor").value;
  const profesores = pr.datos.filter(p => p.activo && p.materias.length);
  llenarSelect($("as-profesor"), profesores, profesores.length ? "Selecciona un profesor" : "No hay profesores con materias",
    p => p.nombre);
  if (prev && profesores.some(p => String(p.id) === prev)) $("as-profesor").value = prev;
  profesoresAsig = pr.datos;
  asignacionesGrupo = as.datos;
  pintarMateriasAsig();

  const tb = $("tablaAsignaciones").tBodies[0]; tb.innerHTML = "";
  if (!as.datos.length) {
    const tr = el("tr"); const td = celda(tr, "Este grupo aún no tiene profesores asignados: los alumnos no podrán evaluar a nadie.", "vacio");
    td.colSpan = 5; tb.appendChild(tr);
  }
  as.datos.forEach(a => {
    const tr = el("tr");
    celda(tr, a.profesor + (a.profesor_activo ? "" : " (inactivo)"));
    celda(tr, a.materia + (a.materia_activa ? "" : " (inactiva)"));
    celda(tr, etiquetaEstado(a.activo));
    celda(tr, a.evaluaciones);
    const acc = el("div", undefined, "acciones");
    const ruta = `/api/admin/grupos/${gid}/asignaciones/${a.profesor_id}/${a.materia_id}`;
    acc.append(
      boton(a.activo ? "Desactivar" : "Activar", () => ejecutar("PUT", ruta, { activo: !a.activo },
        a.activo ? "Asignación desactivada." : "Asignación activada.", recargarCatalogos)),
      boton("Quitar", async () => {
        if (!confirm(`¿Quitar a ${a.profesor} (${a.materia}) de este grupo?`)) return;
        await ejecutar("DELETE", ruta, undefined, "Asignación quitada.", recargarCatalogos);
      }, "peligro chico"));
    celda(tr, acc);
    tb.appendChild(tr);
  });
}

// La materia depende del profesor: solo las que ese profesor ya imparte (y que aún no tiene en este grupo)
function pintarMateriasAsig() {
  const sel = $("as-materia"), pid = $("as-profesor").value;
  const p = profesoresAsig.find(x => String(x.id) === pid);
  const ya = new Set(asignacionesGrupo.filter(a => String(a.profesor_id) === pid).map(a => a.materia_id));
  const mats = p ? p.materias.filter(m => m.activo && !ya.has(m.id)) : [];
  llenarSelect(sel, mats, !p ? "Primero selecciona un profesor" : mats.length ? "Selecciona una materia" : "Ya tiene todas sus materias en este grupo");
  sel.disabled = !mats.length;
}

$("as-grupo").addEventListener("change", () => { setErr("as-grupo"); cargarAsignaciones(); });
$("as-profesor").addEventListener("change", () => { setErr("as-profesor"); pintarMateriasAsig(); });
$("as-materia").addEventListener("change", () => setErr("as-materia"));
$("formAsigGrupo").addEventListener("submit", async e => {
  e.preventDefault();
  const gid = $("as-grupo").value, pid = Number($("as-profesor").value), mid = Number($("as-materia").value);
  let ok = setErr("as-profesor", pid ? "" : "Selecciona un profesor.");
  ok = setErr("as-materia", mid ? "" : "Selecciona una materia.") && ok;
  if (!gid || !ok) return;
  const r = await ejecutar("POST", `/api/admin/grupos/${gid}/asignaciones`, { profesor_id: pid, materia_id: mid },
    "Asignación guardada.", recargarCatalogos);
  if (!r.ok && r.errores) { if (r.errores.profesor_id) setErr("as-profesor", r.errores.profesor_id); if (r.errores.materia_id) setErr("as-materia", r.errores.materia_id); }
});

// ---------- arranque ----------
(async function init() {
  $("fecha").textContent = hoy();
  const r = await api("GET", "/api/admin/me");
  if (r.ok) mostrarPanel(r.datos); else mostrarLogin("");
})();
