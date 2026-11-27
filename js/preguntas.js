"use strict";
// Pantalla del administrador para ver, buscar, agregar, editar y eliminar las preguntas de la encuesta.
// Las reglas las impone el servidor (app/rutas_preguntas.py); aquí solo se arma la interfaz.

const MIN_TEXTO = 10, MAX_TEXTO = 255;
let busqueda = "";          // texto que se está buscando ("" = todas)
let turno = 0;              // descarta respuestas viejas si se pidieron dos recargas seguidas
let ultimas = [];           // preguntas que se están mostrando
let tope = { total: 0, maximo: 50 };

const colapsar = s => s.replace(/\s+/g, " ").trim();

function el(tag, texto, clase) {
  const e = document.createElement(tag);
  if (texto !== undefined) e.textContent = texto;
  if (clase) e.className = clase;
  return e;
}
function boton(texto, fn, clase) {
  const b = el("button", texto, clase || "secundario chico");
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
}
let temporizador;
function avisar(msg) {
  const a = $("avisoPanel");
  a.textContent = "✔ " + msg; a.hidden = false;
  clearTimeout(temporizador);
  temporizador = setTimeout(() => a.hidden = true, 4000);
}
function errorPanel(msg) { $("errorPanel").textContent = msg || ""; }
function errorTexto(msg) {
  $("e-q-texto").textContent = msg || "";
  $("q-texto").classList.toggle("invalido", !!msg);
  return !msg;
}
// Si la sesión caducó se vuelve a la pantalla de acceso
function caducada(r) {
  if (r.status === 401) { window.location.href = "admin.html"; return true; }
  return false;
}

// ---------- arranque ----------
(async function init() {
  $("fecha").textContent = hoy();
  const admin = await exigirAdmin();
  if (!admin) return;
  $("quien").textContent = "👤 " + admin.nombre;
  await cargar();
})();
$("btnSalir").addEventListener("click", cerrarSesion);

// ---------- lista y búsqueda ----------
async function cargar() {
  const mio = ++turno;
  const url = "/api/admin/preguntas" + (busqueda ? "?q=" + encodeURIComponent(busqueda) : "");
  const r = await api("GET", url);
  if (mio !== turno) return;
  if (caducada(r)) return;
  if (!r.ok) { errorPanel(r.error); return; }
  errorPanel("");
  pintar(r.datos);
}

function pintar(d) {
  ultimas = d.preguntas;
  tope = { total: d.total, maximo: d.maximo };
  const tb = $("tablaPreguntas").tBodies[0];
  tb.innerHTML = "";
  d.preguntas.forEach(p => {
    const tr = el("tr");
    tr.appendChild(el("td", String(p.orden)));
    tr.appendChild(el("td", p.texto, "izq"));
    tr.appendChild(el("td", String(p.respuestas)));
    const acc = el("td");
    const caja = el("div", undefined, "acciones");
    caja.appendChild(boton("Editar", () => empezarEdicion(p)));
    caja.appendChild(boton("Eliminar", () => eliminar(p), "peligro chico"));
    acc.appendChild(caja);
    tr.appendChild(acc);
    tb.appendChild(tr);
  });
  $("vacio").hidden = d.preguntas.length > 0;
  $("resumen").textContent = d.busqueda
    ? `${d.preguntas.length} de ${d.total} preguntas coinciden con «${d.busqueda}».`
    : `${d.total} pregunta(s) en la encuesta (máximo ${d.maximo}).`;
  const lleno = d.total >= d.maximo && !$("q-num").value;
  $("q-guardar").disabled = lleno;
  if (lleno) errorTexto(`Ya hay ${d.maximo} preguntas, que es el máximo.`);
  else if (!$("q-texto").value) errorTexto("");
}

$("formBuscar").addEventListener("submit", e => {
  e.preventDefault();
  busqueda = colapsar($("b-texto").value);
  cargar();
});
$("b-limpiar").addEventListener("click", () => {
  $("b-texto").value = ""; busqueda = ""; cargar();
});

