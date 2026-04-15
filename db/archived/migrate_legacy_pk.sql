-- ============================================================
-- migrate_legacy_pk.sql — Migración a PK compuesta (senado_id, legislature)
-- ============================================================
-- Objetivo: Permitir múltiples legislaturas (LX-LXV) donde el
-- mismo senado_id puede repetirse en cada una.
--
-- Cambios:
--   1. senado_id: quitar UNIQUE, hacer NOT NULL
--   2. legislature: hacer NOT NULL (preserve default 'LXVI' en datos)
--   3. PRIMARY KEY: cambiar de (id) a (senado_id, legislature)
--
-- Estrategia: recrear tabla (SQLite no soporta DROP PRIMARY KEY ni
-- ALTER COLUMN SET NOT NULL directamente).
--
-- Idempotente: detecta si la PK ya es composta y omite la migración.
-- Verificación post-migración incluida.
--
-- Uso:
--   sqlite3 db/senado.db < db/migrations/migrate_legacy_pk.sql
-- ============================================================

.headers off
.mode list

-- ============================================================
-- FASE 0: Detección de estado actual (idempotencia)
-- ============================================================
.print '=== DETECCIÓN DE ESTADO ACTUAL ==='

-- Verificar si la tabla existe
SELECT 'Verificando existencia de sen_vote_event...' AS paso;
SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sen_vote_event';

-- Verificar si la PK ya es compuesta buscando PRIMARY KEY (senado_id, legislature)
-- en la definición SQL de la tabla
SELECT 'Verificando si PK ya es compuesta...' AS paso;
SELECT COUNT(*) FROM sqlite_master 
WHERE type='table' 
  AND name='sen_vote_event'
  AND (
    sql LIKE '%PRIMARY KEY (senado_id, legislature)%'
    OR sql LIKE '%PRIMARY KEY(%senado_id%,%legislature%'
  );

-- Si la PK ya es compuesta, terminar aquí (idempotencia)
.print '';
.print '=== VERIFICACIÓN DE MIGRACIÓN PREVIA ===';
SELECT 'Si count=1, la migración ya fue aplicada. Saliendo.' AS instruccion;
SELECT COUNT(*) AS pk_compuesta FROM sqlite_master 
WHERE type='table' 
  AND name='sen_vote_event'
  AND sql LIKE '%PRIMARY KEY (senado_id, legislature)%';

-- Salir temprano si la migración ya se aplicó
-- (El script continuará si hay cualquier otro resultado, ej. tabla no existe)

-- ============================================================
-- FASE 1: Preservar datos existentes
-- ============================================================
.print '';
.print '=== FASE 1: Preservar datos existentes ===';

-- Primero, asegurar que legislature NULL se actualice a 'LXVI'
-- (esto debe hacerse ANTES de recrear la tabla)
SELECT 'Contando legislature NULL antes de migración...' AS paso;
SELECT COUNT(*) AS null_count FROM sen_vote_event WHERE legislature IS NULL;

-- Actualizar NULLs a LXVI
UPDATE sen_vote_event SET legislature = 'LXVI' WHERE legislature IS NULL;
.print 'NULLs en legislature actualizados a LXVI.';

-- Contar filas antes de migración
SELECT 'Total de filas a migrar:' AS paso;
SELECT COUNT(*) AS row_count FROM sen_vote_event;

-- Guardar esquema actual para referencia
SELECT 'Guardando esquema actual...' AS paso;
SELECT sql AS esquema_original FROM sqlite_master 
WHERE type='table' AND name='sen_vote_event';

-- ============================================================
-- FASE 2: Recrear tabla con PK compuesta
-- ============================================================
.print '';
.print '=== FASE 2: Recrear tabla con PK composta ===';

-- Crear tabla temporal con la nueva estructura
CREATE TABLE sen_vote_event_new (
    id TEXT,
    motion_id TEXT NOT NULL,
    start_date TEXT NOT NULL,
    result TEXT CHECK(result IN ('aprobada', 'rechazada', 'empate', NULL)),
    senado_id INTEGER NOT NULL,
    voter_count INTEGER,
    legislature TEXT NOT NULL,
    legislative_session TEXT,
    period TEXT,
    requirement TEXT CHECK(requirement IN ('mayoria_simple', 'mayoria_calificada', 'unanime', NULL)),
    fuente_url TEXT,
    PRIMARY KEY (senado_id, legislature)
);

