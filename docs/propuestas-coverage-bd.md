# Propuestas para Cobertura de Campos >90 %
## Observatorio del Congreso — BD Popolo-Graph
### Fecha: 2026-04-09

---

## 1. Diagnóstico

### Gaps actuales de cobertura

| Tabla | Campo | Cobertura actual | Tipo | Techo estimado | Nota |
|-------|-------|-----------------|------|----------------|------|
| membership | start_date | 42% | Gap real | 99% | Fechas constitucionales disponibles |
| membership | end_date | 30% | Gap real | 95% | Ídem |
| membership | on_behalf_of | 0.1% | Gap real | 35-40% | Sin fuente estructurada de coaliciones |
| person | fecha_nacimiento | 0.1% | Gap real | 65% | Legisladores históricos sin datos |
| person | curul_tipo | 20% | Gap real | 95% | Regex sobre label + fichas SITL |
| person | genero | 96% | Gap real | 99.8% | 192 pendientes; ~70 ambiguos requieren revisión manual |
| organization | fundacion | 5.6% | Gap real | 100% | Datos públicos INE |
| organization | disolucion | 0% | Gap real | 100% | Ídem |
| vote_event | sitl_id | 46% | By-design | — | Solo Diputados. `identifiers_json` es equivalente Senado. `source_id` unifica (99.98%) |
| vote_event | identifiers_json | 54% | By-design | — | Solo Senado. Mutuamente excluyente con sitl_id |
| count | group_id | 85% | By-design | — | NULL = totales agregados intencionales. 97.8% VEs tienen 4 counts sin group_id |

### Campos by-design: no son gaps reales

- **`vote_event.sitl_id` + `vote_event.identifiers_json`** son campos específicos por cámara. El campo unificado es `source_id`, con cobertura 99.98%. Los NULL son diputados que no tienen identifier de Senado y viceversa. No requieren acción.
- **`count.group_id`** en NULL son los totales agregados (a favor, en contra, abstenciones, ausentes). Cada vote event tiene exactamente 4 counts sin group_id correspondientes a sus totales. Es intencional.

### Resumen

- **11 campos** con cobertura < 90%
- 3 son **by-design** → no requieren acción
- **8 gaps reales** que requieren intervención
  - 5 con techo ≥ 95% → cosechables con recursos internos
  - 2 con techo bajo: `on_behalf_of` (~35-40%) y `fecha_nacimiento` (~65%)
  - 1 casi resuelto: `genero` (96% → 99.8%)

---

## 2. Fuentes de Datos Disponibles

| # | Fuente | Datos que aporta | Confianza | Coverage potencial | Esfuerzo |
|---|--------|-----------------|-----------|-------------------|----------|
| 1 | Heurística interna (LEGISLATURAS config + regex label) | start_date, end_date, curul_tipo | Alta | Alta | Bajo (2-3 scripts) |
| 2 | FichaDiputado parser (ya existe, no invocado) | fecha_nacimiento, curul_tipo, entidad, email | Alta | Media (~LXIV+) | Bajo (activar pipeline) |
| 3 | Wikidata SPARQL | fecha_nacimiento, género, partido | Alta | Media (522 LXV) | Medio (API + matching) |
| 4 | SITL fichas curriculares | fecha_nacimiento, curul_tipo, suplente | Alta | Media-alta | Medio (nuevo scraper) |
| 5 | INE (registro de partidos) | fundacion, disolucion | Alta | 100% | Bajo (~1h manual) |
| 6 | Wikipedia ES (anexos legislativos) | tipo elección, coaliciones | Media | Media | Alto (scraping + parseo) |
| 7 | SocialTIC API (candidaturas 2021) | on_behalf_of (coaliciones) | Media-alta | Baja (solo 2021) | Medio |

**Cero dependencia externa.** Las fuentes 1-2 son internas: código ya existe o datos ya están en config. La fuente 5 (INE) es un lookup estático de ~26 partidos — se resuelve manualmente en ~1 hora.

