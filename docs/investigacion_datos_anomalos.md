# Investigación de Datos Anómalos

**Fecha**: 2026-04-15
**BD**: `db/congreso.db` (~337MB, 9,385 votaciones, ~3.5M votos, ~4.8K personas)
**Contexto**: Anomalías reportadas por auditoría DB 2026-04-15

---

## Anomalía 1: Supuestos 5 memberships duplicados exactos

### Reporte original

> Los IDs de persona P00132, P00133, P00150, P00165, P00167 tendrían memberships
> duplicados exactos a O12 (Convergencia) con `start_date=2006-09-01`.

### Datos encontrados

#### 1. Verificación de personas

Las 5 personas existen y tienen datos válidos:

| ID | Nombre | Género |
|----|--------|--------|
| P00132 | Corral Aguilar María Mercedes | M |
| P00133 | Espinosa Piña José Luis | M |
| P00150 | Arenas Guzmán Margarita | F |
| P00165 | Buganza Salmerón Gerardo | M |
| P00167 | Carbajal Méndez Liliana | F |

#### 2. Memberships encontrados

Cada persona tiene **3 memberships**, no duplicados:

| Person | Org | Rol | ID | Label | start_date | end_date |
|--------|-----|-----|----|-------|------------|----------|
| P00132 | O09 (Senado) | senador | M_S03696 | Senador, por Lista Nacional, (PAN), [LX] | 2006-09-01 | 2009-08-31 |
| P00132 | O12 (PAN) | **diputado** | M_D00003 | Diputado PAN | 2006-09-01 | 2009-08-31 |
| P00132 | O12 (PAN) | **senador** | M_S03697 | Senador, PAN [LX] | 2006-09-01 | 2009-08-31 |

El patrón se repite idéntico para las 5 personas: membership al Senado (O09), membership a PAN como diputado (M_D*), y membership a PAN como senador (M_S*).

#### 3. Búsqueda de duplicados exactos

```sql
SELECT person_id, org_id, start_date, end_date, rol, COUNT(*) as cnt
FROM membership
GROUP BY person_id, org_id, start_date, end_date, rol
HAVING cnt > 1;
-- Resultado: 0 filas
```

**No existe ni un solo duplicado exacto** en toda la tabla membership (7,500+ registros).

#### 4. Identidad de O12

O12 = **PAN** (Partido Acción Nacional), NO Convergencia. No existe ninguna organización llamada "Convergencia" en la BD.

### Diagnóstico

**Falso positivo de la auditoría.** Dos errores en el reporte:

1. **O12 es PAN, no Convergencia.** La auditoría malinterpretó el ID de organización.
2. **No son duplicados exactos.** Los memberships tienen roles distintos:
   - `M_D*` (rol=diputado) → insertado por el scraper de **Diputados**
   - `M_S*` (rol=senador) → insertado por el scraper de **Senado** (load_directorio.py)

Ambos scrapers crearon memberships a PAN para los mismos senadores porque los directorios XLS del Senado incluyen la afiliación partidista, y el scraper de Diputados también registró la afiliación partidista para las mismas personas.

### ¿Por qué el scraper de Diputados creó memberships para senadores?

Las personas P00132-P00167 son **senadores** de la LX Legislatura. El scraper de Diputados las procesó porque probablemente aparecen en los datos de composición del SITL como legisladores con afiliación PAN. El membership con rol "diputado" a PAN es técnicamente incorrecto (son senadores), pero el dato de afiliación partidista es correcto.

### Recomendación

**No requiere limpieza.** Los memberships con roles distintos son semánticamente diferentes. Sin embargo, hay un issue menor de calidad de datos:

- Los registros `M_D*` con rol="diputado" para personas que son senadoras deberían tener rol="senador" o "miembro" (afiliación genérica).
- Esto es cosmético y no afecta análisis de co-votación ni índices de poder.
- Si se desea corregir, se puede hacer en una migración futura que normalice roles de memberships partidistas.

---

## Anomalía 2: VE02 — vote_event sin votos ni source_id

