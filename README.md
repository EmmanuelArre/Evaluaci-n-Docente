# Encuesta de Evaluación Docente (UTNG) – Python + Flask + MySQL

Sistema web de evaluación docente. Los alumnos contestan la encuesta anónima (12 preguntas, escala 5–10) y las
respuestas se guardan en una base de datos **MySQL** (`evaluacion_docente`) administrada desde **MySQL Workbench**.
El backend está hecho en **Python con Flask**. Los reportes y la administración de grupos, profesores y materias son
exclusivos del **administrador**.

> **Importante:** el sistema ya no se abre con doble clic en `index.html`. Hay que iniciar el backend
> (`python run.py`) y entrar a **http://localhost:3000**. El navegador nunca se conecta a MySQL; solo el backend lo hace.

## Inicio rápido (detalle completo en [INSTALACION_MYSQL.md](INSTALACION_MYSQL.md))

```
1. Ejecuta database/schema.sql en MySQL Workbench
   (si ya tenías la base de una versión anterior: ejecuta `database/migracion_asignaciones.sql` en lugar de recrearla)
2. python -m venv .venv   y activa el entorno   (Windows CMD: .venv\Scripts\activate)
3. pip install -r requirements.txt
4. copia .env.example a .env y completa los datos
5. python crear_admin.py      (crea el primer administrador; la contraseña se pide sin mostrarse)
6. python run.py              → http://localhost:3000
```

## Estructura

```
evaluacion docente/
├── index.html            Encuesta del alumno (grupo, combo de profesor, combo de materia, 12 preguntas)
├── admin.html            Acceso de administrador + gestión de grupos, profesores y materias
├── reporte.html          Reportes (solo con sesión de administrador)
├── css/styles.css        Estilos originales + bloque añadido al final
├── js/config.js          Las 12 preguntas y la escala 5–10
├── js/datos.js           Utilidades compartidas; llama a la API (ya no usa localStorage)
├── js/captura.js         Formulario del alumno (validaciones originales + nuevas, envío a la API)
├── js/admin.js           Login y CRUD del administrador
├── js/reporte.js         Gráfica, tablas y cálculos originales, alimentados por la API
├── app/                  Backend Flask
│   ├── __init__.py           fábrica de la app, control de acceso, cabeceras de seguridad, archivos estáticos
│   ├── config.py · db.py · errores.py · validar.py · limitador.py
│   ├── sesion.py             sesiones del administrador guardadas en MySQL
│   ├── rutas_publico.py      catálogo del alumno + guardar evaluación
│   ├── rutas_auth.py         login / logout / sesión
│   ├── rutas_admin.py        CRUD de grupos, profesores, materias y asignaciones
│   └── rutas_reportes.py     los 4 reportes (consultas SQL)
├── run.py                Inicia el servidor (Waitress)
├── crear_admin.py        Crea el primer administrador / restablece una contraseña
├── database/schema.sql   Script para MySQL Workbench (tablas, llaves, índices, 12 preguntas)
├── database/migracion_asignaciones.sql  Actualiza una base ya creada: agrega `asignaciones` sin borrar datos
├── normalizar_nombres.py Corrige el formato de nombres ya guardados (vista previa; `--aplicar` para guardar)
├── tests/                39 pruebas de integración (pytest) contra MySQL real, incluidos los 12 escenarios de filtrado profesor–grupo
├── docs/                 DOCX originales, SIN modificar
├── img/                  Imágenes originales
├── requirements.txt · requirements-dev.txt · .env.example · .gitignore
├── INSTALACION_MYSQL.md  Guía paso a paso (los 11 puntos)
└── PRUEBAS.md            Pruebas realizadas, resultados y lo que NO se pudo probar
```

## Qué se conservó, modificó y agregó

| Elemento | Estado |
|---|---|
| 12 preguntas oficiales, escala 5–10, obligatoriedad, comentario ≤ 200 con contador | **Conservado** (mismos textos, mismo `config.js`) |
| Diseño, responsive, gráfica de barras, tabla por alumno, promedios con 1 decimal, imprimir | **Conservado** |
| Formato de grupo | **Cambiado** a `AAAA000` (4 letras + 3 dígitos, ej. `GTID244`); ver nota abajo |
| Combo de grupo en la encuesta | **Nuevo**: el grupo se elige de una lista y de él dependen los profesores y las materias |
| `localStorage` | **Eliminado**: todo va a MySQL por medio de la API |
| Campos Profesor y Materia (texto libre) | **Reemplazados** por combos dependientes cargados desde MySQL |
| Enlace/botón "Ver reporte" en la pantalla del alumno; "Nueva encuesta (borrar todo)" | **Eliminados**; el ✕ individual queda solo para el administrador, con confirmación |
| `reporte.html` / `reporte.js` | **Adaptados**: 4 reportes con combobox, protegidos por sesión |
| Documentos DOCX | **Intactos** |

