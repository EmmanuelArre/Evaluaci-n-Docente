"use strict";
// Utilidades compartidas por todas las pantallas.
// Antes este archivo guardaba los datos en localStorage; ahora toda lectura/escritura
// pasa por la API del backend (que es la única que habla con MySQL).
const $ = id => document.getElementById(id);
const media = a => a.reduce((s, x) => s + x, 0) / a.length;
// Un decimal; el pequeño ajuste evita que un empate exacto (p. ej. 8.45) se redondee hacia abajo por binario
const f1 = n => (Math.round(n * 10 + 1e-9) / 10).toFixed(1);

function hoy() {
  return new Date().toLocaleDateString("es-MX", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// Llamada a la API. Siempre devuelve { ok, status, datos, error, errores } y nunca lanza excepción.
async function api(metodo, url, cuerpo) {
  const opciones = { method: metodo, credentials: "same-origin", headers: {} };
  if (cuerpo !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  let resp;
  try {
    resp = await fetch(url, opciones);
  } catch (e) {
    return { ok: false, status: 0, datos: null, errores: null,
      error: "No se pudo conectar con el servidor. Verifica que esté en ejecución e inténtalo de nuevo." };
  }
  let datos = null;
  try { datos = await resp.json(); } catch (e) { /* respuesta sin JSON */ }
  return {
    ok: resp.ok, status: resp.status, datos,
    error: resp.ok ? "" : (datos && datos.error) || "Error inesperado del servidor.",
    errores: (datos && datos.errores) || null
  };
}

// Rellena un <select> con { id, nombre } y una opción inicial
function llenarSelect(sel, items, textoInicial, etiqueta) {
  sel.innerHTML = "";
  const o0 = document.createElement("option");
  o0.value = ""; o0.textContent = textoInicial;
  sel.appendChild(o0);
  items.forEach(it => {
    const o = document.createElement("option");
    o.value = it.id;
    o.textContent = etiqueta ? etiqueta(it) : it.nombre;
    sel.appendChild(o);
  });
}

// ---- Sesión de administrador (la protección real está en el servidor; esto solo ajusta la pantalla) ----
async function exigirAdmin() {
  const r = await api("GET", "/api/admin/me");
  if (!r.ok) { window.location.href = "admin.html"; return null; }
  return r.datos;
}
async function cerrarSesion() {
  await api("POST", "/api/admin/logout", {});
  window.location.href = "admin.html";
}
