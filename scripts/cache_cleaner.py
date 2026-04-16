"""cache_cleaner.py — Limpieza de cache HTML por antigüedad.

Módulo Python complementario a scripts/clean_cache.sh.
Permite invocar la limpieza programáticamente desde otros scripts
o desde código Python.

Uso CLI:
    python scripts/cache_cleaner.py --max-age 30
    python scripts/cache_cleaner.py --max-age 7 --dry-run

Uso programático:
    from scripts.cache_cleaner import clean_cache
    clean_cache(max_age_days=30, dry_run=False)
"""

import argparse
import time
from pathlib import Path


def clean_cache(
    cache_dir: str | Path | None = None,
    max_age_days: int = 30,
    dry_run: bool = False,
) -> dict:
    """Elimina archivos del cache más antiguos que max_age_days.

    Args:
        cache_dir: Ruta al directorio cache. Si es None, usa <proyecto>/cache/.
        max_age_days: Antigüedad máxima en días (default 30).
        dry_run: Si es True, no elimina archivos, solo reporta.

    Returns:
        Dict con estadísticas:
            - files_deleted: int — archivos eliminados (o que se eliminarían en dry_run)
            - bytes_freed: int — bytes liberados
            - errors: int — archivos que no se pudieron eliminar
    """
    if cache_dir is None:
        cache_dir = Path(__file__).parent.parent / "cache"

    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return {"files_deleted": 0, "bytes_freed": 0, "errors": 0}

    cutoff = time.time() - (max_age_days * 86400)
    files_deleted = 0
    bytes_freed = 0
    errors = 0

    for entry in cache_dir.rglob("*"):
        if not entry.is_file():
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                file_size = entry.stat().st_size
                if dry_run:
                    files_deleted += 1
                    bytes_freed += file_size
                else:
                    entry.unlink()
                    files_deleted += 1
                    bytes_freed += file_size
        except OSError:
            errors += 1

    return {
        "files_deleted": files_deleted,
        "bytes_freed": bytes_freed,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Limpia cache HTML por antigüedad")
    parser.add_argument(
        "--max-age",
        type=int,
        default=30,
        help="Antigüedad máxima en días (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo mostrar qué se eliminaría, sin borrar",
    )
    args = parser.parse_args()

    stats = clean_cache(max_age_days=args.max_age, dry_run=args.dry_run)

    size_mb = stats["bytes_freed"] / (1024 * 1024)
    action = "se eliminarían" if args.dry_run else "eliminados"
    print(f"Archivos {action}: {stats['files_deleted']}")
    print(f"Espacio: {size_mb:.1f} MB")
    if stats["errors"]:
        print(f"Errores: {stats['errors']}")


if __name__ == "__main__":
    main()
