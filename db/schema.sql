-- ============================================================
-- schema.sql — Observatorio del Congreso: Modelo Popolo-Graph
-- ============================================================
-- Combina el estándar Popolo (parlamentario) con extensiones
-- para relaciones de poder informales (redes de poder, teoría
-- de juegos, índices Shapley/Banzhaf).
--
-- Convenciones:
--   - IDs legibles con prefijos (A01, O01, P01, AE01, etc.)
--   - Fechas en formato ISO 8601 (YYYY-MM-DD)
--   - Codificación UTF-8
--   - Foreign keys habilitadas desde el inicio
-- ============================================================

-- Pragmas de configuración de la base de datos
PRAGMA foreign_keys = ON;
PRAGMA encoding = "UTF-8";
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000; 

-- ============================================================
-- Convención de Foreign Keys
-- ============================================================
-- ON DELETE/ON UPDATE se declaran explícitamente en cada FK:
--   CASCADE  → Tablas hijas (registros que no existen sin su padre)
--              Ej: vote.vote_event_id (borrar votación → borrar votos)
--   RESTRICT → Tablas de lookup/padre (no borrar si tiene hijos)
--              Ej: vote_event.motion_id (no borrar motion con vote_events)
-- Los triggers de validación de fechas complementan pero no reemplazan
-- la integridad referencial declarativa.
-- ============================================================

-- ============================================================
-- Tabla 1: area — Divisiones geográficas del país
-- Estados, distritos y circunscripciones electorales.
-- Los distritos pueden tener un parent (estado) mediante parent_id.
-- ============================================================
CREATE TABLE area (
    -- ID legible con prefijo A01, A02, ...
    id TEXT PRIMARY KEY,

    -- Nombre del área (estado, distrito, circunscripción)
    nombre TEXT NOT NULL,

    -- Clasificación del área: estado, distrito o circunscripción
    clasificacion TEXT NOT NULL CHECK(
        clasificacion IN ('estado', 'distrito', 'circunscripcion')
    ),

    -- Referencia al área padre (ej: distrito dentro de un estado)
    parent_id TEXT REFERENCES area(id) ON DELETE RESTRICT ON UPDATE RESTRICT,

    -- Geometría GeoJSON opcional para visualización en mapas
    geometry TEXT
);

-- ============================================================
-- Tabla 2: organization — Organizaciones políticas
-- Partidos, bancadas, coaliciones, instituciones gubernamentales.
-- ============================================================
CREATE TABLE organization (
    -- ID legible con prefijo O01, O02, ...
    id TEXT PRIMARY KEY,

    -- Nombre oficial de la organización (único)
    nombre TEXT NOT NULL UNIQUE,

    -- Abreviatura (MORENA, PAN, PRI, etc.)
    abbr TEXT,

    -- Clasificación: partido, bancada, coalición, gobierno, institución u otro
    clasificacion TEXT NOT NULL CHECK(
        clasificacion IN (
            'partido', 'bancada', 'coalicion',
            'gobierno', 'institucion', 'otro'
        )
    ),

    -- Fecha de fundación en formato ISO 8601 (nullable)
    fundacion TEXT,

    -- Fecha de disolución en formato ISO 8601 (nullable)
    disolucion TEXT
);