**Desarrollo nuevo, APIs públicas.** Las fuentes 3-4 (Wikidata, SITL) requieren desarrollo pero usan APIs documentadas y abiertas. Son el camino para `fecha_nacimiento` y los campos restantes de `curul_tipo`.

**ROI bajo.** Las fuentes 6-7 son las de mayor esfuerzo y menor retorno. Wikipedia requiere scraping frágil sobre anexos inconsistentes. SocialTIC cubre solo 2021. Priorizar solo si se necesitan coaliciones históricas.

---

## 3. Propuesta A: "Cosecha Interna"

### Estrategia general

Código interno + dato estático manual. Cero dependencia de fuentes externas. Aprovecha datos que ya existen en el código (`LEGISLATURAS` en `config.py`) y herramientas construidas (`FichaDiputado` parser).

### Resultado esperado

- **9/11 campos ≥ 90%** (incluyendo 3 *by-design* documentados en §1)
- **5 gaps resueltos**: `start_date`, `end_date`, `genero`, `fundacion`, `disolucion`
- **3 gaps parcialmente mejorados**: `curul_tipo` (20% → ~50%), `on_behalf_of` (0.1% → ~5%), `fecha_nacimiento` (0.1% → ~15%)

### Cobertura pre/post por campo

| Campo | Pre | Post | Método |
|-------|-----|------|--------|
| `membership.start_date` | 42% | 99% | Heurística `LEGISLATURAS` |
| `membership.end_date` | 30% | 95% | Heurística `LEGISLATURAS` |
| `membership.on_behalf_of` | 0.1% | ~5% | Regex sobre `label` (coaliciones explícitas) |
| `person.genero` | 96% | 99.8% | Extender diccionario + revisión manual |
| `person.curul_tipo` | 20% | ~50% | Regex sobre `membership.label` |
| `person.fecha_nacimiento` | 0.1% | ~15% | `FichaDiputado` parser (solo LXIV+) |
| `organization.fundacion` | 5.6% | 100% | Manual INE |
| `organization.disolucion` | 0% | 100% | Manual INE |

### Tareas (orden de ejecución)

#### P0 — Organizaciones manual (1h)

**Script**: `db/migrations/backfill_org_fechas.py`

INSERT `fundacion`/`disolucion` para ~26 partidos nacionales desde lookup estático hardcodeado. Fuente: INE — fechas oficiales de registro/pérdida de registro (datos públicos verificados).

Implementación: diccionario Python `{org_name: (fundacion, disolucion|None)}` + `UPDATE organizations WHERE name = key`.

#### P1 — Backfill fechas memberships Diputados (4h)

**Script**: `db/migrations/backfill_membership_fechas.py`

Para cada membership sin `start_date`/`end_date`, calcula fechas desde `LEGISLATURAS` (config.py) y/o regex sobre `label`. Si `membership.legislative_session` tiene legislatura conocida → `start_date = fecha_inicio`, `end_date = fecha_fin`. Si `label` contiene "Suplente" o patrón de fecha → extraer con regex.

**Requisito previo**: migrar `LEGISLATURAS` de `diputados/scraper/config.py` a `db/constants.py` como fuente canónica compartida.

#### P2 — Backfill `curul_tipo` Senadores (2h)

**Script**: `backfill_curul_tipo.py` (o extender P1)

Regex sobre `membership.label` para detectar tipo de elección. Mapeo:

| Patrón en label | → `curul_tipo` |
|-----------------|-----------------|
| "Primera Fórmula" | `mayoria_relativa` |
| "Primera Minoría" | `primera_minoria` |
| "Segunda Fórmula" | `representacion_proporcional` |

#### P3 — Extender backfill género (2h)

**Script**: `db/migrations/backfill_genero.py` (ya existe, extender)

