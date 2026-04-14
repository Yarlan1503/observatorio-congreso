# Arquitectura — Observatorio del Congreso

> Documentación técnica de referencia post-refactorización.
> Generada a partir del código fuente real. No contiene datos inventados.

---

## 1. Visión General

**Observatorio del Congreso** es un sistema de análisis cuantitativo del poder legislativo mexicano (Cámara de Diputados + Senado de la República). Extrae votaciones nominales desde portales oficiales, las almacena en una base SQLite con modelo Popolo-Graph, y provee scripts de análisis (co-votación, NOMINATE, centralidad, índices de poder).

### Stack

| Componente | Tecnología | Notas |
|---|---|---|
| Lenguaje | Python 3.12+ | Type hints, dataclasses, match |
| HTTP Diputados | `httpx` | SITL/INFOPAL — sin WAF |
| HTTP Senado | `curl_cffi` | Portal LXVI — WAF Incapsula |
| Parsing | `beautifulsoup4` + `lxml` | HTML legacy, mixed encodings |
| Modelado | `pydantic` v2 (Diputados), `dataclasses` (Senado) | Validación de datos parseados |
| Base de datos | SQLite (WAL mode) | `db/congreso.db` |
| Build | `hatchling` (pyproject.toml) | `uv` como package manager |
| Linting | `ruff` (lint + format) | Target Python 3.12 |
| Testing | `pytest` | `tests/` + `db/tests/` |

### Estructura de Directorios

```
observatorio-congreso/
├── scraper_congreso/          # Paquete principal de scraping
│   ├── diputados/             # Scraper SITL/INFOPAL
│   │   ├── __main__.py        # Entry point: python -m scraper_congreso.diputados
│   │   ├── pipeline.py        # Orquestador ScraperPipeline + CLI
│   │   ├── client.py          # SITLClient (httpx, cache SHA256, retry)
│   │   ├── config.py          # Paths, URLs, mapeos de partidos, legislaturas
│   │   ├── legislatura.py     # Constructores de URLs por legislatura
│   │   ├── models.py          # Modelos Pydantic (VotacionRecord, etc.)
│   │   ├── transformers.py    # SITL → Popolo-Graph (dataclasses intermedias)
│   │   ├── loader.py          # Upsert a SQLite (INSERT OR IGNORE)
│   │   └── parsers/           # Parsers HTML → modelos Pydantic
│   │       ├── votaciones.py  # Listado general por periodo
│   │       ├── desglose.py    # Desglose estadístico por partido
│   │       ├── nominal.py     # Listado nominal por partido
│   │       ├── diputado.py    # Ficha curricular individual
│   │       └── composicion.py # Composición del pleno
│   ├── senadores/             # Scraper portal del Senado
│   │   ├── client.py          # SenadoLXVIClient (curl_cffi, anti-WAF 5 capas)
│   │   ├── config.py          # Paths, URLs, config anti-WAF
│   │   ├── models.py          # Dataclasses (SenVotacionDetail, etc.)
│   │   ├── votaciones/        # Scraper de votaciones nominales
│   │   │   ├── __main__.py    # Entry point
│   │   │   ├── cli.py         # Pipeline + CLI (SenadoCongresoPipeline)
│   │   │   ├── loader.py      # CongresoLoader → congreso.db
│   │   │   ├── transformers.py # Transformación a CongresoVotacionRecord
│   │   │   └── parsers/
│   │   │       └── lxvi_portal.py  # Parser HTML portal LXVI
│   │   └── perfiles/          # Scraper de perfiles de senadores
│   │       ├── __main__.py    # Entry point
│   │       ├── scraper.py     # Pipeline + CLI (PerfilPipeline)
│   │       └── parsers/
│   │           └── perfil_parser.py  # Parser HTML perfiles
│   └── utils/                 # Utilidades compartidas
│       ├── id_generator.py    # Generación de IDs con prefijo por cámara
│       ├── db_helpers.py      # get_or_create_organization()
│       ├── db_utils.py        # match_persona_por_nombre()
│       ├── text_utils.py      # normalize_name(), determinar_requirement(), MESES_ES
│       └── logging_config.py  # RotatingFileHandler + console handler
├── db/                        # Base de datos y schema
│   ├── schema.sql             # Schema Popolo-Graph (12 tablas)
│   ├── senado_schema.sql      # Schema legacy del Senado (no usado en congreso.db)
│   ├── init_db.py             # Inicialización: schema + seed data
│   ├── constants.py           # Mapeos de partidos, legislaturas, funciones dinámicas
│   ├── migrations/            # Scripts de migración one-shot (~25 scripts)
│   └── tests/                 # Tests de helpers de BD
├── analysis/                  # Scripts de análisis
│   ├── covotacion.py          # Matrices de co-votación
│   ├── covotacion_dinamica.py # Co-votación temporal (ventanas deslizantes)
│   ├── nominate.py            # NOMINATE (dimensiones ideológicas)
│   ├── centralidad.py         # Centralidad en redes de co-votación
│   ├── comunidades.py         # Detección de comunidades (Louvain)
│   ├── poder_empirico.py      # Índice de poder empírico
│   ├── poder_partidos.py      # Poder por partido
│   ├── evolucion_partidos.py  # Evolución temporal de partidos
│   ├── efecto_genero.py       # Análisis de brecha de género
│   ├── efecto_curul_tipo.py   # Efecto del tipo de curul
│   ├── trayectorias.py        # Trayectorias legislativas
│   ├── visualizacion*.py      # Scripts de visualización (matplotlib)
│   ├── run_*.py               # Runners con CLI argparse
│   ├── scripts/               # Scripts auxiliares (export JSON)
│   └── analisis-bicameral/    # Análisis bicameral (Diputados + Senado)
├── tests/                     # Suite de tests
│   ├── test_scraping_validation.py
│   ├── test_text_utils.py
│   ├── diputados/
│   └── senadores/
│       ├── test_waf_detection.py
│       └── test_transformers.py
├── scripts/                   # Shell scripts de operación
│   ├── scrape_diputados_all.sh
│   ├── scrape_senado_votaciones.sh
│   ├── scrape_senado_perfiles.sh
│   ├── backup_db.sh
│   ├── clean_cache.sh
│   └── run_backfill_fichas.sh
├── cache/                     # Caché HTML (SHA256 filenames)
├── logs/                      # Logs rotativos (10MB, 5 backups)
└── pyproject.toml             # Config del proyecto
```

