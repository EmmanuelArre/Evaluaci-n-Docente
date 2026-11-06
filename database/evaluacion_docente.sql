DROP DATABASE IF EXISTS evaluacion_docente;


CREATE DATABASE IF NOT EXISTS evaluacion_docente
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE evaluacion_docente;

-- ---------------------------------------------------------------------
-- GRUPOS  (clave formal AAA0000: 3 letras mayúsculas + 4 dígitos, RG-02)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grupos (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  clave          CHAR(7) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  descripcion    VARCHAR(100) NULL,
  -- Alumnos del grupo = tope de encuestas válidas. 0 = aún sin capturar: el grupo no acepta encuestas.
  num_alumnos    SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  -- Contraseña de acceso a la encuesta del grupo, CIFRADA con Fernet (AES-128-CBC + HMAC). Nunca en texto
  -- plano. La clave de cifrado vive en la variable de entorno CLAVE_CIFRADO_ACCESO, no en la base ni en el código.
  acceso_cifrado VARCHAR(512) CHARACTER SET ascii COLLATE ascii_bin NULL,
  -- Se incrementa al cambiar la contraseña: invalida las autorizaciones que ya estaban abiertas.
  acceso_version INT UNSIGNED NOT NULL DEFAULT 0,
  activo         TINYINT(1) NOT NULL DEFAULT 1,
  creado_en      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_grupos_clave UNIQUE (clave),
  CONSTRAINT ck_grupos_clave CHECK (clave REGEXP '^[A-Z]{4}[0-9]{3}$'),
  CONSTRAINT ck_grupos_alumnos CHECK (num_alumnos BETWEEN 0 AND 99),
  CONSTRAINT ck_grupos_activo CHECK (activo IN (0, 1))
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- PROFESORES
--  · nombre = nombre completo ya armado (nombres + apellido paterno + apellido materno). Es el que usan los
--    reportes y la tabla de la encuesta, y es único.
--  · nombres (1 a 5 nombres de pila) y apellido_paterno son obligatorios al registrar/editar desde la aplicación;
--    apellido_materno es opcional (NULL). Quedan NULL solo en profesores anteriores a esta versión,
--    hasta que se editen.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profesores (
  id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nombre           VARCHAR(120) NOT NULL,
  nombres          VARCHAR(60) NULL,
  apellido_paterno VARCHAR(28) NULL,
  apellido_materno VARCHAR(28) NULL,
  activo         TINYINT(1) NOT NULL DEFAULT 1,
  creado_en      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_profesores_nombre UNIQUE (nombre),
  CONSTRAINT ck_profesores_nombre CHECK (CHAR_LENGTH(nombre) >= 5),
  CONSTRAINT ck_profesores_activo CHECK (activo IN (0, 1)),
  INDEX idx_profesores_activo (activo)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- MATERIAS  (RM-02: mínimo 3 y máximo 60 caracteres)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS materias (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nombre         VARCHAR(60) NOT NULL,
  activo         TINYINT(1) NOT NULL DEFAULT 1,
  creado_en      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_materias_nombre UNIQUE (nombre),
  CONSTRAINT ck_materias_nombre CHECK (CHAR_LENGTH(nombre) >= 3),
  CONSTRAINT ck_materias_activo CHECK (activo IN (0, 1)),
  INDEX idx_materias_activo (activo)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- PROFESOR_MATERIA  (qué materias imparte cada profesor)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profesor_materia (
  profesor_id INT UNSIGNED NOT NULL,
  materia_id  INT UNSIGNED NOT NULL,
  creado_en   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (profesor_id, materia_id),
  INDEX idx_pm_materia (materia_id),
  CONSTRAINT fk_pm_profesor FOREIGN KEY (profesor_id) REFERENCES profesores (id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_pm_materia FOREIGN KEY (materia_id) REFERENCES materias (id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS asignaciones (
  grupo_id    INT UNSIGNED NOT NULL,
  profesor_id INT UNSIGNED NOT NULL,
  materia_id  INT UNSIGNED NOT NULL,
  activo      TINYINT(1) NOT NULL DEFAULT 1,
  creado_en   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (grupo_id, profesor_id, materia_id),
  INDEX idx_asig_profesor (profesor_id),
  INDEX idx_asig_prof_mat (profesor_id, materia_id),
  CONSTRAINT ck_asig_activo CHECK (activo IN (0, 1)),
  CONSTRAINT fk_asig_grupo FOREIGN KEY (grupo_id) REFERENCES grupos (id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_asig_prof_mat FOREIGN KEY (profesor_id, materia_id)
    REFERENCES profesor_materia (profesor_id, materia_id)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- PREGUNTAS  (catálogo oficial P1–P12, igual a js/config.js)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS preguntas (
  num_pregunta TINYINT UNSIGNED NOT NULL,
  texto        VARCHAR(255) NOT NULL,
  PRIMARY KEY (num_pregunta),
  CONSTRAINT ck_preguntas_num CHECK (num_pregunta BETWEEN 1 AND 12)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- ENCUESTAS  (UNA por envío del formulario; anónima: solo guarda el grupo y la fecha)
-- Es lo que se cuenta contra el límite: encuestas de un grupo <= num_alumnos del grupo.
-- Una encuesta que evalúa a 5 profesores es UNA fila aquí y 5 filas en evaluaciones.
-- No existe ninguna columna que identifique al alumno (ni nombre, ni matrícula, ni correo, ni IP).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS encuestas (
  id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  grupo_id  INT UNSIGNED NOT NULL,
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_encuestas_id_grupo (id, grupo_id),   -- destino de la FK compuesta de evaluaciones
  INDEX idx_enc_grupo (grupo_id),
  CONSTRAINT fk_enc_grupo FOREIGN KEY (grupo_id) REFERENCES grupos (id)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- EVALUACIONES  (la calificación de UN profesor-materia dentro de una encuesta)
-- · (encuesta_id, grupo_id) → encuestas: la evaluación pertenece a una encuesta del MISMO grupo.
-- · (grupo_id, profesor_id, materia_id) → asignaciones: el profesor imparte esa materia a ese grupo.
-- · UNIQUE (encuesta_id, profesor_id, materia_id): una encuesta no evalúa dos veces la misma asignación.
-- RESTRICT: no se puede borrar un grupo/profesor/materia/asignación con historial.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evaluaciones (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  encuesta_id BIGINT UNSIGNED NOT NULL,
  grupo_id    INT UNSIGNED NOT NULL,
  profesor_id INT UNSIGNED NOT NULL,
  materia_id  INT UNSIGNED NOT NULL,
  comentario  VARCHAR(200) NULL,
  creado_en   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_eval_encuesta_asig (encuesta_id, profesor_id, materia_id),
  INDEX idx_eval_grupo_prof_mat (grupo_id, profesor_id, materia_id),
  INDEX idx_eval_prof_mat (profesor_id, materia_id),
  INDEX idx_eval_creado (creado_en),
  CONSTRAINT fk_eval_grupo FOREIGN KEY (grupo_id) REFERENCES grupos (id)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_eval_prof_mat FOREIGN KEY (profesor_id, materia_id)
    REFERENCES profesor_materia (profesor_id, materia_id)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_eval_asignacion FOREIGN KEY (grupo_id, profesor_id, materia_id)
    REFERENCES asignaciones (grupo_id, profesor_id, materia_id)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_eval_encuesta FOREIGN KEY (encuesta_id, grupo_id)
    REFERENCES encuestas (id, grupo_id)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- RESPUESTAS  (12 por evaluación; escala entera 5–10, RQ-03)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS respuestas (
  evaluacion_id BIGINT UNSIGNED NOT NULL,
  num_pregunta  TINYINT UNSIGNED NOT NULL,
  calificacion  TINYINT UNSIGNED NOT NULL,
  PRIMARY KEY (evaluacion_id, num_pregunta),
  INDEX idx_resp_pregunta (num_pregunta),
  CONSTRAINT ck_resp_calif CHECK (calificacion BETWEEN 5 AND 10),
  CONSTRAINT fk_resp_evaluacion FOREIGN KEY (evaluacion_id) REFERENCES evaluaciones (id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_resp_pregunta FOREIGN KEY (num_pregunta) REFERENCES preguntas (num_pregunta)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- ADMINISTRADORES  (solo se guarda el hash bcrypt, nunca la contraseña)
-- El primer administrador se crea con:  python crear_admin.py
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS administradores (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario       VARCHAR(30) NOT NULL,
  nombre        VARCHAR(60) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  activo        TINYINT(1) NOT NULL DEFAULT 1,
  ultimo_acceso DATETIME NULL,
  creado_en     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_admin_usuario UNIQUE (usuario),
  CONSTRAINT ck_admin_activo CHECK (activo IN (0, 1))
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- SESIONES  (almacén de sesiones de express-session; las usa el backend)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sesiones (
  session_id VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  expires    INT UNSIGNED NOT NULL,
  data       MEDIUMTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
  PRIMARY KEY (session_id),
  INDEX idx_sesiones_expires (expires)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- DATOS INICIALES: las 12 preguntas oficiales (no inventa preguntas nuevas)
-- ---------------------------------------------------------------------
INSERT IGNORE INTO preguntas (num_pregunta, texto) VALUES
  (1, 'El profesor expone los contenidos y prácticas de su asignatura de manera clara, gradual y congruente.'),
  (2, 'El profesor proporciona orientación y apoyo a los alumnos con problemas de aprendizaje.'),
  (3, 'Propicia un ambiente de confianza y de participación durante la clase.'),
  (4, 'Establece controles de evaluación del aprendizaje considerando: exámenes parciales, participación, trabajos, prácticas, etc.'),
  (5, 'El profesor da seguimiento al programa, considerando los propósitos y contenidos, a fin de lograr el saber, el saber hacer y el saber ser.'),
  (6, 'El profesor emplea métodos didácticos (gráficas, folletos, acetatos, ilustraciones, dinámicas de grupo o trabajos en equipo) para facilitar la comprensión de los temas.'),
  (7, 'El profesor proporciona mayores referencias sobre los temas que se les dificulta a los alumnos.'),
  (8, 'El profesor responde todas las preguntas formuladas por los alumnos.'),
  (9, 'El profesor muestra disposición para atender a los alumnos dentro y fuera de clase para resolver y aclarar preguntas o dudas en temas que te interesen.'),
  (10, 'El nivel de dificultad de los ejemplos de clase es congruente con el de los exámenes.'),
  (11, 'El profesor entra a tiempo a clase.'),
  (12, 'El profesor fomenta el auto-aprendizaje o actividades de lectura.');

-- ---------------------------------------------------------------------
-- (RECOMENDADO, OPCIONAL) Usuario MySQL propio para la aplicación, en lugar
-- de "root". Quita los "-- " del bloque, cambia la contraseña y ejecútalo.
-- Después usa ese usuario en DB_USER / DB_PASSWORD del archivo .env.
-- ---------------------------------------------------------------------
-- CREATE USER IF NOT EXISTS 'evaluacion_app'@'localhost' IDENTIFIED BY 'CAMBIA_ESTA_CLAVE';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON evaluacion_docente.* TO 'evaluacion_app'@'localhost';
-- FLUSH PRIVILEGES;