Ampliar diccionario de nombres (~500 → ~800), reducir threshold a 1, revisión manual de ~70 genuinamente ambiguos (Jesús, María, Ángel, Guadalupe, Rosario, Pilar, José). Resultado: 192 restantes → ~10-15 genuinamente imposibles, marcados `"unknown"`.

#### P4 — Documentar no-gaps (2h)

Documentación en `schema.md` o data-dictionary — no es código:

- **`vote_event.sitl_id`**: Solo Diputados. Ver `identifiers_json` para Senado. Unificado en `source_id` (99.98%).
- **`vote_event.identifiers_json`**: Solo Senado. Mutuamente excluyente con `sitl_id`.
- **`count.group_id`**: `NULL` = totales agregados (favor, contra, abstenciones, ausentes). 97.8% de VEs tienen exactamente 4 registros.

### Esfuerzo

| Tarea | Horas | Tipo |
|-------|-------|------|
| P0 Organizaciones | 1h | Script simple + datos manuales |
| P1 Fechas memberships | 4h | Script + migración `LEGISLATURAS` |
| P2 `curul_tipo` senadores | 2h | Script regex |
| P3 Género extendido | 2h | Extensión script existente |
| P4 Documentación | 2h | Markdown |
| Testing + validación | 3-4h | Verificación manual |
| **Total** | **~14-15h** | |

Estimación con buffer para edge cases: 16-20h.

### Riesgos y mitigación

| Riesgo | Prob. | Impacto | Mitigación |
|--------|-------|---------|------------|
| `LEGISLATURAS` incompleta para legislaturas antiguas | Baja | Medio | Verificar contra datos oficiales, hardcodear faltantes |
| Regex de `label` no cubre todos los formatos | Media | Bajo | Catalogar formatos primero, fallback a `NULL` |
| Nombres ambiguos de género (>70) | Alta | Bajo | Marcar `"unknown"` — no afecta análisis principales |
| Edge cases en fechas (renuncias, licencias) | Media | Bajo | Documentar que son fechas nominales, no efectivas |

---

## 4. Propuesta B: "Fichas + Wikidata"

Esta propuesta es **acumulada**: incluye todo de la Propuesta A más desarrollo nuevo. El esfuerzo indicado es incremental sobre A.

### Estrategia

Se activan dos fuentes externas de alta confianza:

1. **Pipeline SITL Fichas** — El parser `FichaDiputado` ya existe en `diputados/scraper/parsers/diputado.py` y extrae `fecha_nacimiento`, `principio_eleccion` (→`curul_tipo`), `entidad`, `email`, `suplente`. El pipeline de votaciones nunca lo invoca.
2. **Wikidata SPARQL** — 522 entidades de la LXV Legislatura con P569 (fecha nacimiento ~55%) y P21 (género ~65%). Endpoint público sin rate limit agresivo.

### Resultado esperado (acumulado con A)

Todos los campos de A alcanzados. Además:

| Campo | Post-A | Post-B | Ganancia | Método |
|-------|--------|--------|----------|--------|
| `person.fecha_nacimiento` | ~15% | ~55% | +40 pp | FichaDiputado + Wikidata |
| `person.curul_tipo` | ~50% | ~85% | +35 pp | FichaDiputado `principio_eleccion` |

### Tareas incrementales

#### P5 — Activar pipeline FichaDiputado (6–8h)

- **Base**: `diputados/scraper/parsers/diputado.py` (ya existe).
- **Construir**:
  1. Integración del parser al pipeline de scraping (actualmente solo se parsean votaciones).
  2. Script `db/migrations/backfill_fichas_diputados.py`: para cada `person` en BD, resuelve su URL de ficha SITL vía `identifier` o `membership`, scrapea con `SITLClient` (reusar cache), parsea con `FichaDiputado`, ejecuta `UPDATE person SET fecha_nacimiento, curul_tipo`.
  3. Mapeo `principio_eleccion → curul_tipo`: `"Mayoría Relativa" → "mayoria_relativa"`, `"Representación Proporcional" → "plurinominal"`.