---

## 2. Componentes

### 2.1 Scraper de Diputados (`scraper_congreso/diputados/`)

Extrae votaciones nominales del sistema SITL/INFOPAL de la Cámara de Diputados.

**Arquitectura por capas:**

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Client | `client.py` | HTTP con httpx, caché SHA256, retry exponencial, rate limiting |
| Parsers | `parsers/*.py` | HTML → modelos Pydantic (votaciones, desglose, nominal, fichas) |
| Transformers | `transformers.py` | Modelos Pydantic → dataclasses Popolo (ID generation, deduplicación) |
| Loader | `loader.py` | Dataclasses Popolo → SQLite (upsert transaccional) |
| Pipeline | `pipeline.py` | Orquestación: client → parsers → transformers → loader |
| Config | `config.py` | Paths, URLs, mapeos partido↔SITL ID, datos de legislaturas LX-LXVI |
| Models | `models.py` | Pydantic v2: VotacionRecord, DesgloseVotacion, NominalVotacion, etc. |

**Modelos de datos (Pydantic):**

```
VotacionRecord        → Registro del listado general (sitl_id, titulo, fecha, periodo)
DesgloseVotacion      → Desglose por partido (lista de DesglosePartido + totales)
DesglosePartido       → Votos de un partido: a_favor, en_contra, abstencion, ausente, total
NominalVotacion       → Listado nominal de un partido (sitl_id, votos[])
VotoNominal           → Voto individual: numero, nombre, sentido, diputado_sitl_id
FichaDiputado         → Ficha curricular: nombre, principio_eleccion, entidad, distrito, etc.
ComposicionPleno      → Composición del pleno por partido
```

**Modelos intermedios (dataclasses Popolo):**

```
VotacionCompleta      → Contenedor: vote_event + votes + counts + new_persons + new_memberships
VoteEventPopolo       → Datos de vote_event + motion (se insertan juntos)
VotePopolo            → Voto individual: id, vote_event_id, voter_id, option, group
CountPopolo           → Conteo por partido: id, vote_event_id, option, value, group_id
PersonPopolo          → Nueva persona: id, nombre, identifiers_json, start_date, end_date
MembershipPopolo      → Nueva membresía: id, person_id, org_id, rol, label
```

