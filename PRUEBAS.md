# Pruebas realizadas

Las pruebas se ejecutaron contra un **servidor MySQL 8.0.46 real** (no simulado), con el backend Flask real y un navegador **Chromium** real.
Esto es lo que SÍ se probó, lo que NO, y cómo repetirlo en tu computadora.

## Entorno de prueba

| Componente | Versión |
|---|---|
| MySQL Server | 8.0.46 (Ubuntu 24.04), ejecutando `database/schema.sql` tal como se entrega |
| Python | 3.13 · Flask 3.1 · PyMySQL 1.2 · bcrypt 5.0 · Waitress 3.0 |
| Navegador | Chromium (Playwright) – escritorio 1280 px y móvil 390 px |
| Dependencias | `pip-audit -r requirements.txt` → **sin vulnerabilidades conocidas** |

## 1. Script SQL (`schema.sql`)
- Ejecutado en una base vacía: crea las **9 tablas** y las **12 preguntas** sin errores. ✔
- Ejecutado una **segunda vez**: sin errores y sin duplicar datos (es re-ejecutable). ✔

## 2. Pruebas automáticas de integración (`pytest`) — 22 / 22 ✔

| # | Prueba | Resultado |
|---|---|---|
| 01 | La API responde y conecta con MySQL | ✔ |
| 02 | **19 rutas de administrador (incluidos los 4 reportes y una ruta inexistente) responden 401 sin sesión** | ✔ |
| 03 | `reporte.html` redirige a `admin.html` sin sesión | ✔ |
| 04 | `.env`, `app/`, `run.py`, `requirements.txt`, `database/`, `docs/`, `tests/`, `.venv/` y rutas con `..` no se pueden descargar | ✔ |
| 05 | Login incorrecto → 401 con el mismo mensaje exista o no el usuario; contraseña de más de 72 bytes → 401 (no 500) | ✔ |
| 06 | Login correcto: cookie `HttpOnly` + `SameSite=Strict`, hash bcrypt en la BD, sesión en MySQL (solo huella, no la cookie) | ✔ |
| 07 | Petición de otro origen (CSRF) → 403 | ✔ |
| 08 | Grupos: 8 formatos inválidos rechazados (incl. salto de línea interno), duplicado → 409, mayúsculas automáticas, edición | ✔ |
| 09 | Profesores/materias: validaciones, duplicados, asignación y consulta de materias por profesor | ✔ |
| 10 | Catálogo del alumno: profesores activos; 1 materia / varias / ninguna; profesor inactivo oculto; sin datos sensibles | ✔ |
| 11 | Evaluación válida: **1 evaluación + 12 respuestas** ligadas al grupo/profesor/materia; sin columnas de identificación del alumno | ✔ |
| 12 | Comentario vacío → NULL; 200 caracteres aceptado | ✔ |
| 13 | **25 manipulaciones rechazadas con 400** (grupo inexistente/inválido, inyección SQL, profesor inactivo/inexistente/booleano, materia ajena al profesor, calificación 4/11/7.5/"8"/true/null, 11 o 13 respuestas, comentario de 201…) y **nada se guarda** | ✔ |
| 14 | MySQL rechaza por sí mismo: calificación 4 u 11, pregunta 99, respuesta duplicada, materia ajena al profesor, grupo inexistente, clave en minúsculas o duplicada | ✔ |
| 15 | Historial: no se puede borrar un grupo/profesor/materia/asignación con evaluaciones (409); **desactivar no borra evaluaciones** y deja de recibir nuevas | ✔ |
| 16 | **Reportes con datos de promedio conocido**: 4 tipos, filtros opcionales, promedios por profesor/materia/pregunta, 48 respuestas = 4×12 (**sin duplicar**), errores 400/404 y materia ajena | ✔ |
| 17 | Reportes sin registros → `vacio: true`, promedio `null`, sin error | ✔ |
| 18 | Borrar evaluación (admin) elimina sus 12 respuestas en cascada | ✔ |
| 19 | Cerrar sesión invalida la sesión en el servidor; cookie inventada → 401 | ✔ |
| 20 | Una cookie de sesión ya cerrada no sirve; la sesión expira por inactividad | ✔ |
| 21 | Administrador desactivado no puede entrar, y una sesión abierta pierde acceso al desactivarlo | ✔ |
| 22 | Fuerza bruta: tras 10 intentos fallidos → 429, incluso con la contraseña correcta durante el bloqueo | ✔ |

## 3. Pruebas de interfaz en navegador real — 70 / 70 ✔

Recorrido completo de principio a fin (con capturas de pantalla revisadas a mano). Se ejecutó 6 veces seguidas durante el desarrollo y otras **5 veces seguidas sobre el ZIP final**
extraído en una carpeta limpia (entorno virtual nuevo, base de datos nueva creada con `schema.sql`, `pytest` 22/22): todas las corridas 70/70.

- **Alumno:** botón *Administrador* visible; sin enlace a reportes ni tablas/promedios; combo de profesores cargado desde MySQL; materia deshabilitada hasta
  elegir profesor; **1 materia se autoselecciona**, varias → elige, **ninguna → mensaje informativo**; solo aparecen las materias del profesor.
- **Validaciones:** envío vacío con error por campo; grupo con formato inválido; grupo en mayúsculas; contador 200/200; `maxlength`; atributos HTML
  (`required`, `pattern`, `minlength`); falta 1 de 12 preguntas indica cuál; grupo inexistente → error del backend en el campo y respuestas conservadas.
