# Guía de instalación y uso con MySQL Workbench

> **Idea clave:** MySQL Workbench es solo la herramienta para *administrar* la base de datos. Quien guarda y lee los datos
> es el **servidor MySQL**, y debe estar **encendido** cada vez que uses el sistema. El navegador habla con el backend
> (Python + Flask), y el backend habla con MySQL.

```
Navegador ──► Backend Flask (localhost:3000) ──► Servidor MySQL (localhost:3306)
                                                        ▲
                                  MySQL Workbench (solo para revisar/administrar)
```

**Requisitos:** MySQL Server 8.0 o superior, MySQL Workbench, y [Python](https://www.python.org/downloads/) 3.10 o superior
(probado con 3.13; en Windows marca la casilla **Add python.exe to PATH** al instalarlo). Comprueba con `python --version`
(en Windows también sirve `py --version`).
Los comandos se escriben en una terminal (CMD, PowerShell o Terminal) **dentro de la carpeta del proyecto**.

---

## 1. Comprobar que el servidor MySQL está instalado y activo

**Windows**
1. Presiona `Win + R`, escribe `services.msc` y Enter.
2. Busca un servicio llamado **MySQL80** (o `MySQL`). En *Estado* debe decir **En ejecución**.
   Si no, clic derecho → **Iniciar**.
3. Alternativa en PowerShell: `Get-Service MySQL*` (debe mostrar `Running`).

**macOS:** *Ajustes del Sistema → MySQL* debe mostrar «MySQL is running» (si no, botón *Start MySQL Server*).

**En Workbench:** al abrir la pantalla de inicio, entra a tu conexión local. Si conecta, el servidor está activo.
Dentro, *Navigator → Administration → Server Status* debe decir **Server is running**.

Si MySQL no está instalado, descárgalo con **MySQL Installer** (Windows) o el paquete DMG (macOS) y durante la instalación
define la contraseña de `root`; **anótala**.

## 2. Crear o usar una conexión local en Workbench

1. En la pantalla de inicio, si ya existe **Local instance MySQL80**, haz doble clic, escribe la contraseña de `root` y listo.
2. Si no existe: clic en el **+** junto a *MySQL Connections* y llena:
   - **Connection Name:** `Evaluacion Docente local`
   - **Hostname:** `127.0.0.1`  ·  **Port:** `3306`  ·  **Username:** `root`
3. Clic en **Test Connection** → escribe la contraseña → debe decir *Successfully made the MySQL connection* → **OK**.
4. Haz doble clic sobre la conexión para abrirla.

## 3. Ejecutar el script SQL

1. En Workbench: **File → Open SQL Script…** y elige `database/schema.sql` del proyecto.
2. No selecciones nada y presiona el **rayo ⚡** (*Execute*) o `Ctrl + Shift + Enter`. Esto ejecuta **todo** el script.
3. En el panel inferior *Output* todas las líneas deben quedar en verde (✔). El script se puede ejecutar varias veces
   sin borrar datos.

## 4. Comprobar que se crearon las tablas

1. En el panel **Navigator → SCHEMAS** presiona el icono de **refrescar** (dos flechas circulares).
2. Despliega `evaluacion_docente → Tables`: deben verse **9 tablas**:
   `administradores, evaluaciones, grupos, materias, preguntas, profesor_materia, profesores, respuestas, sesiones`.
3. O ejecuta en una pestaña de consulta:
   ```sql
   USE evaluacion_docente;
   SHOW TABLES;
   SELECT num_pregunta, texto FROM preguntas ORDER BY num_pregunta;   -- deben salir 12 filas
   ```
4. Para ver las relaciones: **Database → Reverse Engineer…** → siguiente → elige `evaluacion_docente` → termina; se genera el diagrama EER.

### (Recomendado) Crear un usuario propio para la aplicación

En vez de usar `root` en el `.env`, ejecuta esto en Workbench (cambia la contraseña por una tuya):

```sql
CREATE USER IF NOT EXISTS 'evaluacion_app'@'localhost' IDENTIFIED BY 'UnaClaveSegura123!';
GRANT SELECT, INSERT, UPDATE, DELETE ON evaluacion_docente.* TO 'evaluacion_app'@'localhost';
FLUSH PRIVILEGES;
```
(También está comentado al final de `schema.sql`.) Así el sistema no necesita permisos para borrar tablas ni bases de datos.

## 5. Configurar las variables de conexión del backend

1. Copia el archivo de ejemplo:
   - Windows (CMD): `copy .env.example .env`
   - macOS/Linux o PowerShell: `cp .env.example .env`
2. Abre `.env` con el Bloc de notas / VS Code y completa:
   ```
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_USER=evaluacion_app          (o root)
   DB_PASSWORD=la_contraseña_de_ese_usuario
   DB_NAME=evaluacion_docente
   SESSION_SECRET=<texto aleatorio de 32+ caracteres>
   ```
3. Para generar el `SESSION_SECRET`, ejecuta y pega el resultado:
   ```
   python -c "import secrets; print(secrets.token_hex(48))"
   ```
4. **Nunca** subas `.env` a GitHub ni lo compartas (ya está en `.gitignore`).

## 6. Instalar las dependencias (entorno virtual de Python)

Un *entorno virtual* es una carpeta (`.venv`) donde se instalan las librerías de este proyecto sin afectar al resto de tu computadora.
Desde la carpeta del proyecto:

```
python -m venv .venv
```
Actívalo (hay que hacerlo **cada vez que abras una terminal nueva** para trabajar con el proyecto):

| Sistema | Comando |
|---|---|
| Windows (CMD) | `.venv\Scripts\activate` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` (si dice que la ejecución de scripts está deshabilitada: `Set-ExecutionPolicy -Scope Process Bypass` y reintenta) |
| macOS / Linux | `source .venv/bin/activate` |

Verás `(.venv)` al inicio de la línea. Después instala las dependencias (requiere internet la primera vez):
```
pip install -r requirements.txt
```
Instala Flask, PyMySQL, cryptography, bcrypt, python-dotenv y waitress.

## 7. Iniciar el backend y abrir el sistema

Con el entorno virtual activo:
```
python run.py
```
Debe mostrar:
```
✔ Evaluación docente en http://localhost:3000
  Base de datos: evaluacion_docente @ 127.0.0.1:3306   (Ctrl+C para detener)
```
Abre **http://localhost:3000** en el navegador. Para detenerlo: `Ctrl + C` en la terminal.
(El servidor solo escucha en tu computadora —`HOST=127.0.0.1`—; para que otros equipos entren hay que publicarlo con HTTPS, ver el final de esta guía.)

Verificación rápida de conexión: abre http://localhost:3000/api/salud → debe decir `"baseDeDatos":"conectada"`.

## 8. Crear el primer administrador de manera segura

Con el servidor MySQL activo y las tablas creadas, en otra terminal (con el entorno virtual activo, en la carpeta del proyecto):
```
python crear_admin.py
```
Te pedirá usuario, nombre completo y contraseña (**no se muestra al escribirla** y se pide dos veces).
Reglas: mínimo 10 caracteres, con mayúsculas, minúsculas y números. Se guarda solo el **hash bcrypt**; la contraseña no queda en
ningún archivo. No hay contraseña predeterminada ni escrita en el código.
Si olvidas la contraseña, ejecuta el mismo comando con el mismo usuario y se restablece.

## 9. Registrar grupos, profesores y materias

1. En http://localhost:3000 presiona **Administrador** e inicia sesión.
2. Pestaña **Materias** → escribe el nombre (mín. 3 caracteres) → *Guardar materia*.
3. Pestaña **Profesores** → escribe el nombre completo (solo letras y espacios, 5 a 60 caracteres) → *Guardar profesor*.
4. En la fila del profesor presiona **Materias** → elige una materia → **Asignar**. Repite para cada materia que imparte.
   (Un profesor sin materias aparece en la encuesta, pero avisa que no tiene materias asignadas.)
5. Pestaña **Grupos** → clave con formato `AAA0000` (ej. `GSI0252`) → *Guardar grupo*.
6. Cada tabla permite **Editar**, **Desactivar/Activar** y **Eliminar**. Si algo ya tiene evaluaciones, no se puede eliminar:
   **desactívalo** y el historial se conserva (los desactivados dejan de aparecer en la encuesta, pero siguen en los reportes).

## 10. Guardar una evaluación y verificarla en Workbench

1. Abre http://localhost:3000 (en una ventana normal o de otro navegador, sin sesión de administrador).
2. Escribe el grupo (ej. `GSI0252`), elige el **profesor** (la **materia** se selecciona sola si solo tiene una; si tiene varias, elige).
3. Contesta las 12 preguntas, agrega un comentario opcional y presiona **Guardar encuesta**. Debe aparecer «✔ Encuesta guardada».
4. En Workbench ejecuta:
   ```sql
   USE evaluacion_docente;

   -- Evaluaciones con su grupo, profesor y materia
   SELECT e.id, g.clave AS grupo, p.nombre AS profesor, m.nombre AS materia, e.comentario, e.creado_en
     FROM evaluaciones e
     JOIN grupos g ON g.id = e.grupo_id
     JOIN profesores p ON p.id = e.profesor_id
     JOIN materias m ON m.id = e.materia_id
    ORDER BY e.id DESC;

   -- Las 12 respuestas de la última evaluación
   SELECT r.num_pregunta, r.calificacion
     FROM respuestas r
    WHERE r.evaluacion_id = (SELECT MAX(id) FROM evaluaciones)
    ORDER BY r.num_pregunta;

   -- Conteos (cada evaluación debe tener exactamente 12 respuestas)
   SELECT (SELECT COUNT(*) FROM evaluaciones) AS evaluaciones, (SELECT COUNT(*) FROM respuestas) AS respuestas;
   ```
   Si no ves datos nuevos, presiona de nuevo el rayo ⚡ (Workbench no se actualiza solo).

## 11. Generar los cuatro tipos de reportes

Inicia sesión como administrador → **Reportes** (barra superior). Elige la pestaña, selecciona en los combobox y presiona **Generar reporte**:

| Reporte | Qué eliges | Qué muestra |
|---|---|---|
| **Por grupo** | Grupo | Profesores y materias evaluados, alumnos, promedio por profesor/materia, por pregunta y general del grupo |
| **Por profesor** | Profesor (+ materia y grupo, opcionales) | Evaluaciones, respuestas, promedios por pregunta y promedio del profesor con esos filtros |
| **Por grupo y profesor** | Grupo y profesor (+ materia, solo las del profesor) | Únicamente los registros que coinciden con los filtros |
| **General por grupo** | Grupo | Resumen completo: cada profesor/materia con su cantidad de alumnos, promedio y los promedios de las 12 preguntas, más el promedio general del grupo |

Si no hay evaluaciones para esos filtros, aparece un mensaje informativo (no un error). El botón **Imprimir** genera una versión
limpia del reporte. En la tabla *Detalle por alumno* el botón ✕ elimina una evaluación (solo administrador, con confirmación).

---

## Problemas frecuentes

| Mensaje / síntoma | Causa y solución |
|---|---|
| `No se pudo conectar a MySQL (2003)` | El servidor MySQL está apagado o `DB_PORT`/`DB_HOST` son incorrectos → paso 1 |
| `No se pudo conectar a MySQL (1045)` | Usuario o contraseña del `.env` incorrectos. Prueba el mismo usuario/clave en Workbench |
| `No se pudo conectar a MySQL (1049)` o «Faltan las tablas» | No se ejecutó `schema.sql` (paso 3) o `DB_NAME` está mal escrito |
| `Configuración incompleta en el archivo .env` | Falta `DB_USER` o `SESSION_SECRET` (mínimo 32 caracteres) |
| `OSError … address already in use` | El puerto 3000 está ocupado: cambia `PORT` en `.env` |
| `ModuleNotFoundError: No module named 'flask'` (o `bcrypt`, `pymysql`…) | El entorno virtual no está activo o faltó `pip install -r requirements.txt` (paso 6) |
| `'python' no se reconoce como un comando` | Reinstala Python marcando *Add python.exe to PATH*, o prueba con `py` en lugar de `python` |
| `RuntimeError: 'cryptography' package is required` | Falta esa librería: `pip install -r requirements.txt` |
| La página abre pero no cargan profesores | Abriste `index.html` con doble clic. Usa **http://localhost:3000** |
| «Demasiados intentos fallidos» | Se bloquea 15 min tras 10 intentos fallidos de login; espera o detén y vuelve a iniciar `python run.py` |
| Quieres reiniciar la base | En Workbench: `DROP DATABASE evaluacion_docente;` y vuelve a ejecutar `schema.sql` (**borra todo**) |

## Si lo publicas fuera de tu computadora

Por defecto el servidor solo escucha en `127.0.0.1` (tu equipo). Para publicarlo usa HTTPS (por ejemplo, detrás de un proxy inverso como Nginx
o Caddy en la misma máquina, que reenvía a `127.0.0.1:3000`), pon `COOKIE_SECURE=true` en `.env` (la cookie solo viaja por HTTPS y Flask confía en
las cabeceras del proxy), y utiliza un usuario de MySQL con permisos limitados (paso 4). Solo si el proxy está en *otra* máquina cambia `HOST`.
Sin HTTPS, las contraseñas viajarían sin cifrar.
