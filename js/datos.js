"use strict";
// Utilidades compartidas por todas las pantallas.
// Antes este archivo guardaba los datos en localStorage; ahora toda lectura/escritura
// pasa por la API del backend (que es la única que habla con MySQL).
const $ = id => document.getElementById(id);
const media = a => a.reduce((s, x) => s + x, 0) / a.length;
// Un decimal; el pequeño ajuste evita que un empate exacto (p. ej. 8.45) se redondee hacia abajo por binario
const f1 = n => (Math.round(n * 10 + 1e-9) / 10).toFixed(1);

// ---- Nombres de personas (misma regla que app/validar.py; el servidor es quien decide en última instancia) ----
const PARTICULAS_NOMBRE = new Set(["de", "del", "la", "las", "los", "y", "van", "von", "der", "den", "da", "das", "do", "dos", "di", "du"]);
const LETRAS_NOMBRE = "A-Za-zÀ-ÖØ-öø-ÿ";
const rePalabraNombre = new RegExp(`^[${LETRAS_NOMBRE}]+(?:[-'’][${LETRAS_NOMBRE}]+)*\\.?$`);
const PARTICULAS_MATERIA = new Set(["de", "del", "la", "las", "los", "el", "y", "e", "o", "u", "a", "al", "en", "con", "para", "por"]);
const reRomano = /^\(?(?:I{1,3}|IV|V|VI{1,3}|IX|X)\)?$/;
function normalizarNombre(s, materia = false) {
  const seps = materia ? "-'’(/.,:;&+#" : "-'’";
  const escapados = seps.replace(/[\\\]^-]/g, "\\$&");
  const patron = new RegExp(`(^|[${escapados}])([^${escapados}])`, "g");
  return String(s).normalize("NFC").trim().replace(/\s+/g, " ").split(" ").map((palabra, i) => {
    const bajo = palabra.toLowerCase();
    if (materia && reRomano.test(palabra)) return palabra;
    if (i > 0 && (materia ? PARTICULAS_MATERIA : PARTICULAS_NOMBRE).has(bajo)) return bajo;
    return bajo.replace(patron, (_, sep, letra) => sep + letra.toUpperCase());
  }).join(" ");
}
// Devuelve { nombre, error }: el nombre ya normalizado o el mensaje de por qué no es válido
function validarNombrePersona(valor, etiqueta, minimo, maximo, minPalabras = 1) {
  const n = normalizarNombre(valor);
  if (!n) return { nombre: "", error: `${etiqueta} es obligatorio.` };
  if (n.length < minimo) return { nombre: n, error: `Mínimo ${minimo} caracteres.` };
  if (n.length > maximo) return { nombre: n, error: `Máximo ${maximo} caracteres.` };
  if (n.split(" ").length < minPalabras) return { nombre: n, error: "Escribe al menos un nombre y un apellido." };
  if (!n.split(" ").every(p => rePalabraNombre.test(p)))
    return { nombre: n, error: "Solo letras, espacios, guion, apóstrofo y punto después de una inicial (ej. J.)." };
  return { nombre: n, error: "" };
}

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
// Materias: misma normalización que los profesores; se conservan dígitos y puntuación habituales
function validarNombreMateria(valor) {
  const n = normalizarNombre(valor, true);
  if (!n) return { nombre: "", error: "La materia es obligatoria." };
  if (n.length < 3) return { nombre: n, error: "Mínimo 3 caracteres." };
  if (n.length > 60) return { nombre: n, error: "Máximo 60 caracteres." };
  if (!/^[\p{L}\p{N} .,:;()\-/&'+#]+$/u.test(n)) return { nombre: n, error: "Contiene caracteres no permitidos." };
  if (!/\p{L}/u.test(n)) return { nombre: n, error: "Debe contener letras." };
  return { nombre: n, error: "" };
}

// ---- Partes del nombre de un profesor (misma regla que app/validar.py:datos_profesor; el servidor decide) ----
const MAX_NOMBRES_PILA = 5, MAX_PALABRAS_APELLIDO = 3, MAX_LARGO_NOMBRES = 60, MAX_LARGO_APELLIDO = 28;
// Devuelve { valor, error }. `valor` ya está normalizado; vacío y opcional = sin error.
function validarParteNombre(texto, etiqueta, maximo, maxPalabras, requerido, plural = false) {
  const n = normalizarNombre(texto == null ? "" : texto);
  if (!n) return { valor: "", error: requerido ? `${etiqueta} es obligatorio.` : "" };
  if (n.length < 2) return { valor: n, error: "Mínimo 2 caracteres." };
  if (n.length > maximo) return { valor: n, error: `Máximo ${maximo} caracteres.` };
  const palabras = n.split(" ");
  if (!palabras.every(w => rePalabraNombre.test(w)))
    return { valor: n, error: "Solo letras (con acentos y ñ), espacios y guiones; sin números ni otros símbolos." };
  const cuenta = palabras.filter(w => !PARTICULAS_NOMBRE.has(w.toLowerCase())).length;
  if (cuenta === 0) return { valor: n, error: `${etiqueta} no es válido.` };
  if (cuenta > maxPalabras) return { valor: n, error: plural ? `Máximo ${maxPalabras} nombres de pila.` : `Máximo ${maxPalabras} palabras.` };
  return { valor: n, error: "" };
}
// Para profesores registrados antes de separar el nombre: propone nombres / paterno / materno (el administrador lo corrige)
function separarNombre(completo) {
  const pal = normalizarNombre(completo || "").split(" ").filter(Boolean);
  if (pal.length <= 1) return { nombres: pal.join(" "), apellido_paterno: "", apellido_materno: "" };
  // una palabra de apellido = la última más las partículas que la preceden ("De la Cruz")
  const tomar = fin => { let i = fin - 1; while (i > 0 && PARTICULAS_NOMBRE.has(pal[i - 1].toLowerCase())) i--; return i; };
  const iMat = pal.length >= 3 ? tomar(pal.length) : -1;
  if (iMat > 0) {
    const iPat = tomar(iMat);
    if (iPat > 0) return { nombres: pal.slice(0, iPat).join(" "), apellido_paterno: pal.slice(iPat, iMat).join(" "), apellido_materno: pal.slice(iMat).join(" ") };
  }
  const iPat = tomar(pal.length);
  return { nombres: pal.slice(0, iPat).join(" "), apellido_paterno: pal.slice(iPat).join(" "), apellido_materno: "" };
}
function generarClaveAcceso(largo = 10) {
  const alfabeto = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const buf = new Uint32Array(largo);
  crypto.getRandomValues(buf);
  return Array.from(buf, x => alfabeto[x % alfabeto.length]).join("");
}
