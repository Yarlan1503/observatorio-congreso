#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CACHE_DIR="$PROJECT_DIR/cache"
MAX_AGE=30
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --max-age) MAX_AGE="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        *) echo "Uso: $0 [--max-age N] [--dry-run]"; exit 1 ;;
    esac
done

# Verify cache dir exists
if [[ ! -d "$CACHE_DIR" ]]; then
    echo "ERROR: Directorio de cache no encontrado: $CACHE_DIR"
    exit 1
fi

# Count and size before
echo "=== Limpieza de Cache ==="
echo "Directorio: $CACHE_DIR"
echo "Antigüedad máxima: ${MAX_AGE} días"
echo ""

TOTAL_BEFORE=$(find "$CACHE_DIR" -type f | wc -l)
SIZE_BEFORE=$(du -sh "$CACHE_DIR" | cut -f1)
echo "Archivos antes: $TOTAL_BEFORE"
echo "Tamaño antes:   $SIZE_BEFORE"
echo ""

# Find and remove old files
if [[ "$DRY_RUN" == true ]]; then
    echo "--- DRY RUN (no se eliminarán archivos) ---"
    OLD_FILES=$(find "$CACHE_DIR" -type f -mtime +${MAX_AGE})
    OLD_COUNT=$(echo "$OLD_FILES" | grep -c . || true)
    OLD_SIZE=$(echo "$OLD_FILES" | xargs -r du -ch | tail -1 | cut -f1 || echo "0")
    echo "Archivos a eliminar: $OLD_COUNT"
    echo "Espacio liberado:    $OLD_SIZE"
else
    # Remove old files
    DELETED=0
    while IFS= read -r file; do
        rm -f "$file"
        ((DELETED++))
    done < <(find "$CACHE_DIR" -type f -mtime +${MAX_AGE})

    # Stats after
    TOTAL_AFTER=$(find "$CACHE_DIR" -type f | wc -l)
    SIZE_AFTER=$(du -sh "$CACHE_DIR" | cut -f1)

    echo "Archivos eliminados: $DELETED"
    echo "Archivos después:    $TOTAL_AFTER"
    echo "Tamaño después:      $SIZE_AFTER"
fi

echo ""
echo "=== Fin limpieza ==="
