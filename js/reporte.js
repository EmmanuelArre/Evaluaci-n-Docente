"use strict";
// Reportes del administrador. Reutiliza la lógica de presentación original (gráfica, tabla por
// alumno, promedios con un decimal), pero los datos llegan del backend (MySQL) y solo con sesión.

const AYUDA = {
  "grupo": "Elige un grupo para ver los profesores y materias evaluados, el número de alumnos y los promedios.",
  "profesor": "Elige un profesor. Opcionalmente filtra por materia y por grupo.",
  "grupo-profesor": "Elige un grupo y un profesor. Opcionalmente filtra por una de las materias asignadas al profesor.",
  "general-grupo": "Resumen de todos los profesores y materias evaluados por el grupo, con el promedio de cada una de las 12 preguntas."
};
const TITULO = {
  "grupo": "Reporte por grupo",
  "profesor": "Reporte por profesor",
  "grupo-profesor": "Reporte por grupo y profesor",
  "general-grupo": "Reporte general por grupo"
};

let tipo = "grupo";
let ultimo = null;           // parámetros del último reporte (para regenerar tras borrar)
let turnoMaterias = 0;
let turnoGrupo = 0;
let profesoresTodos = [];    // catálogo completo (reportes que no dependen del grupo)
let asignacionesGrupo = [];  // profesor/materia que tiene asignados el grupo elegido (reporte grupo + profesor)

const fmt = n => (n === null || n === undefined ? "–" : f1(Number(n)));

function el(tag, texto, clase) {
  const e = document.createElement(tag);
  if (texto !== undefined) e.textContent = texto;
  if (clase) e.className = clase;
  return e;
}
function fila(tbody, valores) {
  const tr = el("tr");
  valores.forEach(v => {
    const td = el("td");
    if (v instanceof Node) td.appendChild(v); else td.textContent = String(v);
    tr.appendChild(td);
  });
  tbody.appendChild(tr);
  return tr;
}

// ---------------- arranque ----------------
(async function init() {
  $("fecha").textContent = hoy();
  const admin = await exigirAdmin();
  if (!admin) return;
  $("quien").textContent = "👤 " + admin.nombre;
  construirLeyenda();
  const [g, p] = await Promise.all([api("GET", "/api/admin/grupos"), api("GET", "/api/admin/profesores")]);
  if (!g.ok || !p.ok) { $("e-reporte").textContent = (g.ok ? p : g).error; return; }
  llenarSelect($("f-grupo"), g.datos, g.datos.length ? "Selecciona un grupo" : "No hay grupos registrados",
    x => x.clave + (x.descripcion ? " – " + x.descripcion : "") + (x.activo ? "" : " (inactivo)"));
  profesoresTodos = p.datos;
  pintarProfesores();
  llenarSelect($("f-materia"), [], "Todas las materias");
  cambiarTipo("grupo");
})();