### Base de datos (`evaluacion_docente`)

`grupos` · `profesores` · `materias` · `profesor_materia` · `asignaciones` · `preguntas` · `evaluaciones` · `respuestas` · `administradores` · `sesiones`

- `asignaciones (grupo_id, profesor_id, materia_id)` dice **quién da qué materia a qué grupo** (muchos a muchos). Su llave primaria impide
  duplicados y su llave foránea a `profesor_materia` impide asignar una materia que el profesor no imparte. `activo` permite retirar una
  asignación conservando el historial.
- `evaluaciones` apunta a `asignaciones (grupo_id, profesor_id, materia_id)` mediante llave foránea compuesta:
  **MySQL mismo impide** guardar una evaluación a un profesor/materia que no corresponde al grupo.
- `respuestas` tiene llave primaria `(evaluacion_id, num_pregunta)`, `CHECK` de 5 a 10 y llave foránea a `preguntas`.
- Las llaves foráneas hacia grupos/profesores/materias son `RESTRICT`: **no se pueden borrar registros con historial**;
  se **desactivan** (columna `activo`) y las evaluaciones se conservan.
- La evaluación es anónima: ninguna columna identifica al alumno.
- Equivalencia con el diccionario de datos: `ALUMNO_ENCUESTA` → `evaluaciones`, `RESPUESTA` → `respuestas`, `PREGUNTA` → `preguntas`.
  `REPORTE` ya no es una tabla: cada reporte se calcula con SQL.

### Seguridad

- Contraseñas con **bcrypt** (coste 12); nunca en el código ni en el navegador.
- **Sesión en el servidor** (tabla `sesiones`): la cookie (`httpOnly`, `SameSite=Strict`) solo trae un identificador aleatorio;
  en la base se guarda su huella HMAC, no el valor de la cookie. Se crea una sesión nueva en cada inicio, **cerrar sesión la borra al instante**,
  expira por inactividad (`SESSION_MINUTOS`) y deja de servir si el administrador se desactiva.
- **Un único punto de control** (`before_request`) exige sesión en TODA ruta `/api/admin/*` (incluidos los reportes y rutas inexistentes) → 401 sin ella.
  `reporte.html` redirige al login.
- Límite de intentos de login (10 fallidos / 15 min por IP), verificación de origen en peticiones que modifican datos,
  cabeceras de seguridad (CSP, nosniff, anti-iframe, sin caché en la API de administrador), consultas SQL siempre parametrizadas,
  y el servidor solo entrega `index/admin/reporte.html`, `css/`, `js/` e `img/` (`.env`, `app/`, `database/`, `docs/`, `tests/` no son accesibles por HTTP).
- El servidor repite todas las validaciones y rechaza datos manipulados (grupo inexistente, materia ajena al profesor,
  calificaciones fuera de 5–10 o no enteras, ≠ 12 respuestas, comentarios > 200…).

### Encuesta única por grupo, límite y contraseña de acceso

- **Flujo del alumno:** elige grupo → escribe la contraseña de ESE grupo (`POST /api/grupos/<id>/acceso`; la verifica Flask) → solo entonces
  `GET /api/grupos/<id>/cuestionario` entrega la tabla de profesores/materias y las preguntas → `POST /api/encuestas` guarda **una encuesta**
  con la evaluación de todos los profesores del grupo en una sola transacción. No existe ningún endpoint público con «todos los profesores».
- **Autorización temporal:** al acertar la contraseña el servidor crea una fila en `sesiones` y una cookie `ed.acc` (HttpOnly, SameSite=Strict) con un token
  aleatorio; la contraseña nunca se guarda en el navegador ni viaja en la URL. Se revalida al enviar (mismo grupo, contraseña vigente) y se consume al guardar.
  Cambiar la contraseña de un grupo revoca las autorizaciones abiertas de ese grupo.
- **Contraseñas de grupo:** se guardan **cifradas de forma reversible** (Fernet, paquete `cryptography`) en `grupos.acceso_cifrado`, para que el administrador
  pueda consultarlas siempre. La clave está en `CLAVE_CIFRADO_ACCESO` (`.env` / variable de entorno), nunca en el código ni en el repositorio; con la base de datos
  sola no se pueden leer. Solo `GET /api/admin/grupos` (sesión de administrador, `no-store`) las descifra. No salen en pantallas de alumnos, reportes, errores ni logs.
  Fuerza bruta: 8 intentos fallidos por IP+grupo y 60 por grupo en la ventana → 429. En producción usa HTTPS (`COOKIE_SECURE=true`).
