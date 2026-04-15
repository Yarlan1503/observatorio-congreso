# Migraciones de Base de Datos

## Estado General

- **BD**: `db/congreso.db` (~337MB)
- **Total scripts**: 25 Python
- **Estado**: Todos los scripts críticos ya están **aplicados**. BD limpia (0 FK violations).
- **Idempotencia**: Todos los scripts son **idempotentes** — seguros de re-ejecutar.

## Orden de Ejecución Recomendado

Los scripts se agrupan por propósito. Dentro de cada grupo, el orden importa.

### Grupo 1: Schema — Agregar columnas e índices

Aplicar **primero**, sobre BD limpia o existente. No dependen de datos.

| # | Script | Qué hace | Tablas | Estado |
|---|--------|----------|--------|--------|
| 1.1 | `add_source_id.py` | Agrega columna `source_id` (TEXT) + índice a `vote_event` | vote_event | ✅ Aplicado |
| 1.2 | `add_requirement_column.py` | Agrega columna `requirement` (TEXT con CHECK) a `vote_event`, puebla desde `motion.requirement` | vote_event, motion | ✅ Aplicado |

### Grupo 2: Datos semilla — Caso cero

Inserta datos de referencia para la reforma electoral de Sheinbaum (marzo 2026).

| # | Script | Qué hace | Tablas | Estado |
|---|--------|----------|--------|--------|
| 2.1 | `migrate_caso_cero.py` | Inserta 27 personas, 63 memberships, 24 posts, 2 motions, 2 VEs, 24 votos, 12 counts, 18 relaciones de poder, 3 eventos políticos | person, membership, post, motion, vote_event, vote, count, relacion_poder, evento_politico | ✅ Aplicado |

### Grupo 3: Correcciones de datos — Clasificación y FKs

Corrige datos mal clasificados por scrapers. **Ejecutar antes de backfills.**

| # | Script | Qué hace | Tablas | Dependencias | Estado |
|---|--------|----------|--------|--------------|--------|
| 3.1 | `fix_lxv_senado.py` | Reclasifica ~835 VEs del Senado LXV mal etiquetadas como LXVI (por rango de fechas) | vote_event | — | ✅ Aplicado (LXV=841, LXVI=357) |
| 3.2 | `fix_fk_violations.py` | Mapea org_ids legacy (O01-O07) → IDs reales (O11-O18) en memberships y counts | membership, count | — | ✅ Aplicado (0 FK violations) |
| 3.3 | `fix_vote_group.py` | Convierte `vote.group` de texto ("Morena", "PT") → IDs de organización ("O01", "O02") | vote | **Después de `fix_duplicados.py`** | ✅ Aplicado (0 non-org groups) |
| 3.4 | `backfill_requirement.py` | Rellena `vote_event.requirement` NULL desde `motion.requirement`, infiere del título si es necesario | vote_event, motion | **Después de `add_requirement_column.py`** | ✅ Aplicado (0 NULLs) |

### Grupo 4: Deduplicación — Eliminar registros duplicados

Elimina duplicados insertados por el pipeline ETL. **Orden estricto.**

| # | Script | Qué hace | Tablas | Dependencias | Estado |
|---|--------|----------|--------|--------------|--------|
| 4.1 | `fix_duplicados.py` | Elimina votos duplicados (mismo voter_id + vote_event_id + group + option). Crea backup. | vote | — | ✅ Aplicado |
| 4.2 | `deduplicar_votos_diputados.py` | Deduplica votos globalmente (keep MIN id por vote_event_id+voter_id) + counts (keep MIN id por vote_event_id+option+group_id). Agrega UNIQUE constraints. Recalcula voter_count. VACUUM. | vote, count, vote_event | — | ✅ Aplicado (índices UNIQUE existen) |
| 4.3 | `deduplicar_counts_diputados.py` | Deduplica counts globales de Diputados (group_id NULL), recrea desde SUM de per-party counts. Recalcula voter_count. | count, vote_event | **Después de 4.2** | ✅ Aplicado |

### Grupo 5: Limpieza — Eliminar datos basura

Elimina organizaciones basura y VEs fantasma. **Después de deduplicación.**

| # | Script | Qué hace | Tablas | Dependencias | Estado |
|---|--------|----------|--------|--------------|--------|
| 5.1 | `limpiar_fantasmas_y_total.py` | Elimina VEs fantasma (0 votos) + orgs basura (O24, O29-O31) + counts asociados | vote_event, count, organization | — | ✅ Aplicado |

### Grupo 6: Recálculo — Corregir resultados de votaciones

Recalcula resultados y voter_counts con lógica corregida.

| # | Script | Qué hace | Tablas | Dependencias | Estado |
|---|--------|----------|--------|--------------|--------|
| 6.1 | `recalcular_resultados.py` | Recalcula `vote_event.result` y `motion.result` con lógica corregida (calificada = 2/3 de presentes) | vote_event, motion | **Después de deduplicación** | ✅ Aplicado |
| 6.2 | `recalcular_ve_senado_v2.py` | Recalcula VEs del Senado usando `COUNT(*) FROM vote` (para VEs donde count estaba vacío) | vote_event, motion | **Después de 6.1** | ✅ Aplicado |

### Grupo 7: Backfills — Enriquecer datos desde fuentes externas

Requiere conectividad (SITL, Wikidata). Puede ejecutarse múltiples veces.