**Legislaturas soportadas:** LX (2006-2009) a LXVI (2024-2027). Las URLs cambian de estructura:
- LX-LXIII: subdominios propios (`sitllx.diputados.gob.mx`, etc.)
- LXIV-LXVI: path prefix en dominio principal (`/LXIV_leg/`, `/LXV_leg/`, `/LXVI_leg/`)

### 2.2 Scraper del Senado (`scraper_congreso/senadores/`)

Dos sub-scrapers con propósitos distintos:

#### Votaciones (`senadores/votaciones/`)

Extrae votaciones nominales del portal LXVI del Senado (`senado.gob.mx/66/votacion/{id}`).

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Client | `client.py` | `SenadoLXVIClient` — curl_cffi con anti-WAF de 5 capas |
| Parser | `parsers/lxvi_portal.py` | HTML página principal + AJAX → `SenVotacionDetail` + `list[SenVotoNominal]` |
| Transformer | `transformers.py` | Datos parseados → `CongresoVotacionRecord` (formato loader) |
| Loader | `loader.py` | `CongresoLoader` → congreso.db (INSERT OR IGNORE) |
| Pipeline | `cli.py` | `SenadoCongresoPipeline` — orquestación completa |

**Modelos de datos (dataclasses):**

```
SenVotacionDetail     → Metadata: fecha, periodo, descripcion, conteos, counts_por_partido
SenVotoNominal        → Voto individual: numero, nombre, grupo_parlamentario, voto
SenCountPorPartido    → Conteo por partido: partido, a_favor, en_contra, abstencion
```

**Particularidades del portal del Senado:**
- Requiere 2 requests por votación: GET página principal + POST AJAX
- AJAX endpoint: `POST /66/app/votaciones/functions/viewTableVot.php`
- IDs secuenciales (1 a 5070+), abarcando LX-LXVI
- Protegido por WAF Incapsula (ver sección 6)

#### Perfiles (`senadores/perfiles/`)

Enriquece datos de personas (género, curul_tipo) desde perfiles del portal.

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Client | `scraper.py` (`PerfilClient`) | Reusa `SenadoLXVIClient` (composición), comparte cookies |
| Parser | `parsers/perfil_parser.py` | HTML perfil → `SenPerfil` (nombre, género, curul_tipo, estado, partido) |
| Enricher | `scraper.py` (`PerfilEnricher`) | Match por nombre + UPDATE person / INSERT membership |
| Pipeline | `scraper.py` (`PerfilPipeline`) | Orquestación con manejo de SessionBurnedError |

**Modos de operación:**
- `--from-listing`: scrapea páginas de listado para obtener IDs reales de senadores LXVI
- `--range START END`: itera IDs secuenciales (randomiza si > 200)
- `--test-id N`: procesa un solo perfil

### 2.3 Utilidades Compartidas (`scraper_congreso/utils/`)

| Archivo | Funciones | Uso |
|---|---|---|
| `id_generator.py` | `next_id()`, `get_next_id_batch()` | IDs secuenciales con prefijo por cámara |
| `db_helpers.py` | `get_or_create_organization()` | Lookup/creación de organizaciones (evita duplicados) |
| `db_utils.py` | `match_persona_por_nombre()` | Matching fuzzy de nombres normalizados |
| `text_utils.py` | `normalize_name()`, `determinar_requirement()`, `determinar_tipo_motion()`, `MESES_ES` | Normalización y clasificación compartida |
| `logging_config.py` | `setup_logging()` | RotatingFileHandler (10MB, 5 backups) + console WARNING |

### 2.4 Base de Datos (`db/`)

| Archivo | Propósito |
|---|---|
| `schema.sql` | Schema Popolo-Graph: 12 tablas, índices, triggers |
| `senado_schema.sql` | Schema legacy del Senado (BD independiente, no usado en congreso.db) |
| `init_db.py` | Inicialización idempotente: schema + seed data (orgs, áreas, actores) |
| `constants.py` | Mapeos partido→org_id, legislaturas, funciones dinámicas desde BD |
| `migrations/` | ~25 scripts de migración one-shot (backfill, fixes, deduplicación) |

**Seed data en `init_db.py`:**
- Organizations: O08 (Cámara de Diputados), O09 (Senado), O10 (Sigamos Haciendo Historia)
- Areas: 32 entidades federativas (A01-Aguascalientes a A32-Zacatecas)
- Actores externos: 16 actores (AE01-AMLO a AE16-Kenia López Rabadán)

### 2.5 Análisis (`analysis/`)