- **Cobertura**: LXIV–LXVI (legislaturas con SITL disponible). LX–LXIII requieren SITL legacy que puede no tener fichas.
- **Riesgo**: rate limiting de SITL → mitigar con cache existente + delays de 2s + checkpoint.

#### P6 — Wikidata SPARQL matching (6–8h)

- **Script**: `db/migrations/backfill_wikidata.py`.
- **Flujo**: SPARQL query a `https://query.wikidata.org/sparql` → fuzzy matching contra BD por nombre (normalización de tildes, mayúsculas, orden) → `UPDATE person SET fecha_nacimiento WHERE match confirmado AND campo vacío`.

```sql
SELECT ?item ?itemLabel ?fechaNacimiento ?generoLabel
WHERE {
  ?item wdt:P39 wd:Q18887908 .
  ?item wdt:P569 ?fechaNacimiento .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es" }
}
```

- **Cobertura**: ~522 entidades LXV. Legislaturas anteriores (LX–LXIV) tendrán menor cobertura en Wikidata.
- **Riesgo**: falsos positivos por nombre → mitigar con threshold de similitud ≥ 0.85 + verificación cruzada partido/legislatura.

#### P7 — Integración y validación (4–6h)

- Verificar que datos de FichaDiputado y Wikidata no contradigan datos existentes.
- **Jerarquía de conflicto**: SITL (fuente oficial) > Wikidata (curado) > existente.
- Generar reporte de coverage post-B.

### Esfuerzo

| Tarea | Horas | Tipo |
|-------|-------|------|
| P5 FichaDiputado pipeline | 6–8h | Integración parser existente + script nuevo |
| P6 Wikidata SPARQL | 6–8h | Script nuevo + fuzzy matching |
| P7 Integración + validación | 4–6h | Verificación + conflictos |
| **Incremental** | **~16–22h** | |
| **Acumulado (A + B)** | **~30–37h** | |

### Riesgos

| Riesgo | Prob. | Impacto | Mitigación |
|--------|-------|---------|------------|
| SITL rate limiting al scrapear fichas | Media | Medio | Cache existente + delays 2s + checkpoint |
| Fuzzy matching Wikidata → falsos positivos | Media | Alto | Threshold ≥ 0.85 + verificación cruzada partido/legislatura |
| Parser FichaDiputado desactualizado | Baja | Medio | Probar con 10 fichas antes de corrida completa |
| Datos contradictorios entre fuentes | Media | Bajo | Jerarquía clara: SITL > Wikidata > existente |

---

## 5. Propuesta C: "Full Coverage"

**Acumulada**: incluye todo de A + B. El esfuerzo indicado es incremental sobre B.

### Estrategia

Maximizar cobertura atacando los campos más difíciles —`on_behalf_of` y `fecha_nacimiento` históricos— con fuentes de menor ROI:

1. **Wikipedia ES**: anexos legislativos (tipo de elección, coaliciones, fechas de nacimiento)
2. **SocialTIC API**: candidaturas 2021 para `on_behalf_of`
3. **Revisión manual**: ~70 nombres ambiguos de género y casos edge en coaliciones

### Cobertura adicional (sobre Propuesta B)

| Campo | Post-B | Post-C | Ganancia | Método |
|-------|--------|--------|----------|--------|
| `membership.on_behalf_of` | ~5% | ~35% | +30 pp | Wikipedia + SocialTIC + manual |
| `person.fecha_nacimiento` | ~55% | ~65% | +10 pp | Wikipedia biografías |

### Tareas incrementales

#### P8 — Wikipedia ES scraping (12–16h)

**Script**: `db/migrations/backfill_wikipedia.py`

Scraping de anexos legislativos por legislatura (LX–LXVI) para extraer tipo de elección (MR/PL) → `curul_tipo`, coaliciones de campaña → `on_behalf_of`, y fechas de nacimiento desde biografías vinculadas. Cada anexo tiene formato distinto; requiere parsers individuales por legislatura. Cobertura de `on_behalf_of` limitada a anexos que incluyan columna de coalición.