-- ============================================================
-- Tabla 3: person — Legisladores y actores políticos
-- Diputados, senadores y otros actores relevantes del Congreso.
-- Incluye campos para teoría de juegos (corriente, vulnerabilidad).
-- ============================================================
CREATE TABLE person (
    -- ID legible con prefijo P01, P02, ...
    id TEXT PRIMARY KEY,

    -- Nombre completo de la persona
    nombre TEXT NOT NULL,

    -- Fecha de nacimiento en formato ISO 8601 (nullable)
    fecha_nacimiento TEXT,

    -- Género: M=masculino, F=femenino, NB=no binario, NULL=no especificado
    genero TEXT CHECK(genero IN ('M', 'F', 'NB')),

    -- Tipo de curul: mayoría relativa, plurinominal o suplente (nullable)
    curul_tipo TEXT CHECK(
        curul_tipo IN ('mayoria_relativa', 'plurinominal', 'suplente')
    ),

    -- Circunscripción electoral (1 a 5, nullable)
    circunscripcion INTEGER CHECK(circunscripcion BETWEEN 1 AND 5),

    -- Fecha de inicio de la legislatura
    start_date TEXT,

    -- Fecha de fin de la legislatura
    end_date TEXT,

    -- Corriente interna del partido (para análisis de lealtades)
    corriente_interna TEXT CHECK(
        corriente_interna IS NULL OR corriente_interna IN ('Monreal', 'AMLO', 'Sheinbaum', 'institucionalista')
    ),

    -- Nivel de vulnerabilidad estimado (para teoría de juegos)
    vulnerabilidad TEXT CHECK(
        vulnerabilidad IS NULL OR vulnerabilidad IN ('alta', 'media', 'baja')
    ),

    -- Observaciones libres sobre el legislador
    observaciones TEXT,

    -- JSON con identificadores externos (ej: {"sitl_id": 108})
    identifiers_json TEXT
);