Scripts de análisis que leen de `congreso.db`. Grupo de dependencias `[analysis]` en pyproject.toml.

| Script | Análisis |
|---|---|
| `covotacion.py` | Matrices de co-votación estática |
| `covotacion_dinamica.py` | Co-votación temporal (ventanas deslizantes) |
| `nominate.py` | NOMINATE (posición ideológica en 2 dimensiones) |
| `centralidad.py` | Centralidad en redes de co-votación |
| `comunidades.py` | Detección de comunidades (algoritmo Louvain) |
| `poder_empirico.py` | Índice de poder empírico |
| `poder_partidos.py` | Poder por partido político |
| `evolucion_partidos.py` | Evolución temporal del poder de partidos |
| `efecto_genero.py` | Brecha de género en patrones de votación |
| `efecto_curul_tipo.py` | Efecto del tipo de curul en disciplina |
| `trayectorias.py` | Trayectorias legislativas longitudinales |
| `visualizacion*.py` | Visualizaciones (matplotlib): poder, NOMINATE, dinámica, artículo |

Cada script de análisis tiene un runner `run_*.py` con CLI argparse.

---

## 3. Flujo de Datos

### 3.1 Diputados — Pipeline Completo

```
                          SITL/INFOPAL
                         (sitl.diputados.gob.mx)
                               │
                               ▼
                    ┌─────────────────────┐
                    │    SITLClient       │  httpx GET
                    │  (client.py)        │  + cache SHA256
                    │  + rate limit 2s    │  + retry exponencial
                    └────────┬────────────┘
                             │ HTML
                             ▼
              ┌──────────────────────────────┐
              │         Parsers              │
              │  (parsers/*.py)              │
              │                              │
              │  votaciones.py → list[VotacionRecord]
              │  desglose.py   → DesgloseVotacion    │
              │  nominal.py    → NominalVotacion     │
              └──────────────┬───────────────┘
                             │ Modelos Pydantic
                             ▼
              ┌──────────────────────────────┐
              │    Transformers              │
              │  (transformers.py)           │
              │                              │
              │  - Generar IDs (id_generator)│
              │  - Match personas por nombre │
              │  - Crear organizaciones      │
              │  - Clasificar motions        │
              │  - Determinar resultados     │
              └──────────────┬───────────────┘
                             │ VotacionCompleta (dataclasses Popolo)
                             ▼
              ┌──────────────────────────────┐
              │        Loader                │
              │  (loader.py)                 │
              │                              │
              │  Transacción única:          │
              │  1. INSERT motion            │
              │  2. INSERT vote_event        │
              │  3. INSERT person (nuevas)   │
              │  4. INSERT membership (nuevas)│
              │  5. INSERT vote (todos)      │
              │  6. INSERT count (todos)     │
              └──────────────┬───────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   congreso.db   │  SQLite (WAL mode)
                    │  (Popolo-Graph) │
                    └─────────────────┘
```

**Flujo detallado por votación (`_scrape_single_votacion`):**

1. `url_votaciones_por_periodo(leg, periodo)` → GET HTML del listado
2. `parse_votaciones(html, periodo)` → lista de `VotacionRecord`
3. Por cada votación:
   - `url_estadistico(leg, sitl_id)` → GET desglose → `parse_desglose()` → `DesgloseVotacion`
   - Por cada partido con diputados: `url_nominal(leg, party_sitl_id, sitl_id)` → GET nominal → `parse_nominal()` → `NominalVotacion`
4. `transformar_votacion(votacion, desglose, nominales, conn, legislatura)` → `VotacionCompleta`
5. `Loader.upsert_votacion(votacion_completa)` → INSERT OR IGNORE en transacción

### 3.2 Senado — Pipeline de Votaciones

```
                    Portal del Senado
                  (senado.gob.mx/66/)
                         │
                         ▼
              ┌──────────────────────┐
              │  SenadoLXVIClient    │  curl_cffi impersonate
              │  (client.py)         │  + anti-WAF 5 capas
              │  + cookies pickle    │  + cache SHA256
              └────────┬─────────────┘
                       │
            ┌──────────┴──────────┐
            │                     │
            ▼                     ▼
    GET /66/votacion/{id}   POST /66/app/.../viewTableVot.php
    (página principal)       (AJAX tabla de votos)
            │                     │
            └──────────┬──────────┘
                       │ (page_html, ajax_html)
                       ▼
              ┌──────────────────────┐
              │  parse_lxvi_votacion │  (parsers/lxvi_portal.py)
              │                      │
              │  → SenVotacionDetail │
              │  → list[SenVotoNominal]
              └────────┬─────────────┘
                       │
                       ▼
              ┌──────────────────────────────┐
              │  _transform_to_congreso_record│  (cli.py)
              │                               │
              │  - parse_fecha_iso()          │
              │  - inferir_genero()           │
              │  - Build counts_por_partido   │
              └────────┬──────────────────────┘
                       │ CongresoVotacionRecord
                       ▼
              ┌──────────────────────┐
              │   CongresoLoader     │  (loader.py)
              │   → congreso.db      │
              └──────────────────────┘
```