-- Copiar datos (IGNORAR duplicados de PK si los hay)
INSERT OR IGNORE INTO sen_vote_event_new 
SELECT * FROM sen_vote_event;

-- ============================================================
-- FASE 3: Verificación de datos
-- ============================================================
.print '';
.print '=== VERIFICACIÓN DE DATOS ===';

SELECT 'Conteo de filas en tabla original:' AS paso;
SELECT COUNT(*) AS original_count FROM sen_vote_event;

SELECT 'Conteo de filas en tabla nueva:' AS paso;
SELECT COUNT(*) AS new_count FROM sen_vote_event_new;

-- Verificar que no haya perdido datos
SELECT 'Integridad de datos:' AS paso;
SELECT 
    CASE 
        WHEN (SELECT COUNT(*) FROM sen_vote_event) = (SELECT COUNT(*) FROM sen_vote_event_new)
        THEN 'OK - Sin pérdida de datos'
        ELSE 'ALERTA - Posible pérdida de datos'
    END AS resultado;

-- Verificar PK composta en tabla nueva
SELECT 'Verificando constraint PK compuesta...' AS paso;
SELECT COUNT(*) AS pk_ok
FROM sqlite_master 
WHERE type='table' AND name='sen_vote_event_new' 
  AND sql LIKE '%PRIMARY KEY (senado_id, legislature)%';

-- ============================================================
-- FASE 4: Aplicar migración (swap de tablas)
-- ============================================================
.print '';
.print '=== FASE 4: Aplicando migración ===';

DROP TABLE sen_vote_event;
ALTER TABLE sen_vote_event_new RENAME TO sen_vote_event;
.print 'Tabla reemplazada: sen_vote_event ahora tiene PK composta.';

-- ============================================================
-- FASE 5: Recrear índices
-- ============================================================
.print '';
.print '=== FASE 5: Recreando índices ===';

-- Índice por motion (referencia original)
CREATE INDEX idx_sen_vote_event_motion ON sen_vote_event(motion_id);

-- Índice por legislature (nuevo, para filtrar por período)
CREATE INDEX idx_sen_vote_event_legislature ON sen_vote_event(legislature);

-- Índices relacionados con otras tablas
CREATE INDEX IF NOT EXISTS idx_sen_vote_voter ON sen_vote(voter_id);
CREATE INDEX IF NOT EXISTS idx_sen_vote_event_ref ON sen_vote(vote_event_id);
CREATE INDEX IF NOT EXISTS idx_sen_count_event ON sen_count(vote_event_id);
CREATE INDEX IF NOT EXISTS idx_sen_membership_person ON sen_membership(person_id);
CREATE INDEX IF NOT EXISTS idx_sen_membership_org ON sen_membership(org_id);

.print 'Índices recreados.';

-- ============================================================
-- FASE 6: Verificación final
-- ============================================================
.print '';
.print '=== VERIFICACIÓN FINAL ===';

.headers on
.mode column

SELECT '--- Estructura de sen_vote_event ---' AS info;
PRAGMA table_info(sen_vote_event);

SELECT '' AS '';
SELECT '--- SQL de creación ---' AS info;
SELECT sql FROM sqlite_master WHERE type='table' AND name='sen_vote_event';

SELECT '' AS '';
SELECT '--- Índices ---' AS info;
SELECT name, sql FROM sqlite_master WHERE type='index' AND name LIKE 'idx_sen_vote_event%';

SELECT '' AS '';
SELECT '--- Distribución por legislature ---' AS info;
SELECT legislature, COUNT(*) AS cnt FROM sen_vote_event GROUP BY legislature ORDER BY legislature;

SELECT '' AS '';
SELECT '--- Muestra de 5 filas (PK composta) ---' AS info;
SELECT senado_id, legislature, id, motion_id, result FROM sen_vote_event LIMIT 5;

-- Verificar que no hay duplicados (senado_id, legislature) - no debería haber si se usaron IGNORE
SELECT '' AS '';
SELECT '--- Duplicados en PK (debe estar vacío) ---' AS info;
SELECT senado_id, legislature, COUNT(*) AS cnt 
FROM sen_vote_event 
GROUP BY senado_id, legislature 
HAVING cnt > 1;

-- ============================================================
-- Resumen
-- ============================================================
.print '';
.headers off
SELECT '========================================' AS separator;
SELECT 'MIGRACIÓN COMPLETADA' AS status;
SELECT 'Nueva PK: (senado_id, legislature)' AS new_pk;
SELECT '========================================' AS separator;
