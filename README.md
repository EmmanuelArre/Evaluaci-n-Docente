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
├── tests/                22 pruebas de integración (pytest) contra MySQL real
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
| Formato de grupo `AAA0000` (RG-02 de los requerimientos) | **Conservado** (ver nota abajo) |
| `localStorage` | **Eliminado**: todo va a MySQL por medio de la API |
| Campos Profesor y Materia (texto libre) | **Reemplazados** por combos dependientes cargados desde MySQL |
| Enlace/botón "Ver reporte" en la pantalla del alumno; "Nueva encuesta (borrar todo)" | **Eliminados**; el ✕ individual queda solo para el administrador, con confirmación |
| `reporte.html` / `reporte.js` | **Adaptados**: 4 reportes con combobox, protegidos por sesión |
| Documentos DOCX | **Intactos** |

### Base de datos (`evaluacion_docente`)

`grupos` · `profesores` · `materias` · `profesor_materia` · `preguntas` · `evaluaciones` · `respuestas` · `administradores` · `sesiones`

- `evaluaciones` apunta a `grupos` y a `profesor_materia (profesor_id, materia_id)` mediante llave foránea compuesta:
  **MySQL mismo impide** guardar una materia que no pertenece al profesor.
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

### Nota sobre el formato de grupo

La clave `AAA0000` (3 letras + 4 dígitos, ej. `GSI0252`) viene de los requerimientos (RG-02) y se conservó.
**Una clave como `GTID244` (4 letras + 3 dígitos) NO cumple ese formato.** Si tu escuela usa ese formato, hay que cambiar la expresión
regular y su mensaje en: `app/validar.py` (`RE_GRUPO`), `database/schema.sql` (`ck_grupos_clave`), `index.html` y `admin.html`
(atributo `pattern`), y `js/captura.js` / `js/admin.js` (`reGrupo`).

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
| `pip install -r requirements-dev.txt` y `pytest` | Pruebas de integración (requieren una base de pruebas; ver [PRUEBAS.md](PRUEBAS.md)) |