---

## 4. Schema Popolo-Graph

### 4.1 Tablas

Schema definido en `db/schema.sql`. Combina el estándar Popolo (parlamentario) con extensiones para redes de poder informales.

| # | Tabla | Prefijo ID | Propósito |
|---|---|---|---|
| 1 | `area` | `A01` | Divisiones geográficas (32 estados, distritos, circunscripciones) |
| 2 | `organization` | `O01` | Organizaciones políticas (partidos, bancadas, coaliciones, instituciones) |
| 3 | `person` | `P00001` | Legisladores y actores políticos (campos: corriente_interna, vulnerabilidad) |
| 4 | `membership` | `M_D/M_S` | Pertenencia persona↔organización con rol y fechas |
| 5 | `post` | `T00001` | Cargos legislativos (posición en org + área) |
| 6 | `motion` | `Y_D/Y_S` | Iniciativas legislativas (clasificación, requirement, result) |
| 7 | `vote_event` | `VE_D/VE_S` | Eventos de votación (instancia de una votación en una cámara) |
| 8 | `vote` | `V_D/V_S` | Votos individuales (legislador × evento) |
| 9 | `count` | `C00001` | Conteos agregados por partido en cada evento |
| 10 | `actor_externo` | `AE01` | Actores fuera del Congreso (gobernadores, dirigentes, etc.) |
| 11 | `relacion_poder` | `RP01` | Redes de poder informales (lealtad, presión, influencia, etc.) |
| 12 | `evento_politico` | `EP01` | Eventos políticos relevantes (reformas, crisis, acuerdos) |

### 4.2 Esquema de Prefijos de ID

Los IDs son legibles e incluyen la cámara de origen cuando aplica. Padding de 5 dígitos.

| Entidad | Diputados | Senado | Global |
|---|---|---|---|
| `vote_event` | `VE_D00001` | `VE_S00001` | — |
| `vote` | `V_D00001` | `V_S00001` | — |
| `motion` | `Y_D00001` | `Y_S00001` | — |
| `membership` | `M_D00001` | `M_S00001` | — |
| `person` | — | — | `P00001` |
| `count` | — | — | `C00001` |
| `post` | — | — | `T00001` |
| `organization` | — | — | `O01` (2 dígitos) |
| `area` | — | — | `A01` (2 dígitos) |
| `actor_externo` | — | — | `AE01` (2 dígitos) |
| `relacion_poder` | — | — | `RP01` (2 dígitos) |
| `evento_politico` | — | — | `EP01` (2 dígitos) |

### 4.3 Generación de IDs

Implementado en `scraper_congreso/utils/id_generator.py`.

```python
# IDs por cámara
next_id(conn, "vote_event", camara="D")  # → "VE_D00042"
next_id(conn, "vote", camara="S")        # → "V_S00103"

# IDs globales
next_id(conn, "person")                  # → "P00015"
next_id(conn, "count")                   # → "C00250"

# Batch (eficiente para múltiples inserts)
get_next_id_batch(conn, "vote", camara="D", count=100)
# → ["V_D00200", "V_D00201", ..., "V_D00299"]
```

La función `next_id()` consulta `MAX(id)` en la tabla para el prefijo dado y genera el siguiente secuencial. `get_next_id_batch()` consulta una vez y genera N IDs consecutivos.

### 4.4 Organizaciones Semilla

`init_db.py` inserta organizaciones base. Los partidos se crean dinámicamente por `get_or_create_organization()`:

| ID | Nombre | Abbr | Clasificación |
|---|---|---|---|
| O08 | Cámara de Diputados | Diputados | institucion |
| O09 | Senado de la República | Senado | institucion |
| O10 | Sigamos Haciendo Historia | Sigamos Haciendo Historia | coalicion |

