# Archived — Migraciones y scripts fuera de uso

Archivos movidos aquí porque ya ejecutaron su propósito y tienen bugs que
impiden su re-ejecución segura. No deben importarse desde código activo.

## Archivos archivados

| Archivo | Fecha de archivo | Motivo |
|---------|-----------------|--------|
| `fix_curul_tipo.py` | 2026-04-16 | Llama a `normalizar_nombre()` que no está definida (`NameError`). Migración one-time ya ejecutada. |
| `fix_curul_tipo_manual.py` | 2026-04-16 | Llama a `normalizar_nombre()` que no está definida (`NameError`). Migración one-time ya ejecutada. |

## Archivos eliminados (2026-04-16)

| Archivo | Motivo de eliminación |
|---------|----------------------|
| `senado_schema.sql` | Obsoleto, schema unificado en `db/schema.sql`. |
| `migrate_legacy_pk.sql` | Migración one-time ya ejecutada, PKs ya corregidos. |
| `fix_org_basura.py` | Migración one-time ya ejecutada, sin imports activos. |
| `limpiar_org_basura_v2.py` | Migración one-time ya ejecutada, sin imports activos. |

## Nota técnica

`normalizar_nombre` debería ser `normalize_name` de
`scraper_congreso/utils/text_utils.py`. Si alguna vez se necesitaran
re-ejecutar estas migraciones, corregir las referencias antes de usarlas.
