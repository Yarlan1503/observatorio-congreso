-- ============================================================
-- schema_senado.sql — Modelo Popolo para el Senado LXVI
-- ============================================================
-- Separa el namespace de IDs del Senado del de Diputados
-- para permitir evolución independiente.
--
-- Convenciones:
--   - Prefijos: SN (Senador), SO (Organización Senado),
--     SVE (Vote Event), SV (Vote), SC (Count), SM (Motion)
--   - FK hacia tablas principales cuando aplique (shared concept)
--   - Foreign keys habilitadas desde el inicio
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA encoding = "UTF-8";

-- ============================================================
-- Tabla: sen_vote_event — Eventos de votación del Senado
-- ============================================================
CREATE TABLE sen_vote_event (
    id TEXT PRIMARY KEY,           -- SVE01, SVE02, ...
    motion_id TEXT NOT NULL,      -- FK a sen_motion
    start_date TEXT NOT NULL,     -- ISO 8601
    result TEXT CHECK(result IN ('aprobada', 'rechazada', 'empate', NULL)),
    senado_id INTEGER UNIQUE,     -- ID de la votación en el portal del Senado
    voter_count INTEGER,
    legislature TEXT DEFAULT 'LXVI',
    legislative_session TEXT,     -- "SEGUNDO AÑO DE EJERCICIO"
    period TEXT,                  -- "SEGUNDO PERIODO ORDINARIO"
    requirement TEXT CHECK(requirement IN ('mayoria_simple', 'mayoria_calificada', 'unanime', NULL)),
    fuente_url TEXT
);

-- ============================================================
-- Tabla: sen_motion — Iniciativas/proyectos votados en el Senado
-- ============================================================
CREATE TABLE sen_motion (
    id TEXT PRIMARY KEY,          -- SM01, SM02, ...
    text TEXT NOT NULL,           -- Descripción del dictamen
    clasificacion TEXT CHECK(
        clasificacion IN ('reforma_constitucional', 'ley_secundaria', 'ordinaria', 'otra')
    ),
    result TEXT CHECK(result IN ('aprobada', 'rechazada', 'pendiente', 'retirada', NULL)),
    date TEXT,
    legislative_session TEXT,
    fuente_url TEXT
);

-- ============================================================
-- Tabla: sen_person — Senadores (basada en Popolo Person)
-- ============================================================
CREATE TABLE sen_person (
    id TEXT PRIMARY KEY,          -- SN01, SN02, ...
    nombre TEXT NOT NULL,
    genero TEXT CHECK(genero IN ('M', 'F', 'NB', NULL)),
    fecha_nacimiento TEXT,
    curul_tipo TEXT CHECK(curul_tipo IN ('mayoria_relativa', 'plurinominal', 'suplente', NULL)),
    estado TEXT,                  -- Entidad federativa (nullable, se llena con cruce)
    estado_tipo TEXT CHECK(estado_tipo IN ('entidad', 'nacional', NULL)), -- bancada nacional
    start_date TEXT,
    end_date TEXT,
    identifiers_json TEXT,         -- {"senado_id": 1234}
    observaciones TEXT
);

-- ============================================================
-- Tabla: sen_membership — Membresías de senadores a partidos
-- ============================================================
CREATE TABLE sen_membership (
    id TEXT PRIMARY KEY,          -- SM01, SM02, ...
    person_id TEXT NOT NULL REFERENCES sen_person(id) ON DELETE CASCADE,
    org_id TEXT NOT NULL,         -- FK a organization (partido)
    rol TEXT NOT NULL DEFAULT 'senador',
    label TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT,
    on_behalf_of TEXT REFERENCES organization(id)
);

-- ============================================================
-- Tabla: sen_vote — Votos individuales de senadores
-- ============================================================
CREATE TABLE sen_vote (
    id TEXT PRIMARY KEY,          -- SV01, SV02, ...
    vote_event_id TEXT NOT NULL REFERENCES sen_vote_event(id),
    voter_id TEXT NOT NULL REFERENCES sen_person(id),
    option TEXT NOT NULL CHECK(option IN ('a_favor', 'en_contra', 'abstencion', 'ausente')),
    "group" TEXT                 -- Partido al que pertenecía al votar
);

-- ============================================================
-- Tabla: sen_count — Conteos agregados por partido
-- ============================================================
CREATE TABLE sen_count (
    id TEXT PRIMARY KEY,          -- SC01, SC02, ...
    vote_event_id TEXT NOT NULL REFERENCES sen_vote_event(id),
    option TEXT NOT NULL CHECK(option IN ('a_favor', 'en_contra', 'abstencion', 'ausente')),
    value INTEGER NOT NULL CHECK(value >= 0),
    group_id TEXT REFERENCES organization(id)
);

-- ============================================================
-- Tabla: sen_organization — Grupos parlamentares del Senado
-- ============================================================
CREATE TABLE sen_organization (
    id TEXT PRIMARY KEY,          -- SO01, SO02, ...
    nombre TEXT NOT NULL,
    clasificacion TEXT CHECK(clasificacion IN ('partido', 'coalicion', 'grupo', 'otro')),
    abbr TEXT,                   -- MORENA, PAN, PRI, etc.
    fundacion TEXT,
    disolucion TEXT
);

-- ============================================================
-- Índices
-- ============================================================
CREATE INDEX idx_sen_vote_event_motion ON sen_vote_event(motion_id);
CREATE INDEX idx_sen_vote_voter ON sen_vote(voter_id);
CREATE INDEX idx_sen_vote_event ON sen_vote(vote_event_id);
CREATE INDEX idx_sen_count_event ON sen_count(vote_event_id);
CREATE INDEX idx_sen_membership_person ON sen_membership(person_id);
CREATE INDEX idx_sen_membership_org ON sen_membership(org_id);