#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB_PATH="$PROJECT_DIR/db/congreso.db"
BACKUP_DIR="$PROJECT_DIR/db/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/congreso_${TIMESTAMP}.db"
MAX_BACKUPS=7

# Helper: ejecutar SQL vía sqlite3 CLI o Python fallback
run_sql() {
    local db="$1"
    local sql="$2"
    if command -v sqlite3 &>/dev/null; then
        sqlite3 "$db" "$sql"
    else
        python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
try:
    result = conn.execute(sys.argv[2]).fetchone()
    if result:
        # Para PRAGMA integrity_check, el resultado es una tupla
        print(result[0] if len(result) == 1 else '|'.join(str(r) for r in result))
finally:
    conn.close()
" "$db" "$sql"
    fi
}

# Helper: ejecutar VACUUM INTO vía sqlite3 CLI o Python fallback
run_vacuum_into() {
    local db="$1"
    local dest="$2"
    if command -v sqlite3 &>/dev/null; then
        sqlite3 "$db" "VACUUM INTO '${dest}';"
    else
        python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
try:
    conn.execute(f'VACUUM INTO \"{sys.argv[2]}\"')
finally:
    conn.close()
" "$db" "$dest"
    fi
}

# 1. Crear directorio si no existe
mkdir -p "$BACKUP_DIR"

# 2. Verificar que la BD existe
if [[ ! -f "$DB_PATH" ]]; then
    echo "ERROR: No se encontró la base de datos en $DB_PATH"
    exit 1
fi

# 3. Ejecutar VACUUM INTO
echo "Creando backup: $(basename "$BACKUP_FILE")"
run_vacuum_into "$DB_PATH" "$BACKUP_FILE"

# 4. Verificar integridad del backup
INTEGRITY=$(run_sql "$BACKUP_FILE" "PRAGMA integrity_check;")
if [[ "$INTEGRITY" != "ok" ]]; then
    echo "ERROR: La verificación de integridad falló: $INTEGRITY"
    exit 1
fi

# 5. Rotar backups (mantener últimos MAX_BACKUPS)
BACKUP_COUNT=$(ls -1t "$BACKUP_DIR"/congreso_*.db 2>/dev/null | wc -l)
if [[ $BACKUP_COUNT -gt $MAX_BACKUPS ]]; then
    echo "Rotando backups ($BACKUP_COUNT encontrados, manteniendo $MAX_BACKUPS)..."
    ls -1t "$BACKUP_DIR"/congreso_*.db | tail -n +$((MAX_BACKUPS + 1)) | xargs rm -f
fi

# 6. Imprimir resumen
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
REMAINING=$(ls -1t "$BACKUP_DIR"/congreso_*.db 2>/dev/null | wc -l)
echo "Backup completado:"
echo "  Archivo: $BACKUP_FILE"
echo "  Tamaño:  $BACKUP_SIZE"
echo "  Integridad: $INTEGRITY"
echo "  Backups restantes: $REMAINING"