| # | Script | Qué hace | Tablas | Fuente | Estado |
|---|--------|----------|--------|--------|--------|
| 7.1 | `backfill_org_fechas.py` | Puebla `fundacion`/`disolucion` de organizaciones (partidos) con fechas verificadas del INE | organization | Hardcodeado (INE) | ✅ Aplicado (13 orgs con fecha) |
| 7.2 | `backfill_genero.py` | Puebla `person.genero` desde CSVs de Nolan (LXV/LXVI) + heurística de primer nombre (LX-LXIV) | person | CSVs + diccionario hardcodeado | ✅ Aplicado (4,744/4,840 = 98.0%, 96 NULLs) |
| 7.3 | `backfill_fichas_diputados.py` | Puebla `fecha_nacimiento` y `curul_tipo` desde fichas curriculares del SITL | person | SITL (scraping) | ✅ Aplicado (55.5% con fecha_nacimiento) |
| 7.4 | `backfill_wikidata.py` | Puebla `fecha_nacimiento` y `genero` desde Wikidata vía SPARQL (fuzzy matching) | person | Wikidata API | ✅ Aplicado (complementa 7.2 y 7.3) |
| 7.5 | `backfill_membership_fechas.py` | Puebla `start_date`/`end_date` de memberships desde rangos legislativos | membership | LEGISLATURAS de constants.py | ✅ Aplicado (100% start, 99.6%+ end) |
| 7.6 | `backfill_curul_tipo_senadores.py` | Puebla `curul_tipo` para senadores inferido desde labels de membership | person | membership labels | ✅ Aplicado |
| 7.7 | `fix_curul_tipo.py` | Puebla `curul_tipo` para diputados scrapendo fichas del SITL (por sitl_id + match por nombre) | person | SITL (scraping) | ✅ Aplicado (534 NULLs restantes son válidos: sin sitl_id) |
| 7.8 | `fix_curul_tipo_manual.py` | Puebla `curul_tipo` para 13 diputados manuales sin sitl_id (PVEM/PT) | person | SITL (scraping) | ✅ Aplicado |

### Grupo 8: Purga — Eliminar datos corruptos para re-scrape

Elimina datos para permitir re-scrape. **Destructivo** (usa backup).

| # | Script | Qué hace | Tablas | Notas | Estado |
|---|--------|----------|--------|-------|--------|
| 8.1 | `purge_lxv_diputados.py` | Elimina VEs, votos, counts y motions de LXV Diputados (O08) para re-scrape | vote_event, vote, count, motion | Crea backup. Solo para re-scrape. | ⏸️ Pendiente (no necesario si datos OK) |

## Dependencias Explícitas

```
add_requirement_column.py  →  backfill_requirement.py     (columna debe existir antes de rellenar)
add_source_id.py           →  scrapers (usado durante scraping, no depende de otros scripts)
fix_duplicados.py          →  fix_vote_group.py           (debe eliminar duplicados antes de mapear group)
fix_duplicados.py          →  deduplicar_votos_diputados.py (ambos limpian duplicados, orden flexible)
deduplicar_votos_diputados.py → deduplicar_counts_diputados.py (primero votos, luego counts)
recalcular_resultados.py   →  recalcular_ve_senado_v2.py  (v2 corrige vacíos que v1 no cubrió)
fix_curul_tipo.py          →  fix_curul_tipo_manual.py    (manual cubre los que el automático no encontró)
```

## Scripts Movidos / Archivados

| Script | Destino | Razón |
|--------|---------|-------|
| `migrate_legacy_pk.sql` | `db/archived/` | Referencia tablas `sen_*` de `senado.db` (BD legacy unificada en `congreso.db`) |
| `queries_demo.py` | `scripts/` | Utilidad de consulta/demo, no es una migración |
| `fix_org_basura.py` | `db/archived/` | Reemplazado por `limpiar_fantasmas_y_total.py` (que es superconjunto de ambos) |
| `limpiar_org_basura_v2.py` | `db/archived/` | Reemplazado por `limpiar_fantasmas_y_total.py` (que es superconjunto de ambos) |

## Notas

- **Ejecutar con**: `.venv/bin/python3 db/migrations/<script>.py`
- **Todos son idempotentes**: seguros de re-ejecutar sin efectos secundarios
- **Scripts que crean backup**: `fix_duplicados.py`, `deduplicar_votos_diputados.py`, `purge_lxv_diputados.py`
- **Scripts que requieren red**: `backfill_fichas_diputados.py`, `backfill_wikidata.py`, `fix_curul_tipo.py`, `fix_curul_tipo_manual.py` (scrapean SITL o Wikidata)
- **Scripts con `--dry-run`**: La mayoría soporta `--dry-run` para previsualizar cambios
- **Scripts con `--stats`**: Varios soportan `--stats` para ver estado sin modificar
- **Coverage residual**: 96 personas sin género (nombres ambiguos), 534 sin curul_tipo (suplentes/sin sitl_id), 44.5% sin fecha_nacimiento (difíciles de obtener para legislaturas antiguas)

## Verificación Rápida

```bash
# Verificar integridad referencial
.venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('db/congreso.db')
conn.execute('PRAGMA foreign_keys = ON')
violations = conn.execute('PRAGMA foreign_key_check').fetchall()
print(f'FK violations: {len(violations)}')
"

# Verificar que no hay votos con group textual
.venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('db/congreso.db')
non_org = conn.execute('SELECT COUNT(*) FROM vote WHERE \"group\" IS NOT NULL AND \"group\" NOT LIKE \"O%\"').fetchone()[0]
print(f'Non-org groups in vote: {non_org}')
"

# Verificar UNIQUE constraints
.venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('db/congreso.db')
idxs = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND name IN ('idx_vote_unique', 'idx_count_unique')\").fetchall()]
print(f'UNIQUE indexes: {idxs}')
"
```
