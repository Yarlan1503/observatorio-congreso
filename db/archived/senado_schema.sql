-- ⚠️ OBSOLETO: Este schema corresponde a la BD independiente senado.db,
-- previa a la unificación en congreso.db. No usar.
-- Archivado como referencia histórica.

-- ============================================================
-- senado_schema.sql — Observatorio del Congreso: Schema del Senado
-- ============================================================
-- Modelo simplificado adaptado de Popolo-Graph para el portal
-- del Senado de la República (senado.gob.mx, LXVI Legislatura).
--
-- Diferencias con el schema principal (Diputados):
--   - IDs autoincrementales (no IDs legibles con prefijos)
--   - Tablas con prefijo senado_ (BD independiente)
--   - Menos tablas: sin areas, posts, motions, actores externos
--   - Los IDs de votacion corresponden al ID del portal
--
-- Convenciones:
--   - Fechas en formato ISO 8601 (YYYY-MM-DD)
--   - Codificación UTF-8
--   - Foreign keys habilitadas desde el inicio
-- ============================================================

-- Pragmas de configuración de la base de datos
PRAGMA foreign_keys = ON;
PRAGMA encoding = "UTF-8";

-- ============================================================
-- Tabla 1: senado_organizacion — Partidos y bancadas del Senado
-- Grupos parlamentarios registrados en la LXVI Legislatura.
-- ============================================================
CREATE TABLE senado_organizacion (
    -- ID autoincremental
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Nombre oficial de la organización (único)
    nombre TEXT NOT NULL UNIQUE,

    -- Clasificación: partido, bancada u otro
    clasificacion TEXT NOT NULL CHECK(
        clasificacion IN ('partido', 'bancada', 'otro')
    ),

    -- Abreviatura oficial (MORENA, PAN, PRI, PVEM, PT, MC, SG)
    abreviatura TEXT NOT NULL UNIQUE
);

-- ============================================================
-- Tabla 2: senado_persona — Senadores
-- Legisladores que integran el Senado de la República.
-- Incluye campo nombre_normalizado para matching fuzzy.
-- ============================================================
CREATE TABLE senado_persona (
    -- ID autoincremental
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Nombre completo tal como aparece en el portal
    nombre TEXT NOT NULL,

    -- Nombre normalizado (sin acentos, sin tildes, uppercase)
    -- para comparaciones robustas de matching
    nombre_normalizado TEXT NOT NULL,

    -- Género: M=masculino, F=femenino, NB=no binario
    genero TEXT CHECK(genero IN ('M', 'F', 'NB')),

    -- Tipo de curul: mayoría relativa, plurinominal o primera minoría
    curul_tipo TEXT CHECK(
        curul_tipo IN ('mayoria_relativa', 'plurinominal', 'primera_minoría')
    )
);

-- ============================================================
-- Tabla 3: senado_membresia — Pertenencia a organizaciones
-- Relación entre senadores y sus grupos parlamentarios.
-- Un senador puede cambiar de bancada (múltiples membresías).
-- ============================================================
CREATE TABLE senado_membresia (
    -- ID autoincremental
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Referencia al senador (eliminación en cascada)
    persona_id INTEGER NOT NULL REFERENCES senado_persona(id) ON DELETE CASCADE,

    -- Referencia a la organización (eliminación en cascada)
    organizacion_id INTEGER NOT NULL REFERENCES senado_organizacion(id) ON DELETE CASCADE,

    -- Rol dentro de la organización: senador por defecto
    rol TEXT NOT NULL DEFAULT 'senador',

    -- Fecha de inicio de la membresía
    start_date TEXT
);

-- ============================================================
-- Tabla 4: senado_votacion — Votaciones del Senado
-- Metadatos de cada votación nominal. El ID corresponde al
-- identificador del portal senado.gob.mx.
-- ============================================================
CREATE TABLE senado_votacion (
    -- ID del portal senado.gob.mx (primary key directo)
    id INTEGER PRIMARY KEY,

    -- Título de la votación (ej: "Dictamen que reforma...")
    titulo TEXT NOT NULL,

    -- Descripción extendida de la votación
    descripcion TEXT DEFAULT '',

    -- Fecha del día de la sesión (formato libre del portal)
    fecha TEXT DEFAULT '',

    -- Fecha en formato ISO 8601 (YYYY-MM-DD), parseada
    fecha_iso TEXT DEFAULT '',

    -- Periodo legislativo (ej: "Primer Periodo Ordinario")
    periodo TEXT DEFAULT '',

    -- Año de ejercicio fiscal (ej: "2025")
    anio_ejercicio TEXT DEFAULT '',

    -- Conteo de votos a favor
    total_pro INTEGER DEFAULT 0,

    -- Conteo de votos en contra
    total_contra INTEGER DEFAULT 0,

    -- Conteo de abstenciones
    total_abstencion INTEGER DEFAULT 0,

    -- Total de votos emitidos
    total_votos INTEGER DEFAULT 0,

    -- Resultado de la votación
    resultado TEXT CHECK(
        resultado IN ('aprobada', 'rechazada', 'empate')
    ),

    -- URL fuente en el portal del Senado
    fuente_url TEXT NOT NULL UNIQUE
);

-- ============================================================
-- Tabla 5: senado_voto — Votos individuales
-- Registro del voto de cada senador en cada votación.
-- Tabla central para análisis de disciplina y co-votación.
-- ============================================================
CREATE TABLE senado_voto (
    -- ID autoincremental
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Referencia a la votación (eliminación en cascada)
    votacion_id INTEGER NOT NULL REFERENCES senado_votacion(id) ON DELETE CASCADE,

    -- Referencia al senador (eliminación en cascada)
    persona_id INTEGER NOT NULL REFERENCES senado_persona(id) ON DELETE CASCADE,

    -- Opción de voto: a_favor, en_contra o abstencion
    opcion TEXT NOT NULL CHECK(
        opcion IN ('a_favor', 'en_contra', 'abstencion')
    ),

    -- Abreviatura del partido al que pertenecía al votar
    grupo TEXT,

    -- Un senador solo puede votar una vez por votación
    UNIQUE(votacion_id, persona_id)
);

-- ============================================================
-- ÍNDICES — Para acelerar las consultas más frecuentes
-- ============================================================

-- Índice sobre senado_persona (búsqueda por nombre normalizado)
CREATE INDEX idx_senado_persona_nombre ON senado_persona(nombre_normalizado);

-- Índice sobre senado_voto (consultas por votación)
CREATE INDEX idx_senado_voto_votacion ON senado_voto(votacion_id);

-- Índice sobre senado_voto (consultas por persona)
CREATE INDEX idx_senado_voto_persona ON senado_voto(persona_id);

-- Índice sobre senado_votacion (ordenamiento por fecha)
CREATE INDEX idx_senado_votacion_fecha ON senado_votacion(fecha_iso);
