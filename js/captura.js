"use strict";
const reGrupo = /^[A-Za-z]{4}\d{3}$/;

let enviando = false;      // evita envíos repetidos
let cargaMaterias = 0;     // descarta respuestas viejas si el alumno cambia rápido de profesor

(function init() {
  $("fecha").textContent = hoy();
  construirPreguntas();
  actualizarContador();
  cargarProfesores();
})();

function construirPreguntas() {
  const cont = $("preguntas");
  cont.innerHTML = "";
  CONFIG.preguntas.forEach((txt, i) => {
    const n = i + 1;
    let opts = "";
    for (let v = CONFIG.minCalif; v <= CONFIG.maxCalif; v++)
      opts += `<label class="op"><input type="radio" name="p${n}" value="${v}"><span>${v}</span></label>`;
    const fila = document.createElement("div");
    fila.className = "preg";
    fila.id = "fila" + n;
    fila.innerHTML = `<div class="num">${n}</div><div class="txt"></div><div class="opciones" role="radiogroup" aria-label="Pregunta ${n}">${opts}</div>`;
    fila.querySelector(".txt").textContent = txt;
    cont.appendChild(fila);
  });
}

// ---------- Profesores y materias (desde MySQL vía API) ----------
async function cargarProfesores() {
  const sel = $("profesor");
  sel.disabled = true;
  const r = await api("GET", "/api/profesores");
  if (!r.ok) {
    llenarSelect(sel, [], "No se pudo cargar la lista");
    setError("profesor", r.error + " Recarga la página para reintentar.");
    return;
  }
  setError("profesor", "");
  llenarSelect(sel, r.datos, r.datos.length ? "Selecciona un profesor" : "No hay profesores registrados");
  sel.disabled = !r.datos.length;
  if (!r.datos.length) $("e-profesor").textContent = "Aún no hay profesores registrados. Avisa al administrador.";
}

async function cargarMaterias() {
  const sel = $("materia"), info = $("i-materia");
  const id = $("profesor").value;
  const turno = ++cargaMaterias;
  info.textContent = "";
  setError("materia", "");
  llenarSelect(sel, [], "Primero selecciona un profesor");
  sel.disabled = true;
  if (!id) return;

  llenarSelect(sel, [], "Cargando materias…");
  const r = await api("GET", `/api/profesores/${encodeURIComponent(id)}/materias`);
  if (turno !== cargaMaterias) return; // llegó tarde: el alumno ya cambió de profesor
  if (!r.ok) {
    llenarSelect(sel, [], "No se pudieron cargar");
    setError("materia", r.error);
    return;
  }
  const mats = r.datos;
  if (mats.length === 0) {
    llenarSelect(sel, [], "Sin materias asignadas");
    info.textContent = "Este profesor no tiene materias asignadas. Avisa al administrador.";
  } else if (mats.length === 1) {
    llenarSelect(sel, mats, "Selecciona una materia");
    sel.value = String(mats[0].id);           // una sola materia: se selecciona sola
    sel.disabled = false;
    info.textContent = "Materia asignada automáticamente.";
  } else {
    llenarSelect(sel, mats, "Selecciona una materia");
    sel.disabled = false;
  }
}

$("profesor").addEventListener("change", () => { setError("profesor", ""); cargarMaterias(); });
$("materia").addEventListener("change", () => setError("materia", ""));

// ---------- Validaciones ----------
function setError(id, msg) {
  $("e-" + id).textContent = msg;
  const campo = $(id);
  if (campo) campo.classList.toggle("invalido", !!msg);
  return !msg;
}

function validarGeneral() {
  const g = $("grupo").value.trim(), p = $("profesor").value, m = $("materia").value;
  let ok = true;
  ok = setError("grupo", !g ? "El grupo es obligatorio." : !reGrupo.test(g) ? "Formato: 3 letras y 4 dígitos (ej. GSI0252)." : "") && ok;
  ok = setError("profesor", !p ? "Selecciona un profesor." : "") && ok;
  ok = setError("materia", !p ? "" : !m ? ($("materia").disabled ? "Este profesor no tiene materias disponibles." : "Selecciona una materia.") : "") && ok;
  if (!p && !$("e-materia").textContent) $("e-materia").textContent = "";
  return ok;
}

function validarRespuestas() {
  const resp = [];
  let faltan = [];
  for (let n = 1; n <= CONFIG.totalPreguntas; n++) {
    const sel = document.querySelector(`input[name="p${n}"]:checked`);
    $("fila" + n).classList.toggle("invalido", !sel);
    const v = sel ? Number(sel.value) : NaN;
    if (sel && Number.isInteger(v) && v >= CONFIG.minCalif && v <= CONFIG.maxCalif) resp.push(v); else faltan.push(n);
  }
  $("e-preguntas").textContent = faltan.length ? `Falta contestar la(s) pregunta(s): ${faltan.join(", ")}.` : "";
  return faltan.length ? null : resp;
}

function validarComentario() {
  const largo = $("comentario").value.length;
  return setError("comentario", largo > CONFIG.maxComentario ? `Máximo ${CONFIG.maxComentario} caracteres.` : "");
}

$("grupo").addEventListener("input", e => { e.target.value = e.target.value.toUpperCase(); setError("grupo", ""); });
$("comentario").addEventListener("input", actualizarContador);

function actualizarContador() {
  $("contador").textContent = `${$("comentario").value.length} / ${CONFIG.maxComentario}`;
}

function limpiar() {
  document.querySelectorAll("#preguntas input:checked").forEach(r => r.checked = false);
  document.querySelectorAll(".preg").forEach(f => f.classList.remove("invalido"));
  $("comentario").value = "";
  $("e-preguntas").textContent = "";
  $("e-comentario").textContent = "";
  actualizarContador();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("btnLimpiar").addEventListener("click", limpiar);

function bloquearEnvio(si) {
  enviando = si;
  $("btnGuardar").disabled = si;
  $("btnGuardar").textContent = si ? "Guardando…" : "Guardar encuesta";
}

$("formEncuesta").addEventListener("submit", async e => {
  e.preventDefault();
  if (enviando) return;                       // ya hay un envío en curso
  $("e-envio").textContent = "";
  $("aviso").hidden = true;

  const okG = validarGeneral();
  const okC = validarComentario();
  const resp = validarRespuestas();
  if (!okG || !okC || !resp) { (document.querySelector(".invalido") || $("grupo")).scrollIntoView({ block: "center" }); return; }

  bloquearEnvio(true);
  const r = await api("POST", "/api/evaluaciones", {
    grupo: $("grupo").value.trim().toUpperCase(),
    profesor_id: Number($("profesor").value),
    materia_id: Number($("materia").value),
    respuestas: resp,
    comentario: $("comentario").value.trim()
  });
  bloquearEnvio(false);

  if (!r.ok) {
    // Los datos capturados se conservan para poder reintentar
    if (r.errores) {
      ["grupo", "profesor", "materia", "comentario", "preguntas"].forEach(k => { if (r.errores[k]) setError(k, r.errores[k]); });
    }
    $("e-envio").textContent = `No se pudo guardar la encuesta: ${r.error} Tus respuestas siguen en pantalla; corrige y vuelve a presionar "Guardar encuesta".`;
    (document.querySelector(".invalido") || $("e-envio")).scrollIntoView({ block: "center" });
    return;
  }
  $("aviso").hidden = false;
  setTimeout(() => $("aviso").hidden = true, 6000);
  limpiar(); // se limpian respuestas y comentario; grupo/profesor/materia se conservan (como antes)
});