### Reporte original

> VE02 tendría 0 votos y NULL en source_id.

### Datos encontrados

#### 1. Detalle de VE02

| Campo | Valor |
|-------|-------|
| id | VE02 |
| motion_id | Y02 |
| start_date | 2026-03-17 |
| organization_id | O09 (Senado) |
| result | pendiente |
| voter_count | NULL |
| legislatura | LXVI |
| requirement | mayoria_calificada |
| source_id | NULL |
| sitl_id | NULL |
| identifiers_json | NULL |

#### 2. Motion asociada (Y02)

| Campo | Valor |
|-------|-------|
| id | Y02 |
| texto | Iniciativa mixta: reformas constitucionales + leyes secundarias. Ejes: menos privilegios (topes salariales, recortes a instituciones electorales) + más participación (revocación de mandato adelantada). Retira puntos explosivos: no se tocan plurinominales, financiamiento ni senadurías de RP. |
| clasificacion | reforma_constitucional |
| requirement | mayoria_calificada |
| result | pendiente |
| date | 2026-03-17 |

#### 3. Votos y counts

- Votos: **0**
- Counts: **0**

#### 4. Origen

VE02 fue insertado manualmente por `db/migrations/migrate_caso_cero.py` — la migración del "caso cero" (Reforma Político-Electoral de Sheinbaum, marzo 2026). Este script insertó:
- 2 motions (Y01, Y02)
- 2 vote_events (VE01, VE02)
- ~27 personas
- ~24 votos (solo para VE01)
- 12 counts (solo para VE01)

#### 5. Contexto: VE01 vs VE02

| | VE01 | VE02 |
|--|------|------|
| Cámara | O08 (Diputados) | O09 (Senado) |
| Fecha | 2026-03-11 | 2026-03-17 |
| Resultado | rechazada | pendiente |
| Votos | 24 | 0 |
| Counts | 12 | 0 |
| source_id | NULL | NULL |
| Contexto | Reforma electoral votada y rechazada en Diputados | Reforma electoral pendiente en Senado |

#### 6. source_id NULL

VE01 y VE02 son los **únicos** vote_events sin source_id en toda la BD (de 9,385). Esto es correcto porque no provienen de scraping (SITL o portal Senado) sino de inserción manual.

### Diagnóstico

**Dato legítimo.** VE02 no es un registro fantasma ni un bug:

1. Representa una votación pendiente en el Senado que aún no ha ocurrido.
2. Fue insertado por `migrate_caso_cero.py` como parte del caso de estudio de la reforma electoral.
3. Tiene 0 votos porque la votación no se ha realizado.
4. `source_id=NULL` es correcto porque es un registro manual, no de scraping.
5. La motion Y02 tiene contenido descriptivo válido.

### Recomendación

**Dejar como está.** VE02 es un placeholder legítimo para una votación pendiente. Opciones futuras:

1. Si la votación eventualmente ocurre en el Senado, el scraper la capturará como VE_S* y se puede eliminar VE02 o marcarla como reemplazada.
2. Si la reforma se archiva sin votación en Senado, VE02 permanece como registro del intento.
3. Considerar agregar un campo `manual=True` o `source='manual'` para distinguir registros insertados manualmente de los generados por scraping.

---

## Resumen

| Anomalía | Diagnóstico | Acción requerida |
|----------|-------------|------------------|
| 5 memberships duplicados | **Falso positivo** — roles distintos (diputado vs senador), 0 duplicados exactos en toda la BD | Ninguna |
| VE02 sin votos ni source_id | **Dato legítimo** — votación pendiente insertada manualmente por migrate_caso_cero.py | Ninguna |

### Script de limpieza

No se creó script de limpieza porque:
- **Anomalía 1**: 0 duplicados exactos. No hay nada que limpiar.
- **Anomalía 2**: Dato legítimo. No debe eliminarse.

El script existente `db/migrations/fix_duplicados.py` limpia votos duplicados en la tabla `vote`, no memberships. Sigue siendo útil para su propósito original.