-- ============================================================
-- Tabla 4: membership — Pertenencia a organizaciones
-- Relación entre personas y organizaciones (partidos, bancadas,
-- coaliciones) con rol, fechas y etiqueta legible.
-- ============================================================
CREATE TABLE membership (
    -- ID legible con prefijo M01, M02, ...
    id TEXT PRIMARY KEY,

    -- Referencia a la persona (eliminación en cascada)
    person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE ON UPDATE CASCADE,

    -- Referencia a la organización (eliminación en cascada)
    org_id TEXT NOT NULL REFERENCES organization(id) ON DELETE CASCADE ON UPDATE CASCADE,

    -- Rol dentro de la organización: diputado, senador, suplente, etc.
    rol TEXT NOT NULL,

    -- Descripción legible del cargo (ej: "Diputado plurinominal, Circ. 4")
    label TEXT,

    -- Fecha de inicio de la membresía
    start_date TEXT NOT NULL,

    -- Fecha de fin (NULL significa que está vigente)
    end_date TEXT,

    -- Organización en representación de la cual se ejerce (ej: coalición)
    on_behalf_of TEXT REFERENCES organization(id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

-- ============================================================
-- Tabla 5: post — Cargos legislativos
-- Posiciones específicas dentro de una organización y un área
-- (ej: diputado por un distrito específico en la Cámara).
-- ============================================================
CREATE TABLE post (
    -- ID legible con prefijo T01, T02, ...
    id TEXT PRIMARY KEY,

    -- Organización (cámara) a la que pertenece el cargo
    org_id TEXT NOT NULL REFERENCES organization(id) ON DELETE RESTRICT ON UPDATE RESTRICT,

    -- Área geográfica asociada al cargo (estado/distrito)
    area_id TEXT REFERENCES area(id) ON DELETE RESTRICT ON UPDATE RESTRICT,

    -- Descripción legible del cargo
    label TEXT NOT NULL,

    -- Fecha de inicio del cargo
    start_date TEXT NOT NULL,

    -- Fecha de fin del cargo
    end_date TEXT
);

-- ============================================================
-- Tabla 6: motion — Iniciativas y propuestas legislativas
-- Reformas constitucionales, leyes secundarias, ordinarias.
-- Incluye el tipo de mayoría requerida para su aprobación.
-- ============================================================
CREATE TABLE motion (
    -- ID legible con prefijo Y01, Y02, ...
    id TEXT PRIMARY KEY,

    -- Texto completo o resumen de la iniciativa
    texto TEXT NOT NULL,

    -- Clasificación del tipo de iniciativa
    clasificacion TEXT NOT NULL CHECK(
        clasificacion IN (
            'reforma_constitucional', 'ley_secundaria', 'ordinaria', 'otra'
        )
    ),

    -- Tipo de mayoría requerida para aprobación
    requirement TEXT NOT NULL CHECK(
        requirement IN ('mayoria_simple', 'mayoria_calificada', 'unanime')
    ),

    -- Resultado de la votación (nullable si aún no se vota)
    result TEXT CHECK(
        result IS NULL OR result IN ('aprobada', 'rechazada', 'pendiente', 'retirada')
    ),

    -- Fecha de la votación
    date TEXT,

    -- Periodo legislativo (ej: "LXVI Legislatura")
    legislative_session TEXT,

    -- URL de la fuente oficial de la iniciativa
    fuente_url TEXT
);

-- ============================================================
-- Tabla 7: vote_event — Eventos de votación
-- Instancia específica de una votación en una cámara determinada.
-- Los conteos agregados se derivan de la tabla count (fuente de verdad).
-- ============================================================
CREATE TABLE vote_event (
    -- ID legible con prefijo VE01, VE02, ...
    id TEXT PRIMARY KEY,

    -- Referencia a la iniciativa votada
    motion_id TEXT NOT NULL REFERENCES motion(id) ON DELETE RESTRICT ON UPDATE RESTRICT,

    -- Fecha de inicio del evento de votación
    start_date TEXT NOT NULL,

    -- Cámara que realizó la votación
    organization_id TEXT NOT NULL REFERENCES organization(id) ON DELETE RESTRICT ON UPDATE RESTRICT,

    -- Resultado de la votación
    result TEXT CHECK(
        result IS NULL OR result IN ('aprobada', 'rechazada', 'empate')
    ),

    -- Identificador de la votación en el SITL (votaciont parameter)
    sitl_id INTEGER,

    -- Número de legislators que participaron (para verificación rápida)
    voter_count INTEGER,

    -- Legislatura a la que pertenece (LX, LXI, ..., LXVI)
    legislatura TEXT,

    -- Tipo de mayoría requerida para aprobación (copiado de motion)
    requirement TEXT CHECK(
        requirement IS NULL OR requirement IN ('mayoria_simple', 'mayoria_calificada', 'unanime')
    ),

    -- ID original del portal de origen (senado.gob.mx ID o SITL ID)
    -- Nullable para backward compatibility; usado para deduplicación
    source_id TEXT,

    -- JSON con identificadores externos Popolo (ej: [{"scheme": "senado_gob_mx", "identifier": "1234"}])
    identifiers_json TEXT
);

-- ============================================================
-- Tabla 8: vote — Votos individuales
-- Registro del voto de cada legislador en cada evento de votación.
-- Tabla central para análisis de Shapley/Banzhaf.
-- ============================================================
CREATE TABLE vote (
    -- ID legible con prefijo V01, V02, ...
    id TEXT PRIMARY KEY,

    -- Referencia al evento de votación
    vote_event_id TEXT NOT NULL REFERENCES vote_event(id) ON DELETE CASCADE ON UPDATE CASCADE,

    -- Referencia al legislador que votó
    voter_id TEXT NOT NULL REFERENCES person(id) ON DELETE RESTRICT ON UPDATE RESTRICT,

    -- Opción de voto: a_favor, en_contra, abstención o ausente
    option TEXT NOT NULL CHECK(
        option IN ('a_favor', 'en_contra', 'abstencion', 'ausente')
    ),

    -- Partido o bancada a la que pertenecía en el momento del voto
    "group" TEXT
);

-- ============================================================
-- Tabla 9: count — Conteos de votos por grupo
-- Desglose de votos por partido/grupo en cada evento de votación.
-- ============================================================
CREATE TABLE count (
    -- ID legible con prefijo C01, C02, ...
    id TEXT PRIMARY KEY,

    -- Referencia al evento de votación
    vote_event_id TEXT NOT NULL REFERENCES vote_event(id) ON DELETE CASCADE ON UPDATE CASCADE,

    -- Opción de voto conteada
    option TEXT NOT NULL CHECK(
        option IN ('a_favor', 'en_contra', 'abstencion', 'ausente')
    ),

    -- Número de votos (no negativo)
    value INTEGER NOT NULL CHECK(value >= 0),

    -- Partido que aporta estos votos
    group_id TEXT REFERENCES organization(id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

-- ============================================================
-- Tabla 10: actor_externo — Actores fuera del Congreso
-- Gobernadores, alcaldes, ex presidentes, dirigentes partidistas,
-- jueces y otros actores relevantes para las redes de poder.
-- ============================================================
CREATE TABLE actor_externo (
    -- ID legible con prefijo AE01, AE02, ...
    id TEXT PRIMARY KEY,

    -- Nombre completo del actor externo
    nombre TEXT NOT NULL,

    -- Tipo de actor: gobernador, alcalde, ex_presidente, etc.
    tipo TEXT NOT NULL CHECK(
        tipo IN (
            'gobernador', 'alcalde', 'ex_presidente',
            'dirigente', 'juez', 'otro'
        )
    ),

    -- Área geográfica de influencia (nullable)
    area_id TEXT REFERENCES area(id) ON DELETE RESTRICT ON UPDATE RESTRICT,

    -- Fecha de inicio del cargo o relevancia
    start_date TEXT,

    -- Fecha de fin del cargo o relevancia
    end_date TEXT,

    -- Observaciones sobre el actor y su red de influencia
    observaciones TEXT
);

-- ============================================================
-- Tabla 11: relacion_poder — Redes de poder informales
-- Extensiones Popolo para capturar relaciones de poder que no
-- se reflejan en la estructura formal: lealtades, presión,
-- clientelismo, conflictos, alianzas.
-- ============================================================
CREATE TABLE relacion_poder (
    -- ID legible con prefijo RP01, RP02, ...
    id TEXT PRIMARY KEY,

    -- Tipo de entidad origen: person, organization o actor_externo
    source_type TEXT NOT NULL CHECK(
        source_type IN ('person', 'organization', 'actor_externo')
    ),

    -- ID de la entidad origen
    source_id TEXT NOT NULL,

    -- Tipo de entidad destino: person, organization o actor_externo
    target_type TEXT NOT NULL CHECK(
        target_type IN ('person', 'organization', 'actor_externo')
    ),

    -- ID de la entidad destino
    target_id TEXT NOT NULL,

    -- Tipo de relación de poder
    tipo TEXT NOT NULL CHECK(
        tipo IN (
            'lealtad', 'presion', 'influencia', 'familiar',
            'clientelismo', 'conflicto', 'alianza'
        )
    ),

    -- Peso de la relación (1=muy débil, 5=muy fuerte)
    peso INTEGER NOT NULL CHECK(peso BETWEEN 1 AND 5),

    -- Fecha de inicio de la relación
    start_date TEXT,

    -- Fecha de fin de la relación
    end_date TEXT,

    -- Fuente de la información (URL o referencia)
    fuente TEXT,

    -- Notas adicionales sobre la relación
    nota TEXT
);

-- ============================================================
-- Tabla 12: evento_politico — Eventos políticos relevantes
-- Reformas, votaciones clave, crisis, acuerdos y otros eventos
-- que afectan las dinámicas de poder en el Congreso.
-- ============================================================
CREATE TABLE evento_politico (
    -- ID legible con prefijo EP01, EP02, ...
    id TEXT PRIMARY KEY,

    -- Fecha del evento
    fecha TEXT NOT NULL,

    -- Tipo de evento (libre: reforma, votación, crisis, acuerdo, etc.)
    tipo TEXT NOT NULL,

    -- Descripción detallada del evento
    descripcion TEXT NOT NULL,

    -- Consecuencia o impacto del evento
    consecuencia TEXT,

    -- URL de la fuente del evento
    fuente_url TEXT,

    -- Referencia a la iniciativa legislativa relacionada (nullable)
    motion_id TEXT REFERENCES motion(id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

-- ============================================================
-- ÍNDICES — Para acelerar las consultas más frecuentes
-- ============================================================

-- Índices sobre membership (consultas por persona y por organización)
CREATE INDEX idx_membership_person ON membership(person_id);
CREATE INDEX idx_membership_org ON membership(org_id);

-- Índices sobre vote_event (consultas por iniciativa y source_id)
CREATE INDEX idx_vote_event_motion ON vote_event(motion_id);
CREATE INDEX idx_vote_event_source ON vote_event(source_id);

-- Índices sobre vote_event (filtros principales del sistema)
CREATE INDEX idx_vote_event_legislatura ON vote_event(legislatura);
CREATE INDEX idx_vote_event_org ON vote_event(organization_id);
CREATE INDEX idx_vote_event_start_date ON vote_event(start_date);

-- Índices sobre vote (consultas por votante y por evento)
CREATE INDEX idx_vote_voter ON vote(voter_id);
CREATE INDEX idx_vote_event ON vote(vote_event_id);

-- Índice único: un votante solo puede votar una vez por evento (deduplicación)
CREATE UNIQUE INDEX idx_vote_unique ON vote(vote_event_id, voter_id);

-- Índices sobre count (consultas por evento y por grupo)
CREATE INDEX idx_count_event ON count(vote_event_id);
CREATE INDEX idx_count_group ON count(group_id);

-- Índice único: un conteo por (evento, opción, grupo) (deduplicación)
CREATE UNIQUE INDEX idx_count_unique ON count(vote_event_id, option, group_id);

-- Índices sobre relacion_poder (consultas por origen, destino y tipo)
CREATE INDEX idx_relacion_source ON relacion_poder(source_type, source_id);
CREATE INDEX idx_relacion_target ON relacion_poder(target_type, target_id);
CREATE INDEX idx_relacion_tipo ON relacion_poder(tipo);

-- Índice sobre person (filtrar por corriente interna)
CREATE INDEX idx_person_corriente ON person(corriente_interna);

-- Índice sobre actor_externo (filtrar por tipo)
CREATE INDEX idx_actor_tipo ON actor_externo(tipo);

-- ============================================================
-- TRIGGERS — Validación de integridad de fechas
-- ============================================================

-- Trigger: validar que end_date >= start_date al insertar en person
CREATE TRIGGER trg_person_dates
BEFORE INSERT ON person
WHEN NEW.end_date IS NOT NULL AND NEW.start_date IS NOT NULL
BEGIN
    SELECT CASE WHEN NEW.end_date < NEW.start_date
    THEN RAISE(ABORT, 'end_date debe ser >= start_date en person')
    END;
END;

-- Trigger: validar que end_date >= start_date al actualizar en person
CREATE TRIGGER trg_person_dates_update
BEFORE UPDATE ON person
WHEN NEW.end_date IS NOT NULL AND NEW.start_date IS NOT NULL
BEGIN
    SELECT CASE WHEN NEW.end_date < NEW.start_date
    THEN RAISE(ABORT, 'end_date debe ser >= start_date en person')
    END;
END;

-- Trigger: validar que end_date >= start_date al insertar en membership
CREATE TRIGGER trg_membership_dates
BEFORE INSERT ON membership
WHEN NEW.end_date IS NOT NULL
BEGIN
    SELECT CASE WHEN NEW.end_date < NEW.start_date
    THEN RAISE(ABORT, 'end_date debe ser >= start_date en membership')
    END;
END;

-- Trigger: validar que end_date >= start_date al actualizar en membership
CREATE TRIGGER trg_membership_dates_update
BEFORE UPDATE ON membership
WHEN NEW.end_date IS NOT NULL
BEGIN
    SELECT CASE WHEN NEW.end_date < NEW.start_date
    THEN RAISE(ABORT, 'end_date debe ser >= start_date en membership')
    END;
END;
