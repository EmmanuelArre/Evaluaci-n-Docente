"use strict";
// Flujo del alumno: 1) elegir grupo  2) escribir la contraseña del grupo (la verifica el SERVIDOR)
// 3) ver la tabla de profesores/materias y el cuestionario  4) enviar UNA encuesta con todos los profesores.
// La contraseña solo vive en el campo de texto mientras se escribe: no se guarda en localStorage/sessionStorage,
// ni en cookies de JavaScript, ni en la URL; se borra en cuanto se envía. La autorización la guarda el servidor
// en una cookie httpOnly que este script no puede leer.
let enviando = false;       // evita envíos repetidos
let accediendo = false;
let turno = 0;              // descarta respuestas viejas si el alumno cambia de grupo mientras algo carga
let cuestionarioActual = null;   // { grupo, asignaciones, preguntas } del grupo autorizado

(function init() {
  $("fecha").textContent = hoy();
  cargarGrupos();
})();

async function cargarGrupos() {
  const sel = $("grupo");
  sel.disabled = true;
  const r = await api("GET", "/api/grupos");
  if (!r.ok) {
    llenarSelect(sel, [], "No se pudo cargar la lista");
    setError("grupo", r.error + " Recarga la página para reintentar.");
    return;
  }
  setError("grupo", "");
  llenarSelect(sel, r.datos, r.datos.length ? "Selecciona tu grupo" : "No hay grupos registrados", g => g.clave);
  sel.disabled = !r.datos.length;
  if (!r.datos.length) setError("grupo", "Aún no hay grupos registrados. Avisa al administrador.");
}

function setError(id, msg) {
  $("e-" + id).textContent = msg;
  const campo = $(id);
  if (campo) campo.classList.toggle("invalido", !!msg);
  return !msg;
}

// Borra TODO lo que dependa del grupo anterior (tabla, secciones, respuestas, contraseña escrita)
function olvidarGrupo() {
  turno++;
  cuestionarioActual = null;
  $("formEncuesta").hidden = true;
  $("confirmacion").hidden = true;
  $("tablaProfesores").innerHTML = "";
  $("secciones").innerHTML = "";
  $("disponibilidad").textContent = "";
  $("e-envio").textContent = "";
  $("clave").value = "";
  setError("clave", "");
  $("e-acceso").textContent = "";
}

$("grupo").addEventListener("change", () => {
  olvidarGrupo();
  setError("grupo", "");
  const opt = $("grupo").selectedOptions[0];
  const hay = !!$("grupo").value;
  $("campoClave").hidden = !hay;
  $("botonesAcceso").hidden = !hay;
  $("nombreGrupo").textContent = hay ? `(${opt.textContent})` : "";
  if (hay) $("clave").focus();
});

$("formAcceso").addEventListener("submit", async e => {
  e.preventDefault();
  if (accediendo) return;
  const gid = $("grupo").value;
  $("e-acceso").textContent = "";
  if (!gid) { setError("grupo", "Selecciona tu grupo."); return; }
  const clave = $("clave").value;
  if (!clave.trim()) { setError("clave", "Escribe la contraseña del grupo."); return; }
  setError("clave", "");

  accediendo = true;
  $("btnAcceder").disabled = true;
  $("btnAcceder").textContent = "Verificando…";
  const mio = ++turno;
  const r = await api("POST", `/api/grupos/${encodeURIComponent(gid)}/acceso`, { clave });
  $("clave").value = "";                         // nunca se conserva en pantalla
  accediendo = false;
  $("btnAcceder").disabled = false;
  $("btnAcceder").textContent = "Acceder a la encuesta";
  if (mio !== turno) return;                     // el alumno cambió de grupo mientras tanto

  if (!r.ok) {
    if (r.status === 401) setError("clave", "La contraseña no es válida.");
    else if (r.status === 429) $("e-acceso").textContent = r.error;
    else $("e-acceso").textContent = r.error;      // 409: sin contraseña configurada / límite alcanzado / sin alumnos
    return;
  }
  await cargarCuestionario(gid, mio);
});

async function cargarCuestionario(gid, mio) {
  const r = await api("GET", `/api/grupos/${encodeURIComponent(gid)}/cuestionario`);
  if (mio !== turno) return;
  if (!r.ok) { $("e-acceso").textContent = r.error; return; }
  cuestionarioActual = r.datos;
  pintarCuestionario(r.datos);
}