Partidos creados dinámicamente (ejemplos):

| ID | Nombre | Abbr | SITL ID |
|---|---|---|---|
| O01 | Morena | MORENA | 14 |
| O04 | Partido Acción Nacional | PAN | 3 |
| O05 | Partido Revolucionario Institucional | PRI | 1 |
| O03 | Partido Verde Ecologista de México | PVEM | 5 |
| O02 | Partido del Trabajo | PT | 4 |
| O06 | Movimiento Ciudadano | MC | 6 |
| O07 | Partido de la Revolución Democrática | PRD | 2 |
| O11 | Independientes | IND | 9 |

### 4.5 Índices

Definidos en `schema.sql` para las consultas más frecuentes:

- `idx_membership_person`, `idx_membership_org` — Búsqueda de membresías
- `idx_vote_event_motion`, `idx_vote_event_source` — Búsqueda de eventos por motion/source_id
- `idx_vote_voter`, `idx_vote_event` — Búsqueda de votos
- `idx_count_event`, `idx_count_group` — Conteos agregados
- `idx_relacion_source`, `idx_relacion_target`, `idx_relacion_tipo` — Redes de poder
- `idx_person_corriente` — Filtrar por corriente interna
- `idx_actor_tipo` — Filtrar actores por tipo

### 4.6 Triggers

Validación de integridad de fechas (end_date >= start_date):

- `trg_person_dates` / `trg_person_dates_update` — INSERT/UPDATE en `person`
- `trg_membership_dates` / `trg_membership_dates_update` — INSERT/UPDATE en `membership`

---

## 5. Entry Points CLI

### 5.1 Diputados

```bash
# Scrapear votaciones de un periodo
python -m scraper_congreso.diputados --leg LXVI --periodo 1 --limit 5

# Scrapear una votación individual por SITL ID
python -m scraper_congreso.diputados --sitl-id 1234

# Scrapear todos los periodos de una legislatura
python -m scraper_congreso.diputados --leg LXVI --all-periods

# Estadísticas de la BD
python -m scraper_congreso.diputados --stats
```

**Flags:**

| Flag | Tipo | Default | Descripción |
|---|---|---|---|
| `--leg` | str | `LXVI` | Legislatura (LX, LXI, ..., LXVI) |
| `--periodo` | int | `1` | Periodo legislativo |
| `--limit` | int | None | Máximo votaciones a procesar |
| `--sitl-id` | int | None | Votación individual por SITL ID |
| `--all-periods` | flag | — | Descubrir y scrapear todos los periodos |
| `--no-cache` | flag | — | Desactivar caché HTML |
| `--delay` | float | `2.0` | Delay entre requests (segundos) |
| `--stats` | flag | — | Mostrar estadísticas de la BD y salir |

### 5.2 Senado — Votaciones

```bash
# Scrapear rango de IDs
python -m scraper_congreso.senadores.votaciones --range 1 5070

# Scrapear rango con límite
python -m scraper_congreso.senadores.votaciones --range 1 100 --limit 10

# Probar un solo ID
python -m scraper_congreso.senadores.votaciones --test-id 1

# Inicializar schema
python -m scraper_congreso.senadores.votaciones --init-schema

# Estadísticas
python -m scraper_congreso.senadores.votaciones --stats
```

**Flags:**

| Flag | Tipo | Default | Descripción |
|---|---|---|---|
| `--range` | int int | — | Rango de IDs (inicio y fin inclusivos) |
| `--test-id` | int | — | Procesar un solo ID |
| `--init-schema` | flag | — | Inicializar schema de congreso.db |
| `--stats` | flag | — | Estadísticas de la BD |
| `--no-cache` | flag | — | Desactivar caché |
| `--delay` | float | `2.0` | Delay entre requests |
| `--limit` | int | None | Máximo votaciones a procesar |

### 5.3 Senado — Perfiles

```bash
# Scrapear desde listados oficiales (recomendado)
python -m scraper_congreso.senadores.perfiles --from-listing

# Dry run (sin cambios en BD)
python -m scraper_congreso.senadores.perfiles --from-listing --limit 10 --dry-run

# Scrapear por rango de IDs
python -m scraper_congreso.senadores.perfiles --range 1 1754

# Probar un solo perfil
python -m scraper_congreso.senadores.perfiles --test-id 1575 --dry-run

# Estadísticas
python -m scraper_congreso.senadores.perfiles --stats
```