function construirLeyenda() {
  const ol = $("leyenda");
  CONFIG.preguntas.forEach((t, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<b>${i + 1}</b> <span></span>`;
    li.querySelector("span").textContent = t;
    ol.appendChild(li);
  });
}

// ---------------- filtros ----------------
document.querySelectorAll(".pestana").forEach(b => b.addEventListener("click", () => cambiarTipo(b.dataset.tipo)));

function cambiarTipo(t) {
  tipo = t;
  document.querySelectorAll(".pestana").forEach(b => b.classList.toggle("activa", b.dataset.tipo === t));
  $("ayudaTipo").textContent = AYUDA[t];
  document.querySelectorAll("#formReporte [data-tipos]").forEach(c => c.hidden = !c.dataset.tipos.split(" ").includes(t));
  // El grupo es obligatorio salvo en el reporte por profesor, donde es un filtro opcional
  $("l-grupo").textContent = t === "profesor" ? "Grupo (opcional)" : "Grupo";
  $("l-materia").textContent = "Materia (opcional)";
  const opcionGrupo = $("f-grupo").options[0];
  if (opcionGrupo && $("f-grupo").options.length > 1) opcionGrupo.textContent = t === "profesor" ? "Todos los grupos" : "Selecciona un grupo";
  ["f-grupo", "f-profesor", "f-materia"].forEach(i => setErr(i, ""));
  $("e-reporte").textContent = "";
  limpiarResultado();
  cargarProfesoresDelGrupo();
}

function setErr(id, msg) {
  $("e-" + id).textContent = msg;
  $(id).classList.toggle("invalido", !!msg);
  return !msg;
}

// En el reporte «grupo + profesor» el combo de profesores solo ofrece a quienes dan clase al grupo elegido;
// en los demás reportes se ofrece el catálogo completo.
function pintarProfesores() {
  const sel = $("f-profesor"), previo = sel.value;
  if (tipo === "grupo-profesor") {
    const vistos = new Map();
    asignacionesGrupo.forEach(a => vistos.set(a.profesor_id, a.profesor + (a.profesor_activo ? "" : " (inactivo)")));
    const items = Array.from(vistos, ([id, nombre]) => ({ id, nombre }));
    llenarSelect(sel, items, !$("f-grupo").value ? "Primero selecciona un grupo"
      : items.length ? "Selecciona un profesor" : "Este grupo no tiene profesores asignados");
    sel.disabled = !items.length;
  } else {
    llenarSelect(sel, profesoresTodos, profesoresTodos.length ? "Selecciona un profesor" : "No hay profesores registrados",
      x => x.nombre + (x.activo ? "" : " (inactivo)"));
    sel.disabled = false;
  }
  if (previo && Array.from(sel.options).some(o => o.value === previo)) sel.value = previo;
  pintarMaterias();
}

async function cargarProfesoresDelGrupo() {
  if (tipo !== "grupo-profesor") { asignacionesGrupo = []; pintarProfesores(); return; }
  const gid = $("f-grupo").value, turno = ++turnoGrupo;
  asignacionesGrupo = [];
  pintarProfesores();                                   // limpia al instante los profesores del grupo anterior
  if (!gid) return;
  const r = await api("GET", `/api/admin/grupos/${encodeURIComponent(gid)}/asignaciones`);
  if (turno !== turnoGrupo) return;
  if (r.status === 401) { window.location.href = "admin.html"; return; }
  if (!r.ok) { setErr("f-profesor", r.error); return; }
  asignacionesGrupo = r.datos;
  pintarProfesores();
}

// La materia depende del profesor: solo se ofrecen las asignadas a él (y, con grupo, las que da a ese grupo)
async function pintarMaterias() {
  const id = $("f-profesor").value, sel = $("f-materia");
  const turno = ++turnoMaterias;
  llenarSelect(sel, [], "Todas las materias");
  sel.disabled = true;
  if (!id) return;
  if (tipo === "grupo-profesor") {
    const mats = asignacionesGrupo.filter(a => String(a.profesor_id) === id)
      .map(a => ({ id: a.materia_id, nombre: a.materia, activo: a.materia_activa }));
    llenarSelect(sel, mats, mats.length ? "Todas las materias" : "Sin materias asignadas", m => m.nombre + (m.activo ? "" : " (inactiva)"));
    sel.disabled = !mats.length;
    return;
  }
  const r = await api("GET", `/api/admin/profesores/${encodeURIComponent(id)}/materias`);
  if (turno !== turnoMaterias) return;
  if (!r.ok) { setErr("f-materia", r.error); return; }
  llenarSelect(sel, r.datos, r.datos.length ? "Todas las materias" : "Sin materias asignadas",
    m => m.nombre + (m.activo ? "" : " (inactiva)"));
  sel.disabled = !r.datos.length;
}
$("f-profesor").addEventListener("change", () => { setErr("f-profesor", ""); pintarMaterias(); });
["f-grupo", "f-materia"].forEach(i => $(i).addEventListener("change", () => setErr(i, "")));
$("f-grupo").addEventListener("change", cargarProfesoresDelGrupo);

$("formReporte").addEventListener("submit", e => {
  e.preventDefault();
  let ok = true;
  const necesitaGrupo = tipo !== "profesor", necesitaProfesor = tipo === "profesor" || tipo === "grupo-profesor";
  if (necesitaGrupo) ok = setErr("f-grupo", $("f-grupo").value ? "" : "Selecciona un grupo.") && ok;
  if (necesitaProfesor) ok = setErr("f-profesor", $("f-profesor").value ? "" : "Selecciona un profesor.") && ok;
  if (!ok) return;
  const p = new URLSearchParams();
  if ($("f-grupo").value && !$("f-grupo").closest("[data-tipos]").hidden) p.set("grupo", $("f-grupo").value);
  if (necesitaProfesor && $("f-profesor").value) p.set("profesor", $("f-profesor").value);
  if (necesitaProfesor && $("f-materia").value) p.set("materia", $("f-materia").value);
  generar(tipo, p);
});

// ---------------- generación y pintado ----------------
function limpiarResultado() {
  $("resultado").hidden = true;
  $("msgVacio").hidden = true;
  ultimo = null;
}

async function generar(t, params) {
  $("e-reporte").textContent = "";
  $("btnGenerar").disabled = true;
  const r = await api("GET", `/api/admin/reportes/${t}?${params.toString()}`);
  $("btnGenerar").disabled = false;
  if (r.status === 401) { window.location.href = "admin.html"; return; }
  if (!r.ok) { limpiarResultado(); $("e-reporte").textContent = r.error; return; }
  ultimo = { t, params };
  pintar(r.datos);
}

function pintar(d) {
  $("e-reporte").textContent = "";
  if (d.vacio) {
    $("resultado").hidden = true;
    $("msgVacio").hidden = false;
    $("msgVacio").textContent = "No hay evaluaciones registradas con los filtros seleccionados. Cuando los alumnos contesten la encuesta aparecerán aquí.";
    return;
  }
  $("msgVacio").hidden = true;
  $("resultado").hidden = false;
  $("tituloReporte").textContent = TITULO[d.tipo];

  const F = d.filtros;
  $("r-grupo").textContent = F.grupo ? F.grupo.clave : "Todos";
  $("r-profesor").textContent = F.profesor ? F.profesor.nombre : (d.porProfesor.length === 1 ? d.porProfesor[0].nombre : "Todos");
  $("r-materia").textContent = F.materia ? F.materia.nombre : (d.porMateria.length === 1 ? d.porMateria[0].nombre : "Todas");
  $("r-encuestas").textContent = d.resumen.encuestas;
  $("r-total").textContent = d.resumen.evaluaciones;
  $("r-respuestas").textContent = d.resumen.respuestas;
  $("r-general").textContent = fmt(d.resumen.promedio);

  pintarGrafica(d);
  pintarPM(d);
  pintarResumenes(d);
  pintarDetalle(d);
}

// Gráfica de barras: misma lógica que la versión original
function pintarGrafica(d) {
  const gr = $("grafica"); gr.innerHTML = "";
  const rango = CONFIG.maxCalif - CONFIG.minCalif;
  d.porPregunta.forEach((p, i) => {
    const alto = p === null ? 0 : Math.max(0, (p - CONFIG.minCalif) / rango * 100);
    const c = document.createElement("div");
    c.className = "barra-col";
    c.innerHTML = `<span class="val">${fmt(p)}</span><div class="barra" style="height:${alto}%"></div><span class="eti">${i + 1}</span>`;
    gr.appendChild(c);
  });
}

// Profesores y materias evaluados (con promedio de cada pregunta en el reporte general)
function pintarPM(d) {
  const conPreguntas = d.tipo === "general-grupo";
  const mostrarGrupo = !d.filtros.grupo;
  $("tituloPM").textContent = conPreguntas ? "Profesores y materias evaluados – promedio por pregunta" : "Profesores y materias evaluados";
  let h = "<tr>" + (mostrarGrupo ? "<th>Grupo</th>" : "") + "<th>Profesor</th><th>Materia</th><th>Alumnos</th><th>Promedio</th>";
  if (conPreguntas) for (let i = 1; i <= CONFIG.totalPreguntas; i++) h += `<th>P${i}</th>`;
  $("tablaPM").tHead.innerHTML = h + "</tr>";
  const tb = $("tablaPM").tBodies[0]; tb.innerHTML = "";
  d.porProfesorMateria.forEach(x => {
    const v = [];
    if (mostrarGrupo) v.push(x.grupo);
    v.push(x.profesor, x.materia, x.evaluaciones, el("b", fmt(x.promedio)));
    if (conPreguntas) x.preguntas.forEach(p => v.push(fmt(p)));
    const tr = fila(tb, v);
    tr.children[0 + (mostrarGrupo ? 1 : 0)].classList.add("izq");
    tr.children[1 + (mostrarGrupo ? 1 : 0)].classList.add("izq");
  });
  const pie = $("tablaPM").tFoot;
  const cols = (mostrarGrupo ? 1 : 0) + 2;
  let f = `<tr><td colspan="${cols}">${conPreguntas ? "Promedio general del grupo" : "General"}</td><td>${d.resumen.evaluaciones}</td><td><b>${fmt(d.resumen.promedio)}</b></td>`;
  if (conPreguntas) d.porPregunta.forEach(p => f += `<td>${fmt(p)}</td>`);
  pie.innerHTML = f + "</tr>";
}

function pintarResumenes(d) {
  const tp = $("tablaProf").tBodies[0]; tp.innerHTML = "";
  d.porProfesor.forEach(x => fila(tp, [x.nombre, x.evaluaciones, el("b", fmt(x.promedio))]).children[0].classList.add("izq"));
  const tm = $("tablaMat").tBodies[0]; tm.innerHTML = "";
  d.porMateria.forEach(x => fila(tm, [x.nombre, x.evaluaciones, el("b", fmt(x.promedio))]).children[0].classList.add("izq"));
}

// Tabla por alumno: misma estructura que la original (P1–P12, promedio por alumno, comentarios)
function pintarDetalle(d) {
  const F = d.filtros;
  const cGrupo = !F.grupo, cProf = !F.profesor && d.porProfesor.length > 1, cMat = !F.materia && d.porMateria.length > 1;
  let h = "<tr><th>Alum</th><th>Fecha</th>" + (cGrupo ? "<th>Grupo</th>" : "") + (cProf ? "<th>Profesor</th>" : "") + (cMat ? "<th>Materia</th>" : "");
  for (let i = 1; i <= CONFIG.totalPreguntas; i++) h += `<th>P${i}</th>`;
  h += "<th>Prom. x alumno</th><th>Comentarios</th><th></th></tr>";
  $("tabla").tHead.innerHTML = h;

  const tb = $("tabla").tBodies[0]; tb.innerHTML = "";
  const extra = (cGrupo ? 1 : 0) + (cProf ? 1 : 0) + (cMat ? 1 : 0);
  d.detalle.forEach((a, idx) => {
    const tr = document.createElement("tr");
    const prom = media(a.respuestas);
    const celdas = [idx + 1, new Date(a.fecha).toLocaleDateString("es-MX")];
    if (cGrupo) celdas.push(a.grupo);
    if (cProf) celdas.push(a.profesor);
    if (cMat) celdas.push(a.materia);
    a.respuestas.forEach(r => celdas.push(r));
    celdas.push(el("b", f1(prom)));
    const com = el("span", a.comentario || ""); celdas.push(com);
    const del = el("button", "✕", "del");
    del.type = "button"; del.setAttribute("aria-label", `Eliminar alumno ${idx + 1}`);
    del.addEventListener("click", () => eliminar(a.id, idx + 1));
    celdas.push(del);
    celdas.forEach(c => {
      const td = el("td");
      if (c instanceof Node) td.appendChild(c); else td.textContent = String(c);
      tr.appendChild(td);
    });
    tr.children[tr.children.length - 2].className = "com";
    tb.appendChild(tr);
  });
  $("tabla").tFoot.innerHTML = `<tr><td colspan="${2 + extra}">Prom.</td>` +
    d.porPregunta.map(p => `<td>${fmt(p)}</td>`).join("") +
    `<td><b>${fmt(d.resumen.promedio)}</b></td><td></td><td></td></tr>`;

  const av = $("avisoTrunc");
  av.hidden = !d.detalleTruncado;
  av.textContent = d.detalleTruncado ? "Se muestran solo las primeras 1000 evaluaciones; los promedios incluyen todas." : "";
}

async function eliminar(id, numero) {
  if (!confirm(`¿Eliminar definitivamente la evaluación del alumno ${numero}? Se borrarán también sus 12 respuestas y los promedios se recalcularán.`)) return;
  const r = await api("DELETE", `/api/admin/evaluaciones/${id}`);
  if (r.status === 401) { window.location.href = "admin.html"; return; }
  if (!r.ok) { $("e-reporte").textContent = r.error; return; }
  if (ultimo) generar(ultimo.t, ultimo.params);
}

$("btnImprimir").addEventListener("click", () => window.print());
$("btnSalir").addEventListener("click", cerrarSesion);
