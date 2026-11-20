# Pruebas realizadas

Resultado de la última ejecución real: **59 pruebas automáticas, 59 aprobadas** (`pytest`, 17 s) y una prueba de extremo a extremo en Chromium con **18 comprobaciones, sin fallas**.

## Entorno (leer antes de confiar en los resultados)

| Componente | Detalle |
|---|---|
| Base de datos | **MariaDB 10.11.14**, no MySQL 8. El entorno de pruebas no tenía MySQL 8. |
| Diferencia cubierta | MySQL 8 admite `SELECT … FOR SHARE`; MariaDB 10.11 no. Las pruebas cargan un pequeño adaptador (solo de pruebas, no forma parte del sistema) que traduce esa cláusula a `LOCK IN SHARE MODE`. Los bloqueos `FOR UPDATE` que protegen el límite se ejecutaron tal cual. |
| Python / navegador | Python 3.13, Flask, PyMySQL, `cryptography` (Fernet); Chromium con Playwright (escritorio 1100–1200 px y móvil 390 px) |
| **No probado** | Ejecución sobre MySQL 8 real (ni el `schema.sql` ni `migracion_encuestas.sql`); Workbench; HTTPS real; varios procesos de servidor a la vez (el limitador de intentos está en memoria de un solo proceso). |

## Cómo repetirlas

1. Crea una base cuyo nombre termine en `_test` (las pruebas **borran** sus tablas) y ejecuta `database/schema.sql` en ella.
2. Exporta `DB_USER`, `DB_PASSWORD`, opcionalmente `TEST_DB_NAME`, y ten `CLAVE_CIFRADO_ACCESO` en el `.env`.
3. `pip install -r requirements-dev.txt` y `pytest`.

## Qué cubren las 59 pruebas

**`tests/test_api.py` (23)** – API, sesión de administrador, grupos y profesores, asignaciones, acceso del alumno, guardado de la encuesta (1 encuesta + N evaluaciones + 12·N respuestas), datos manipulados, restricciones de MySQL (llaves foráneas, `CHECK`, único), historial protegido, reportes y cálculos de promedio, cierre y caducidad de sesión, fuerza bruta de login.

**`tests/test_escenarios.py` (16)** – Filtrado profesor–grupo detrás de la contraseña: un grupo con 7 profesores muestra exactamente esos 7; los de otros grupos no aparecen; cambiar de grupo cambia la lista; grupo sin profesores; profesor ajeno o materia ajena rechazados aunque se manipule la solicitud; sin duplicados; normalización de nombres; campos vacíos; encuestas válidas e inválidas; fallo de la consulta sin datos ajenos; quitar/desactivar asignaciones; nombres de profesor (nombre(s) 1–5, paterno obligatorio, materno opcional con `None`, `""` u omitido; acentos, ñ, guion; rechazo de dígitos, símbolos y seis nombres).

**`tests/test_encuestas.py` (20)** – Spec de límite y contraseñas:
- Tabla y cuestionario solo tras la contraseña; grupo inexistente o manipulado.
- Calificaciones: aceptan 5 y 10; rechazan 4, 11, 7.5, `"8"`, `null`, `true`, 0, −1; pregunta o profesor faltante no cuenta.
- Una encuesta de 3 profesores cuenta una vez (+1 encuesta, +3 evaluaciones, +36 respuestas).
- **Límite con 35 alumnos:** 34 encuestas aceptadas, la 35.ª entra, la 36.ª se rechaza con la contraseña correcta; una autorización abierta antes del límite tampoco lo supera.
- **Concurrencia:** 8 envíos simultáneos (hilos con barrera) por la última plaza de un grupo de 5 → exactamente un 201 y 5 encuestas en total.
- Grupo con 0 alumnos; inconsistencia (más encuestas que alumnos) bloquea y muestra 0 disponibles; reducir alumnos por debajo de las encuestas → 409 sin borrar nada; validación de alumnos (0, negativos, decimales, texto, booleanos, 501) y de la clave de grupo.
- **Anonimato:** las tablas de encuestas no tienen columnas de identidad; `encuestas` solo tiene `id`, `grupo_id`, `creado_en`; la fila de autorización solo guarda grupo y versión.
- **Contraseñas (§18.8):** asignar, consultar y modificar; la anterior deja de servir y revoca autorizaciones abiertas; la de otro grupo no abre; unicidad entre grupos; sin contraseña → acceso no disponible; sin sesión de administrador → 401 sin contraseñas en el cuerpo; guardar sin autorización, con cookie inventada o de otro grupo → 403; la autorización se consume al enviar (reenvío → 403); fuerza bruta → 429 incluso con la contraseña correcta; las contraseñas no aparecen en respuestas públicas, reportes, logs capturados ni en la base (solo texto cifrado `gAAAA…`); cookie `HttpOnly` y `SameSite=Strict`.

## Prueba de extremo a extremo (Chromium, servidor real con waitress)

Panel de administración: alta de materia, de profesores con tres campos (validación en el navegador de dígitos, apellido vacío y seis nombres), de un grupo con 2 alumnos y contraseña generada, que queda visible en la tabla; asignaciones. Alumno: sin grupo no hay contraseña ni cuestionario; contraseña incorrecta no da acceso y el campo se limpia; con la correcta aparece la tabla numerada y 24 preguntas (2 profesores × 12) con botones 5, 6, 7, 8, 9 y 10, ninguno marcado por defecto; la contraseña no aparece en `localStorage`, `sessionStorage`, cookies legibles ni URL; encuesta incompleta no se envía; envío completo; cambiar de grupo borra el cuestionario; tras 2 encuestas el acceso se bloquea aunque la contraseña sea correcta; sin desbordamiento horizontal a 390 px.

## Limitaciones sin resolver

- No se puede impedir que una persona conteste varias veces: la encuesta es anónima y la contraseña es compartida. Solo se respeta el tope por grupo.
- Los grupos migrados quedan con 0 alumnos y sin contraseña hasta que el administrador los capture. Las encuestas anteriores se reconstruyeron con el mínimo posible de envíos, porque el número real nunca se guardó; revisa la tabla de estado que muestra la migración.
- Si se pierde `CLAVE_CIFRADO_ACCESO`, las contraseñas guardadas no se pueden recuperar y hay que asignarlas de nuevo.
- El limitador de intentos vive en la memoria del proceso: se reinicia con el servidor y no se comparte entre varios procesos.
- La pantalla del alumno se verificó en Chromium; no se probó en otros navegadores.