**Flags:**

| Flag | Tipo | Default | Descripción |
|---|---|---|---|
| `--from-listing` | flag | — | Obtener IDs de listados oficiales del Senado LXVI |
| `--range` | int int | — | Rango de IDs (inicio y fin inclusivos) |
| `--test-id` | int | — | Procesar un solo ID |
| `--stats` | flag | — | Estadísticas de la BD |
| `--dry-run` | flag | — | Simular sin cambios en BD |
| `--delay` | float | `2.0` | Delay entre requests |
| `--limit` | int | None | Máximo perfiles a procesar |

### 5.4 Inicialización de BD

```bash
# Crear BD desde cero (interactivo, pide confirmación si ya existe)
python db/init_db.py
```

### 5.5 Scripts de Shell

```bash
# Scrapear todas las legislaturas de Diputados (LX a LXVI)
bash scripts/scrape_diputados_all.sh

# Wrapper para scraper de votaciones del Senado (pasa argumentos)
bash scripts/scrape_senado_votaciones.sh --range 1 5070

# Wrapper para scraper de perfiles del Senado (pasa argumentos)
bash scripts/scrape_senado_perfiles.sh --from-listing

# Backup de la BD (VACUUM INTO + integrity check + rotación 7 backups)
bash scripts/backup_db.sh

# Limpieza de caché (archivos > 30 días)
bash scripts/clean_cache.sh
bash scripts/clean_cache.sh --max-age 7 --dry-run

# Backfill de fichas SITL por legislatura
bash scripts/run_backfill_fichas.sh
```

---

## 6. Anti-WAF del Senado (5 Capas)

El portal del Senado (`senado.gob.mx`) está protegido por **WAF Incapsula**. El `SenadoLXVIClient` (`scraper_congreso/senadores/client.py`) implementa 5 capas de evasión:

### Capa 1: curl_cffi Impersonate Pool

```python
_IMPERSONATE_TARGETS = ("chrome", "safari", "chrome116", "chrome131", "edge", "chrome_android")
```

Usa `curl_cffi` con TLS fingerprint de navegadores reales. El pool contiene 6 fingerprints con JA3 hashes distintos. Solo se rota al recrear la sesión (no mid-session).

### Capa 2: Cookies Pickle Persistentes

Las cookies de Incapsula se persisten en `cache/senado/senado_cookies.pkl` vía `pickle`. Al crear una sesión, se cargan cookies previas para mantener la reputación acumulada. Tras un WAF burn, se omiten las cookies quemadas (`skip_existing_cookies=True`).

### Capa 3: Circuit Breaker

```python
WAF_CONSECUTIVE_THRESHOLD = 2
```

Si se detectan 2+ bloqueos WAF consecutivos, se lanza `SessionBurnedError`. El caller debe pausar y reanudar, no seguir golpeando.

Detección de WAF (`_is_waf_response()`):
- Status codes: 403, 406, 429, 503
- HTML < 5KB + marcadores: `incident_id`, `waf block`, `forbidden`, `access denied`

### Capa 4: Rotación Proactiva

```python
MAX_REQUESTS_PER_SESSION = 10
```

Cada 10 requests, la sesión se recrea preventivamente con un fingerprint diferente del pool. Esto previene que el WAF detecte patrones de scraping en sesiones largas. Las cookies se conservan en la rotación proactiva.

### Capa 5: Warm-up Post-Burn

Cuando una sesión se quema (WAF burn), el proceso de recuperación es:

1. Rotar al siguiente fingerprint del pool (JA3 distinto)
2. NO cargar cookies quemadas del `.pkl`
3. Hacer GET a la página principal del Senado (`/66/`) para obtener cookies frescas de Incapsula
4. Continuar scraping con la nueva sesión limpia

El `PerfilPipeline` añade pausa exponencial (10min base, 30min max, hasta 3 intentos) cuando recibe `SessionBurnedError`, dando tiempo al WAF a expirar el bloqueo por IP.

### Resumen del flujo anti-WAF

```
Request → ¿Cache HIT? → [return cache]
              │
              ▼ (miss)
         ¿Request count >= 10? → ROTACIÓN PROACTIVA
              │                       │
              ▼                       ├── Nuevo fingerprint (pool)
         curl_cffi GET/POST           ├── Cookies conservadas
              │                       └── Pausa 30s
              ▼
         ¿WAF detectado?
          ├── NO → Guardar cookies → Return HTML
          └── SÍ → Consecutive WAFs++
                    │
                    ├── < 2 → Backoff + Recrear sesión (skip cookies)
                    └── >= 2 → SessionBurnedError
                               │
                               ├── Caller pausa exponencial
                               ├── Nuevo fingerprint
                               ├── NO carga cookies quemadas
                               └── Warm-up GET /66/ → cookies frescas
```