#### P9 — SocialTIC API (4–6h)

**Script**: `db/migrations/backfill_socialtic.py`

Query de candidaturas 2021, matching por nombre contra la BD, UPDATE de `on_behalf_of`. Solo cubre LXV (2021–2024). **Limitante conocida**: la coalición electoral ≠ partido legislativo — un diputado electo por "Juntos Hacemos Historia" puede sentarse como MORENA. Documentar esta distinción.

#### P10 — Revisión manual género (2–3h)

Cruce de ~70 nombres ambiguos con pronombres en biografías Wikipedia, fotos SITL y noticias. Asignar M/F donde sea evidente; marcar `unknown` los casos genuinamente ambiguos.

#### P11 — Revisión manual on_behalf_of (4–6h)

Para diputados sin coalición determinada automáticamente: consulta de actas INE y noticias de época electoral.

### Esfuerzo

| Concepto | Horas | Tipo |
|----------|-------|------|
| P8 Wikipedia scraping | 12–16h | Script nuevo multi-formato |
| P9 SocialTIC API | 4–6h | Script + matching |
| P10 Manual género | 2–3h | Revisión humana |
| P11 Manual on_behalf_of | 4–6h | Revisión humana |
| Testing + validación | 4–6h | Verificación |
| **Incremental** | **26–37h** | |
| **Acumulado (A+B+C)** | **56–74h** | |

### Riesgos

| Riesgo | Prob. | Impacto | Mitigación |
|--------|-------|---------|------------|
| Formatos Wikipedia inconsistentes por legislatura | Alta | Alto | Un parser por legislatura; no buscar genérico |
| Coalición electoral ≠ partido legislativo | Alta | Medio | Documentar distinción; `on_behalf_of` = coalición electoral, no bancada |
| ROI bajo por legislatura | Alta | Medio | Ejecutar solo legislaturas prioritarias |
| Datos SocialTIC incompletos o erróneos | Media | Bajo | Verificar contra fuentes oficiales |

---

## 6. Comparativa

### Resumen de propuestas

| Métrica | A: Cosecha Interna | B: Fichas + Wikidata | C: Full Coverage |
|---------|--------------------|-----------------------|-------------------|
| Esfuerzo acumulado | 16–20h (2–3 días) | 30–37h (5–7 días) | 56–74h (10–14 días) |
| Campos ≥ 90% (de 11) | 9 | 10 | 10 |
| Gaps reales resueltos (de 8) | 5 | 6 | 7 |
| Riesgo | Bajo | Medio | Alto |
| Dependencia externa | Ninguna | Wikidata + SITL | + Wikipedia + SocialTIC |

### Cobertura por campo y propuesta

| Campo | Actual | Post-A | Post-B | Post-C | Techo |
|-------|--------|--------|--------|--------|-------|
| `membership.start_date` | 42% | 99% | 99% | 99% | 99% |
| `membership.end_date` | 30% | 95% | 95% | 95% | 95% |
| `membership.on_behalf_of` | 0.1% | ~5% | ~5% | ~35% | 35–40% |
| `person.fecha_nacimiento` | 0.1% | ~15% | ~55% | ~65% | 65% |
| `person.curul_tipo` | 20% | ~50% | ~85% | ~85% | 95% |
| `person.genero` | 96% | 99.8% | 99.8% | 99.8% | 99.8% |
| `organization.fundacion` | 5.6% | 100% | 100% | 100% | 100% |
| `organization.disolucion` | 0% | 100% | 100% | 100% | 100% |
| `vote_event.sitl_id` | 46% | 46%\* | 46%\* | 46%\* | — (by-design) |
| `vote_event.identifiers_json` | 54% | 54%\* | 54%\* | 54%\* | — (by-design) |
| `count.group_id` | 85% | 85%\* | 85%\* | 85%\* | — (by-design) |