- **Límite:** encuestas válidas del grupo ≤ alumnos del grupo. Una encuesta de varios profesores cuenta **una** vez. El conteo y el INSERT ocurren bajo
  `SELECT … FOR UPDATE` sobre la fila del grupo, así que dos envíos simultáneos no ocupan la misma última plaza. Con 0 alumnos no se aceptan encuestas; con más
  encuestas que alumnos (inconsistencia) se bloquea y el panel muestra 0 disponibles, nunca un negativo. Reducir los alumnos por debajo de las encuestas existentes se rechaza (409); nada se borra solo.
- **Anonimato:** ninguna tabla de encuestas guarda nombre, matrícula, correo, IP ni identificador. La contraseña es compartida por el grupo, por lo que **no se puede impedir que
  una misma persona conteste dos veces**: solo se respeta el tope total del grupo.
- **Reportes:** `encuestas` = envíos completos (`COUNT(DISTINCT encuesta_id)`), `evaluaciones` = profesor-materia evaluadas, `respuestas` = calificaciones individuales; los promedios se
  calculan sobre las respuestas y los filtros por grupo/profesor/materia siguen funcionando.
- **Profesores:** nombre(s) (1 a 5), apellido paterno (obligatorio) y apellido materno (opcional), con la misma validación en el navegador y en Flask. `profesores.nombre` conserva el nombre completo.

### Formato de nombres

Los nombres de personas (profesores y administradores) se guardan como `Nombre Apellido`: sin espacios sobrantes, primera letra de cada
palabra en mayúscula y partículas (`de`, `del`, `la`, `los`, `y`…) en minúscula (`Juan Carlos de la Cruz`). Se normaliza en el formulario y
de nuevo en el servidor (`app/validar.py`, `js/datos.js`). Para corregir nombres antiguos: `python normalizar_nombres.py` (vista previa) y
`python normalizar_nombres.py --aplicar`. El script no modifica identificadores ni relaciones y se detiene si dos registros quedarían idénticos.
El nombre de un profesor debe tener al menos un nombre y un apellido (dos palabras; una inicial como `J.` cuenta). `normalizar_nombres.py`
avisa de los profesores ya guardados con una sola palabra, sin modificarlos, para que los completes a mano.
Los nombres de materia usan la misma normalización y validación (obligatorio, 3 a 60 caracteres, sin espacios sobrantes, `Bases de Datos`,
`Introducción a la Programación`) y conservan dígitos y puntuación (`Inglés 2`, `Cálculo (I)`). Los números romanos solo se respetan si se escriben
en mayúsculas (`II`); siglas como `POO` quedan como `Poo`. Las claves de grupo no se transforman (se guardan en mayúsculas).

### Nota sobre el formato de grupo

La clave de grupo es `AAAA000` (4 letras + 3 dígitos, ej. `GTID244`). La versión anterior de `schema.sql` exigía `AAA0000`, aunque la
validación del servidor y de las pantallas ya aceptaba `AAAA000`; por eso la base rechazaba grupos como `GTID244`. `schema.sql` y
`migracion_asignaciones.sql` ya lo corrigen. Si cambias de formato otra vez, hay que modificarlo en `app/validar.py` (`RE_GRUPO`),
`database/schema.sql` (`ck_grupos_clave`), `index.html`/`admin.html` (`pattern`) y `js/admin.js` (`reGrupo`).

### Nota sobre los DOCX

Se dejaron intactos, como pediste. Describen la versión anterior, así que **ya no coinciden en estos puntos**:
RNF-01 («sin dependencias externas»), «los datos se comparten mediante localStorage», RF-08 (eliminar capturas, ahora solo administrador)
y la entidad `REPORTE` del diccionario (ahora derivada con SQL). Funcionalidad nueva sin documentar: administrador,
grupos/profesores/materias administrables y 4 reportes por combobox.

## Comandos

| Comando | Para qué |
|---|---|
| `pip install -r requirements.txt` | Instala las dependencias (con el entorno virtual activo) |
| `python run.py` | Inicia el sistema en `http://localhost:3000` |
| `python crear_admin.py` | Crea un administrador o restablece su contraseña |
| `python generar_clave.py` | Genera la clave `CLAVE_CIFRADO_ACCESO` para el `.env` |
| `pip install -r requirements-dev.txt` y `pytest` | Pruebas de integración (requieren una base de pruebas; ver [PRUEBAS.md](PRUEBAS.md)) |
