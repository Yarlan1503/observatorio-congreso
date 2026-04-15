#!/usr/bin/env bash
# mantener.sh — Mantenimiento unificado del Observatorio Congreso
# Uso: scripts/mantener.sh [--dry-run] [--skip-backup] [--skip-cache]
#                              [--skip-logs] [--skip-pycache]
#                              [--max-age-cache N] [--max-age-logs N]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Defaults
DRY_RUN=false
SKIP_BACKUP=false
SKIP_CACHE=false
SKIP_LOGS=false
SKIP_PYCACHE=false
MAX_AGE_CACHE=30
MAX_AGE_LOGS=30

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        --skip-cache)
            SKIP_CACHE=true
            shift
            ;;
        --skip-logs)
            SKIP_LOGS=true
            shift
            ;;
        --skip-pycache)
            SKIP_PYCACHE=true
            shift
            ;;
        --max-age-cache)
            MAX_AGE_CACHE="$2"
            shift 2
            ;;
        --max-age-logs)
            MAX_AGE_LOGS="$2"
            shift 2
            ;;
        *)
            echo "Opción desconocida: $1"
            echo "Uso: scripts/mantener.sh [--dry-run] [--skip-backup] [--skip-cache]"
            echo "                          [--skip-logs] [--skip-pycache]"
            echo "                          [--max-age-cache N] [--max-age-logs N]"
            exit 1
            ;;
    esac
done

echo "========================================"
echo " mantener.sh — Mantenimiento unificado"
echo "========================================"
if [[ "$DRY_RUN" == true ]]; then
    echo "🔸 MODO DRY-RUN (simulación, no se borra nada real)"
fi
echo ""

# ──────────────────────────────────────────
# 1. Backup BD
# ──────────────────────────────────────────
echo "━━━ 1. Backup BD ━━━"
if [[ "$SKIP_BACKUP" == true ]]; then
    echo "⏭  Saltado (--skip-backup)"
elif [[ "$DRY_RUN" == true ]]; then
    echo "🔸 DRY-RUN: se ejecutaría bash $SCRIPT_DIR/backup_db.sh"
else
    echo " Ejecutando backup_db.sh..."
    bash "$SCRIPT_DIR/backup_db.sh"
fi
echo ""

# ──────────────────────────────────────────
# 2. Cache cleanup
# ──────────────────────────────────────────
echo "━━━ 2. Cache cleanup ━━━"
if [[ "$SKIP_CACHE" == true ]]; then
    echo "⏭  Saltado (--skip-cache)"
else
    if [[ "$DRY_RUN" == true ]]; then
        echo "🔸 DRY-RUN: se ejecutaría bash $SCRIPT_DIR/clean_cache.sh --max-age $MAX_AGE_CACHE --dry-run"
        bash "$SCRIPT_DIR/clean_cache.sh" --max-age "$MAX_AGE_CACHE" --dry-run
    else
        echo " Ejecutando clean_cache.sh --max-age $MAX_AGE_CACHE..."
        bash "$SCRIPT_DIR/clean_cache.sh" --max-age "$MAX_AGE_CACHE"
    fi
fi
echo ""

# ──────────────────────────────────────────
# 3. Log cleanup
# ──────────────────────────────────────────
echo "━━━ 3. Log cleanup (>$MAX_AGE_LOGS días) ━━━"
if [[ "$SKIP_LOGS" == true ]]; then
    echo "⏭  Saltado (--skip-logs)"
else
    LOG_DIR="$PROJECT_DIR/logs/"
    if [[ "$DRY_RUN" == true ]]; then
        echo "🔸 DRY-RUN: logs que se eliminarían:"
        find "$LOG_DIR" -type f -name "*.log" -mtime +"$MAX_AGE_LOGS" -print 2>/dev/null || true
    else
        DELETED=$(find "$LOG_DIR" -type f -name "*.log" -mtime +"$MAX_AGE_LOGS" -print -delete 2>/dev/null || true)
        if [[ -z "$DELETED" ]]; then
            echo "   No hay logs >$MAX_AGE_LOGS días para eliminar."
        else
            echo "$DELETED" | while read -r f; do echo "   Eliminado: $f"; done
        fi
    fi
fi
echo ""

# ──────────────────────────────────────────
# 4. __pycache__ cleanup
# ──────────────────────────────────────────
echo "━━━ 4. __pycache__ cleanup ━━━"
if [[ "$SKIP_PYCACHE" == true ]]; then
    echo "⏭  Saltado (--skip-pycache)"
else
    if [[ "$DRY_RUN" == true ]]; then
        echo "🔸 DRY-RUN: directorios __pycache__ que se eliminarían:"
        find "$PROJECT_DIR" -path '*/.venv' -prune -o -name '__pycache__' -type d -print 2>/dev/null || true
    else
        find "$PROJECT_DIR" -path '*/.venv' -prune -o -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
        echo "   __pycache__ eliminados (excluyendo .venv)."
    fi
fi
echo ""

# ──────────────────────────────────────────
# 5. Check .bak
# ──────────────────────────────────────────
echo "━━━ 5. Check .bak en db/ ━━━"
BAK_FILES=$(ls db/*.bak* 2>/dev/null || true)
if [[ -n "$BAK_FILES" ]]; then
    echo "⚠  WARNING: Se encontraron archivos .bak en db/:"
    echo "$BAK_FILES" | while read -r f; do echo "   $f"; done
    echo "   Considere eliminarlos para ahorrar espacio."
else
    echo "   No se encontraron archivos .bak en db/."
fi
echo ""

# ──────────────────────────────────────────
# 6. Resumen
# ──────────────────────────────────────────
echo "━━━ 6. Resumen de tamaño ━━━"
for dir in cache/ logs/ db/ db/backups/ analysis/ .git/; do
    TARGET="$PROJECT_DIR/$dir"
    if [[ -d "$TARGET" ]]; then
        SIZE=$(du -sh "$TARGET" 2>/dev/null | cut -f1)
        echo "   $dir → $SIZE"
    else
        echo "   $dir → (no existe)"
    fi
done
echo ""
echo "========================================"
echo " Mantenimiento completado."
echo "========================================"