// ---------- alta y edición ----------
$("q-texto").addEventListener("input", () => {
  $("q-contador").textContent = `${$("q-texto").value.length} / ${MAX_TEXTO}`;
  errorTexto("");
});

function validarTexto() {
  const t = colapsar($("q-texto").value);
  if (!t) { errorTexto("La pregunta es obligatoria."); return null; }
  if (t.length < MIN_TEXTO) { errorTexto(`Mínimo ${MIN_TEXTO} caracteres.`); return null; }
  if (t.length > MAX_TEXTO) { errorTexto(`Máximo ${MAX_TEXTO} caracteres.`); return null; }
  errorTexto("");
  return t;
}

function limpiarFormulario() {
  $("q-num").value = "";
  $("q-texto").value = "";
  $("q-contador").textContent = `0 / ${MAX_TEXTO}`;
  $("tit-pregunta").textContent = "Nueva pregunta";
  $("q-guardar").textContent = "Agregar pregunta";
  $("q-cancelar").hidden = true;
  errorTexto("");
}

function empezarEdicion(p) {
  $("q-num").value = String(p.num);
  $("q-texto").value = p.texto;
  $("q-contador").textContent = `${p.texto.length} / ${MAX_TEXTO}`;
  $("tit-pregunta").textContent = `Editar la pregunta ${p.orden}`;
  $("q-guardar").textContent = "Guardar cambios";
  $("q-guardar").disabled = false;
  $("q-cancelar").hidden = false;
  errorTexto("");
  $("q-texto").focus();
  $("formPregunta").scrollIntoView({ block: "start" });
}
$("q-cancelar").addEventListener("click", () => { limpiarFormulario(); cargar(); });

$("formPregunta").addEventListener("submit", async e => {
  e.preventDefault();
  errorPanel("");
  const texto = validarTexto();
  if (texto === null) return;
  const num = $("q-num").value;
  if (num) {
    const p = ultimas.find(x => String(x.num) === num);
    if (p && p.respuestas > 0 && !confirm(
      `Esta pregunta ya tiene ${p.respuestas} respuestas guardadas. Cambiar el texto no modifica las respuestas, ` +
      "así que confirma que la nueva redacción sigue midiendo lo mismo. ¿Guardar el cambio?")) return;
  }
  $("q-guardar").disabled = true;
  const r = num ? await api("PUT", `/api/admin/preguntas/${num}`, { texto })
                : await api("POST", "/api/admin/preguntas", { texto });
  $("q-guardar").disabled = false;
  if (caducada(r)) return;
  if (!r.ok) {
    if (r.errores && r.errores.texto) errorTexto(r.errores.texto); else errorPanel(r.error);
    return;
  }
  avisar(num ? "Pregunta actualizada." : "Pregunta agregada al final de la encuesta.");
  limpiarFormulario();
  await cargar();
});

// ---------- eliminar ----------
async function eliminar(p) {
  const aviso = p.respuestas > 0
    ? `¿Eliminar la pregunta ${p.orden}?\n\nSe borrarán también sus ${p.respuestas} respuestas guardadas y los promedios de los reportes cambiarán. Esto no se puede deshacer.`
    : `¿Eliminar la pregunta ${p.orden}? Todavía no tiene respuestas.`;
  if (!confirm(aviso)) return;
  errorPanel("");
  const r = await api("DELETE", `/api/admin/preguntas/${p.num}`);
  if (caducada(r)) return;
  if (!r.ok) { errorPanel(r.error); return; }
  if ($("q-num").value === String(p.num)) limpiarFormulario();
  avisar(r.datos.respuestas_borradas > 0
    ? `Pregunta eliminada junto con ${r.datos.respuestas_borradas} respuestas.` : "Pregunta eliminada.");
  await cargar();
}