- **Guardado:** confirmación visible; 12 respuestas en MySQL; **error de red → mensaje para reintentar y los datos siguen en pantalla**;
  **doble clic → un solo registro** (con retardo artificial de 0.8 s).
- **Administrador:** login vacío/incorrecto/correcto; cookie `httpOnly` (invisible a `document.cookie`); alta, edición, duplicado y baja de grupos con
  confirmación; alta de materias y profesores, validación de nombre corto; asignación de materias; tabla con materias por profesor.
- **Acceso:** un alumno que abre `reporte.html` es enviado al login; su llamada a la API de reportes → 401; tras *Cerrar sesión* todo vuelve a bloquearse.
- **Reportes:** los cuatro tipos con combobox; materia dependiente (solo las del profesor); combos obligatorios/opcionales según el reporte;
  promedio general igual al calculado por SQL; gráfica de 12 barras; tabla por profesor/materia con P1–P12 en el reporte general; filtros exactos;
  mensaje informativo cuando no hay coincidencias; borrar evaluación con confirmación y recálculo; la impresión oculta controles.
- **Móvil (390 px):** sin desbordamiento horizontal.
- **CSP:** las páginas funcionan con la política de seguridad activa; solo aparece el 401 esperado al comprobar sesión en la pantalla de login.
- **`python crear_admin.py`** en terminal interactiva: la contraseña no se muestra, rechaza claves débiles o que no coinciden, guarda hash bcrypt de 60 caracteres.

### Hallazgos durante la migración a Flask
- **Orden en el panel:** el formulario se limpiaba *después* de recargar las tablas, y una persona (o un script) muy rápida podía perder lo que acababa de teclear.
  Ahora se limpia en cuanto el guardado tiene éxito (`js/admin.js`).
- **Filas afectadas en MySQL:** PyMySQL reporta 0 filas cuando un `UPDATE` no cambia valores (p. ej. desactivar algo ya desactivado); se verifica la existencia
  antes de responder 404, para no dar falsos «no existe».
- **Fechas:** Flask serializa `datetime` en formato RFC 822/GMT por defecto, lo que desplazaría la hora en el navegador; se usa ISO 8601 local.
- **Promedios:** se calculan en doble precisión en SQL (`AVG(calificacion + 0e0)`) y `f1()` redondea empates exactos (8.45 → 8.5) de forma estable.

## 4. Lo que NO se pudo probar (tendrás que verificarlo tú)

| Pendiente | Cómo probarlo |
|---|---|
| **La interfaz de MySQL Workbench en sí** (no existe en el entorno de prueba). El script se ejecutó con el cliente `mysql` del mismo servidor 8.0, pero no dentro de Workbench | Sigue los pasos 2–4 de [INSTALACION_MYSQL.md](INSTALACION_MYSQL.md) |
| Windows y macOS (se probó en Linux): activación del entorno virtual, `py`/`python`, instalación de `bcrypt`/`cryptography` | Pasos 5–8 de la guía; si `pip install` falla, envía el mensaje de error |
| Firefox, Safari y Edge (solo Chromium) | Recorre manualmente los pasos 9–11 |
| HTTPS con `COOKIE_SECURE=true`, proxy inverso y despliegue en servidor | No se probó; ver nota al final de la guía |
| Carga (muchos alumnos a la vez) | No se probó; Waitress corre con 8 hilos y cada petición abre su propia conexión a MySQL. El límite de 300 envíos / 10 min por IP es ajustable en `app/__init__.py` |
| Más de un proceso/servidor a la vez | El limitador de intentos vive en memoria de un solo proceso; no está pensado para varios procesos |
| Versiones de MySQL distintas de 8.0.x (p. ej. MariaDB) | El script usa `CHECK` y `FOR SHARE`: requiere MySQL 8.0.16+ |

## 5. Cómo ejecutar las pruebas automáticas en tu computadora (opcional)

Las pruebas **borran el contenido** de la base que usen, por eso exigen una base distinta cuyo nombre termine en `_test` y se niegan a correr en `evaluacion_docente`.

1. En Workbench abre `database/schema.sql`, y antes de ejecutarlo reemplaza (Ctrl+H) `evaluacion_docente` por `evaluacion_docente_test`. Ejecútalo.
2. Si usas el usuario `evaluacion_app`, dale permisos también sobre la base de pruebas:
   `GRANT SELECT, INSERT, UPDATE, DELETE ON evaluacion_docente_test.* TO 'evaluacion_app'@'localhost';`
3. Con el entorno virtual activo: `pip install -r requirements-dev.txt` y luego `pytest`.
   Toma usuario/contraseña de tu `.env` y usa la base `evaluacion_docente_test` (se puede cambiar con la variable `TEST_DB_NAME`).
   Debe terminar con `22 passed`.

## 6. Lista de comprobación manual rápida (10 minutos)

1. Crear grupo `GSI0252`, 2 materias y 2 profesores (uno con 2 materias, otro con 1) y asignarlas.
2. En la encuesta: elegir el profesor de 1 materia → se autoselecciona; el de 2 → elegir; intentar enviar vacío → errores por campo.
3. Guardar 3 evaluaciones y comprobar en Workbench que `evaluaciones` tiene 3 filas y `respuestas` 36.
4. Intentar abrir `http://localhost:3000/reporte.html` sin sesión → debe enviarte al login.
5. Como administrador, generar los 4 reportes y comparar un promedio con `SELECT AVG(calificacion) FROM respuestas;`.
6. Desactivar un profesor → ya no aparece en la encuesta pero sus evaluaciones siguen en los reportes.