function pintarCuestionario(d) {
  $("tituloGrupo").textContent = `(${d.grupo.clave})`;
  const disp = d.disponibilidad;
  $("disponibilidad").textContent = `Encuestas disponibles en este grupo: ${disp.disponibles} de ${disp.alumnos}.`;
  const cuerpo = $("tablaProfesores");
  cuerpo.innerHTML = "";
  $("vacio").hidden = d.asignaciones.length > 0;
  d.asignaciones.forEach((a, i) => {                // el número es solo visual; el envío usa los identificadores reales
    const tr = document.createElement("tr");
    [String(i + 1), a.profesor, a.materia].forEach(t => { const td = document.createElement("td"); td.textContent = t; tr.appendChild(td); });
    cuerpo.appendChild(tr);
  });
  const cont = $("secciones");
  cont.innerHTML = "";
  d.asignaciones.forEach((a, i) => cont.appendChild(crearSeccion(a, i + 1, d.preguntas)));
  $("pie").hidden = d.asignaciones.length === 0;
  $("btnGuardar").disabled = d.asignaciones.length === 0;
  $("formEncuesta").hidden = false;
  $("campoClave").hidden = true;              // ya autorizado: el selector de grupo sigue visible; cambiarlo borra todo
  $("botonesAcceso").hidden = true;
  $("formEncuesta").scrollIntoView({ block: "start" });
}

function crearSeccion(a, num, preguntas) {
  const clave = `${a.profesor_id}_${a.materia_id}`;
  const sec = document.createElement("section");
  sec.className = "tarjeta seccion-prof";
  sec.dataset.clave = clave;
  const h = document.createElement("h2");
  h.textContent = `${num}. ${a.profesor} — ${a.materia}`;
  sec.appendChild(h);
  const encab = document.createElement("div");
  encab.className = "encab-preg";
  encab.innerHTML = "<span>No.</span><span>Pregunta</span><span>Calificación</span>";
  sec.appendChild(encab);
  preguntas.forEach(p => {
    const fila = document.createElement("div");
    fila.className = "preg";
    fila.id = `fila_${clave}_${p.num}`;
    const n = document.createElement("div"); n.className = "num"; n.textContent = p.num;
    const t = document.createElement("div"); t.className = "txt"; t.textContent = p.texto;
    // Calificación con botones 5 a 10, como en la versión anterior; ninguno viene marcado
    const ops = document.createElement("div");
    ops.className = "opciones";
    ops.setAttribute("role", "radiogroup");
    ops.setAttribute("aria-label", `Pregunta ${p.num} de ${a.profesor}, ${a.materia}`);
    for (let v = CONFIG.minCalif; v <= CONFIG.maxCalif; v++) {
      const lab = document.createElement("label"); lab.className = "op";
      const inp = document.createElement("input");
      inp.type = "radio"; inp.name = `r_${clave}_${p.num}`; inp.value = String(v);
      inp.addEventListener("change", () => {
        fila.classList.remove("invalido");
        if (!sec.querySelector(".preg.invalido")) $(`e-s_${clave}`).textContent = "";
        $("e-envio").textContent = "";
      });
      const sp = document.createElement("span"); sp.textContent = String(v);
      lab.append(inp, sp); ops.appendChild(lab);
    }
    const sel = ops;
    fila.append(n, t, sel);
    sec.appendChild(fila);
  });
  const campo = document.createElement("div");
  campo.className = "campo";
  campo.innerHTML = `<label for="c_${clave}">Comentarios (opcional)</label>
    <textarea id="c_${clave}" maxlength="${CONFIG.maxComentario}" rows="2"></textarea>
    <small class="error" id="e-c_${clave}" role="alert"></small>`;
  sec.appendChild(campo);
  const err = document.createElement("small");
  err.className = "error"; err.id = `e-s_${clave}`; err.setAttribute("role", "alert");
  sec.appendChild(err);
  return sec;
}