---

## 7. Configuración y Deployment

### 7.1 pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.backends"

[project]
name = "observatorio-congreso"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "curl_cffi>=0.15.0",     # Anti-WAF Senado
    "httpx>=0.27",           # HTTP Diputados
    "beautifulsoup4>=4.12",  # Parsing HTML
    "lxml>=5.0",             # Parser rápido
    "pydantic>=2.5",         # Validación modelos
]

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.11"]
analysis = [
    "numpy>=1.26", "pandas>=2.2", "scipy>=1.12",
    "networkx>=3.2", "python-louvain>=0.16",
    "matplotlib>=3.8", "polars>=0.20",
]
```

### 7.2 Ruff (Lint + Format)

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "SIM", "RUF"]

# Per-file ignores:
# - db/migrations/: sys.path hacks + legacy refs
# - analysis/: exploratory scripts (relaxed)
# - tests/: allow assert
```

### 7.3 Paths Principales

| Path | Propósito |
|---|---|
| `db/congreso.db` | Base de datos principal (SQLite WAL) |
| `cache/` | Caché HTML del scraper de Diputados (SHA256 filenames) |
| `cache/senado/` | Caché HTML del scraper del Senado + cookies pickle |
| `cache/senado_perfiles/` | Caché HTML del scraper de perfiles |
| `logs/` | Logs rotativos (diputados.log, senado_votaciones.log, etc.) |
| `db/backups/` | Backups automáticos (rotación 7) |

### 7.4 Dependencias

**Runtime (siempre necesarias):**
- `curl_cffi>=0.15.0` — Cliente HTTP anti-WAF para Senado
- `httpx>=0.27` — Cliente HTTP para Diputados
- `beautifulsoup4>=4.12` — Parsing HTML
- `lxml>=5.0` — Parser HTML/XML rápido
- `pydantic>=2.5` — Validación de modelos

**Análisis (`[analysis]`):**
- `numpy`, `pandas`, `polars` — Procesamiento de datos
- `scipy` — Optimización (NOMINATE), estadísticas
- `networkx` — Grafos y centralidad
- `python-louvain` — Detección de comunidades
- `matplotlib` — Visualizaciones

**Dev (`[dev]`):**
- `pytest>=8.0` — Testing
- `ruff>=0.11` — Linting y formateo

### 7.5 Setup

```bash
# Instalar con uv (recomendado)
uv sync
uv sync --group analysis  # incluir dependencias de análisis

# Instalar con pip
pip install -e .
pip install -e ".[analysis]"  # si se usan optional deps

# Inicializar BD
python db/init_db.py

# Verificar instalación
python -m scraper_congreso.diputados --stats
python -m scraper_congreso.senadores.votaciones --stats

# Correr tests
pytest
```

### 7.6 Caché

- **Diputados**: Un archivo `.html` por URL, nombrado por `SHA256(url)`. Sin expiración automática — limpiar manualmente con `scripts/clean_cache.sh`.
- **Senado**: Igual esquema SHA256, pero en `cache/senado/`. Cookies pickle en `cache/senado/senado_cookies.pkl`.
- **Perfiles**: `cache/senado_perfiles/`, comparte cookies con votaciones.

---

## Apendice: Convenciones de Código

- **Encoding**: UTF-8 en toda la cadena. Los parsers manejan fallback Latin-1 para HTML legacy del SITL.
- **Fechas**: ISO 8601 (`YYYY-MM-DD`) en la BD. Los parsers convierten formatos locales (`"10 Diciembre 2024"`, `"10/12/2024"`).
- **IDs**: Legibles, con prefijo por cámara, padding 5 dígitos (excepto organizaciones/áreas: 2 dígitos).
- **Idempotencia**: `INSERT OR IGNORE` en toda la cadena. Los pipelines son safe para re-ejecutar.
- **Naming**: `snake_case` para funciones/variables, `PascalCase` para clases, `UPPER_CASE` para constantes.
- **Logging**: Cada módulo usa `logging.getLogger(__name__)`. Config centralizada vía `setup_logging()`.
