-- =====================================================================
-- MIGRACIÓN: CRUD de preguntas (cantidad variable)
-- Quita el tope de 12 preguntas de la tabla `preguntas`. No borra ni cambia datos.
-- Se corre UNA vez, en MySQL Workbench, sobre la base que ya tienes (TiDB o local).
-- =====================================================================
USE evaluacion_docente;

-- Si tu servidor no reconoce DROP CONSTRAINT, comenta esta línea y usa la siguiente (DROP CHECK).
ALTER TABLE preguntas DROP CONSTRAINT ck_preguntas_num;
-- ALTER TABLE preguntas DROP CHECK ck_preguntas_num;

-- COMPROBACIÓN: debe seguir mostrando tus preguntas actuales
SELECT num_pregunta, LEFT(texto, 60) AS texto FROM preguntas ORDER BY num_pregunta;