// Revisa que TODAS las preguntas de TODOS los profesores tengan una calificación entera de 5 a 10
function reunirEvaluaciones() {
  const evaluaciones = [];
  let primeraFalta = null, faltan = 0;
  cuestionarioActual.asignaciones.forEach(a => {
    const clave = `${a.profesor_id}_${a.materia_id}`;
    const resp = [], faltantes = [];
    cuestionarioActual.preguntas.forEach(p => {
      const marcado = document.querySelector(`input[name="r_${clave}_${p.num}"]:checked`);
      const sel = marcado || document.querySelector(`input[name="r_${clave}_${p.num}"]`);
      const v = marcado ? Number(marcado.value) : NaN;
      const ok = Number.isInteger(v) && v >= CONFIG.minCalif && v <= CONFIG.maxCalif;
      $(`fila_${clave}_${p.num}`).classList.toggle("invalido", !ok);
      if (ok) resp.push(v); else { faltantes.push(p.num); if (!primeraFalta) primeraFalta = sel; }
    });
    const com = $(`c_${clave}`).value.trim();
    const comOk = com.length <= CONFIG.maxComentario;
    $(`e-c_${clave}`).textContent = comOk ? "" : `Máximo ${CONFIG.maxComentario} caracteres.`;
    $(`e-s_${clave}`).textContent = faltantes.length ? `Falta contestar la(s) pregunta(s): ${faltantes.join(", ")}.` : "";
    faltan += faltantes.length + (comOk ? 0 : 1);
    if (!comOk && !primeraFalta) primeraFalta = $(`c_${clave}`);
    evaluaciones.push({ profesor_id: a.profesor_id, materia_id: a.materia_id, respuestas: resp, comentario: com });
  });
  return { evaluaciones, faltan, primeraFalta };
}

function bloquearEnvio(si) {
  enviando = si;
  $("btnGuardar").disabled = si;
  $("btnGuardar").textContent = si ? "Enviando…" : "Enviar encuesta";
}

$("formEncuesta").addEventListener("submit", async e => {
  e.preventDefault();
  if (enviando || !cuestionarioActual) return;          // ya hay un envío en curso (doble clic / Enter repetido)
  $("e-envio").textContent = "";
  const { evaluaciones, faltan, primeraFalta } = reunirEvaluaciones();
  if (faltan) {
    $("e-envio").textContent = "Contesta todas las preguntas de todos los profesores antes de enviar.";
    if (primeraFalta) primeraFalta.scrollIntoView({ block: "center" });
    return;
  }
  bloquearEnvio(true);
  const r = await api("POST", "/api/encuestas", { grupo_id: cuestionarioActual.grupo.id, evaluaciones });
  bloquearEnvio(false);

  if (r.ok) {
    olvidarGrupo();
    $("formEncuesta").hidden = true;
    $("confirmacion").hidden = false;
    $("confirmacion").scrollIntoView({ block: "start" });
    return;
  }
  if (r.status === 403) {                                // la autorización expiró o cambió la contraseña: se vuelve al paso 1
    volverAlInicio(r.error + " Vuelve a escribir la contraseña.");
    return;
  }
  if (r.status === 409 || r.status === 429) {            // límite alcanzado, sin alumnos o demasiados envíos
    volverAlInicio(r.error);
    return;
  }
  // 400 u otro: las respuestas se conservan en pantalla para corregir y reintentar
  if (r.errores && r.errores.evaluaciones) $("e-envio").textContent = r.errores.evaluaciones;
  else $("e-envio").textContent = `No se pudo guardar la encuesta: ${r.error} Tus respuestas siguen en pantalla.`;
});

function volverAlInicio(mensaje) {
  olvidarGrupo();
  $("paso1").hidden = false;
  $("e-acceso").textContent = mensaje || "";
  $("campoClave").hidden = !$("grupo").value;
  $("botonesAcceso").hidden = !$("grupo").value;
  window.scrollTo({ top: 0 });
}

$("btnCancelar").addEventListener("click", () => {
  if (enviando) return;
  if (confirm("¿Salir sin enviar? Se perderán las respuestas capturadas.")) volverAlInicio("");
});

$("btnOtra").addEventListener("click", () => {
  $("grupo").value = "";
  $("campoClave").hidden = true;
  $("botonesAcceso").hidden = true;
  $("confirmacion").hidden = true;
  $("paso1").hidden = false;
  window.scrollTo({ top: 0 });
});