\* Documentado como by-design. No requiere acción.

---

## 7. Recomendación

### Ranking: A >> B > C

**1.ª — Propuesta A.** ROI máximo. En 2–3 días resuelve 5 de 8 gaps sin tocar fuentes externas. Cero riesgo.

**2.ª — Propuesta B** (condicional). Solo si se necesita `fecha_nacimiento` o `curul_tipo` para análisis concretos. La mejora es significativa (+40 pp en `fecha_nacimiento`), pero introduce dependencia externa y lógica de fuzzy matching.

**3.ª — Propuesta C** (no recomendada ahora). El esfuerzo se duplica para ganar ~30 pp en `on_behalf_of`, un campo sin fuente estructurada. Solo se justifica si existe un análisis específico de coaliciones electorales históricas.

### Orden de ejecución sugerido

1. Ejecutar Propuesta A completa (P0 → P4).
2. **Checkpoint 1** — Verificar cobertura post-A. ¿Los gaps restantes justifican B?
3. Si sí → ejecutar P5 (FichaDiputado, el más directo).
4. **Checkpoint 2** — Cobertura post-P5. ¿Wikidata justifica P6?
5. Si sí → ejecutar P6 (Wikidata) + P7 (integración).
6. **Checkpoint 3** — Evaluar si C se justifica. Requiere caso de uso específico.

### Checkpoints de decisión

| Checkpoint | Pregunta clave | Criterio de avance |
|-----------|----------------|-------------------|
| Post-A | ¿Se necesita `fecha_nacimiento` o `curul_tipo` para análisis? | Si no → detener. 9/11 campos ≥ 90%. |
| Post-P5 | ¿Cobertura SITL suficiente? ¿Faltan legislaturas históricas relevantes? | Si LXIV+ cubre las legislaturas de interés → detener. |
| Post-B | ¿Existe análisis que requiera `on_behalf_of`? | Si no → detener. C no se justifica. |

---

## 8. Campos con techo imposible

### `membership.on_behalf_of` — Techo: 35–40%

**Por qué no llega a 90%:** No existe fuente estructurada de coaliciones electorales mexicanas. El INE publica resultados por partido, pero la relación «candidato electo por coalición X» no está en formato *machine-readable*. Los anexos de Wikipedia incluyen esta información de forma irregular (algunas legislaturas sí, otras no). SocialTIC cubre solo 2021. Además, la distinción entre coalición electoral y bancada legislativa hace el dato ambiguo: un diputado electo por «Va por México» (PAN+PRI+PRD) puede legislar como PAN puro.

**Alternativa:** Usar `organization` (partido de bancada), que ya tiene ~100% de cobertura. Para análisis de coaliciones electorales, construir tabla *ad-hoc* con datos INE por legislatura.

### `person.fecha_nacimiento` — Techo: 65%

**Por qué no llega a 90%:** Los legisladores de legislaturas históricas (LX–LXIII, 2006–2015) no tienen fichas SITL con datos biográficos. Wikidata tiene cobertura decente para la LXV (~55%) pero muy baja para legislaturas anteriores. Muchos legisladores históricos no son figuras públicas suficientemente notables para tener entrada en Wikipedia o Wikidata.

**Alternativa:** Para análisis demográficos (edad promedio por partido, distribución etaria), la muestra de ~65% es estadísticamente representativa si se controla por legislatura. No imputar datos faltantes.

### `person.curul_tipo` — Techo: 95%

**Por qué no llega a 100%:** Algunas membresías históricas tienen *labels* no estándar que el regex no puede parsear. Legisladores suplentes que nunca asumieron el cargo pueden no tener tipo documentado. El 5% restante requeriría revisión manual caso por caso con ROI bajo.

**Alternativa:** Para análisis de composición por tipo de elección, el 95% es suficiente. Filtrar los `NULL` del análisis.
