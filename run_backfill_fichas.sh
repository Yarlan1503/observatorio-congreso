#!/bin/bash
# Ejecuta backfill de fichas SITL por legislatura, en orden de prioridad
set -e
cd "$(dirname "$0")"

echo "=== BACKFILL FICHAS SITL ==="
echo "Inicio: $(date)"

for LEG in LXVI LXV LXIV LXIII LXII LXI LX; do
    echo ""
    echo ">>> Legislatura: $LEG — $(date)"
    .venv/bin/python3 db/migrations/backfill_fichas_diputados.py --legislatura "$LEG" 2>&1 | tee "logs/backfill_${LEG,,}.log" || true
    echo "<<< $LEG terminado — $(date)"
done

echo ""
echo "=== COVERAGE FINAL ==="
.venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('db/congreso.db')
total = conn.execute('SELECT COUNT(*) FROM person').fetchone()[0]
fn = conn.execute('SELECT COUNT(*) FROM person WHERE fecha_nacimiento IS NOT NULL AND fecha_nacimiento != \"\"').fetchone()[0]
ct = conn.execute('SELECT COUNT(*) FROM person WHERE curul_tipo IS NOT NULL AND curul_tipo != \"\"').fetchone()[0]
gen = conn.execute('SELECT COUNT(*) FROM person WHERE genero IS NOT NULL').fetchone()[0]
print(f'fecha_nacimiento: {fn}/{total} ({100*fn/total:.1f}%)')
print(f'curul_tipo:       {ct}/{total} ({100*ct/total:.1f}%)')
print(f'genero:           {gen}/{total} ({100*gen/total:.1f}%)')
conn.close()
"

echo "Fin: $(date)"
