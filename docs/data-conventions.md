# Convenciones de Campos — Observatorio del Congreso

Este documento describe las convenciones, limitaciones y cobertura de campos clave en la BD (`db/congreso.db`).

## Campos de identificación

### `vote_event.sitl_id`
- **Cámara**: Solo Diputados
- **Descripción**: Identificador de la votación en el sistema SITL (parámetro `votaciont`)
- **Coverage**: ~99.98% de vote_events de Diputados
- **Relación**: Mutuamente excluyente con `identifiers_json` (Senado usa ese campo)
- **Nota**: El campo unificado `source_id` normaliza ambos orígenes

### `vote_event.identifiers_json`
- **Cámara**: Solo Senado
- **Descripción**: JSON con identificadores externos del portal senado.gob.mx
- **Coverage**: ~100% de vote_events de Senado
- **Relación**: Mutuamente excluyente con `sitl_id`

## Campos de conteo

### `count.group_id`
- **Descripción**: Identificador del partido/grupo para desglose de votos
- **Convención**: `NULL` = totales agregados (favor, contra, abstenciones, ausentes)
- **Patrón**: Cada `vote_event` tiene exactamente 4 counts sin `group_id` (totales)
- **Coverage**: 100% de vote_events tienen counts agregados

## Campos de fechas

### `membership.start_date` / `membership.end_date`
- **Descripción**: Periodo de la membresía legislativa
- **Convención**: Fechas constitucionales (1 sep → 31 ago), NO fecha efectiva de toma de posesión
- **Precisión**: ±13 días (algunas fechas reales de toma de protesta difieren)
- **Coverage (post-backfill)**:
  - `start_date`: 100% (8957/8957)
  - `end_date`: 99.4% (8904/8957, 53 NULL = vigentes + otros roles)
- **Fuente**: `LEGISLATURAS` en `db/constants.py` — fechas constitucionales LX-LXVI
- **Nota**: Diputados sirven 3 años por legislatura; senadores sirven periodos de 3 años dentro de su término de 6 años

## Campos de partido/organización

### `organization.fundacion` / `organization.disolucion`
- **Descripción**: Fechas de registro INE del partido político
- **Coverage**: 11/18 organizaciones con fechas (partidos formales)
- **Sin fecha**: Instituciones (Cámara, Senado), coaliciones, independientes, Sin Partido
- **Fuente**: Registro público IFE/INE
- **Ver script**: `db/migrations/backfill_org_fechas.py`

### `membership.on_behalf_of`
- **Descripción**: Partido bajo coalición electoral (cuando un candidato fue postulado por coalición)
- **Coverage**: Techo ~35-40%
- **Limitación**: Sin fuente estructurada disponible
- **Nota**: Requiere cruce manual con registros de coaliciones del INE

## Campos de persona

### `person.fecha_nacimiento`
- **Descripción**: Fecha de nacimiento del legislador
- **Coverage**: Techo ~65%
- **Limitación**: Legisladores históricos (LX-LXIII) sin datos biográficos en fuentes digitales
- **Fuente**: Curriculas del SITL (Diputados), fichas del Senado

### `person.genero`
- **Valores**: 'M' (masculino), 'F' (femenino), NULL (desconocido)
- **Coverage**: 97.9% (4738/4840 clasificados)
- **Distribución**: M=2771, F=1967, NULL=102
- **Fuente**: CSVs oficiales (LXV-LXVI) + heurística de primer nombre (LX-LXIV)
- **Limitación**: 102 NULLs son nombres genuinamente ambiguos (María, Jesús, Guadalupe, etc.)
- **Ver script**: `db/migrations/backfill_genero.py`

### `person.curul_tipo`
- **Valores**: 'mayoria_relativa', 'plurinominal', 'suplente', NULL
- **Descripción**: Tipo de curul del legislador
- **Coverage**:
  - Diputados LXV-LXVI: ~97% (vía scraping SITL)
  - Senadores (con labels detallados): ~86% (vía regex en membership.label)
  - Diputados LX-LXIV y senadores con labels genéricos: pendiente
- **Mapeo de Senado**:
  - "por Lista Nacional" → plurinominal
  - "por [Estado]" → mayoria_relativa (incluye 1a fórmula y 1a minoría)
  - Labels genéricos → NULL (sin información de tipo)
- **Nota**: El schema CHECK solo permite los 3 valores listados. Para Senado, 1a fórmula y 1a minoría se mapean al mismo valor (mayoria_relativa) pues no hay fuente para distinguirlas.
- **Ver scripts**: `db/migrations/fix_curul_tipo.py`, `db/migrations/backfill_curul_tipo_senadores.py`

## Constantes de referencia

### LEGISLATURAS (`db/constants.py`)
- **Fuente**: `diputados/scraper/config.py`
- **Contenido**: 7 legislaturas (LX-LXVI) con fechas constitucionales
- **Uso**: Proxy para `membership.start_date`/`end_date` cuando no hay fecha exacta

## Scripts de backfill disponibles

| Script | Tabla afectada | Campos | Descripción |
|--------|---------------|--------|-------------|
| `backfill_org_fechas.py` | organization | fundacion, disolucion | Fechas INE de partidos |
| `backfill_membership_fechas.py` | membership | start_date, end_date | Fechas constitucionales |
| `backfill_curul_tipo_senadores.py` | person | curul_tipo | Tipo de curul para senadores |
| `backfill_genero.py` | person | genero | Clasificación por nombre |
| `fix_curul_tipo.py` | person | curul_tipo | Tipo de curul para diputados (scraping SITL) |

Todos los scripts son **idempotentes** — pueden ejecutarse múltiples veces sin efectos secundarios.
