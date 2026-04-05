# db/id_generator.py — Generación centralizada de IDs para el Observatorio del Congreso

"""
Generador de IDs con prefijo por cámara, secuencial y sin colisiones.

Esquema de IDs:
    vote_event: VE_D* (Diputados), VE_S* (Senado)
    vote:       V_D*  (Diputados), V_S*  (Senado)
    motion:     Y_D*  (Diputados), Y_S*  (Senado)
    membership: M_D*  (Diputados), M_S*  (Senado)
    person:     P*    (global, compartido entre cámaras)
    count:      C*    (global, compartido entre cámaras)
    post:       T*    (global, compartido entre cámaras)

Padding: 5 dígitos (ej: P00001, VE_D00042).

La función next_id() consulta el MAX actual en la BD para cada prefijo
y continúa desde ahí, garantizando unicidad even si datos previos existen.
"""

import sqlite3
from typing import Optional


# ---------------------------------------------------------------------------
# Prefijos por tipo de entidad y cámara
# ---------------------------------------------------------------------------

# entity_type → {camara: prefix}
_PREFIXES: dict[str, dict[str, str]] = {
    "vote_event": {"D": "VE_D", "S": "VE_S"},
    "vote": {"D": "V_D", "S": "V_S"},
    "motion": {"D": "Y_D", "S": "Y_S"},
    "membership": {"D": "M_D", "S": "M_S"},
}

# Entidades globales (sin prefijo de cámara)
_GLOBAL_PREFIXES: dict[str, str] = {
    "person": "P",
    "count": "C",
    "post": "T",
}

# Tabla en la BD para cada tipo de entidad
_ENTITY_TABLES: dict[str, str] = {
    "vote_event": "vote_event",
    "vote": "vote",
    "motion": "motion",
    "membership": "membership",
    "person": "person",
    "count": "count",
    "post": "post",
}

# Padding (número de dígitos)
_PAD_WIDTH = 5


def next_id(
    conn: sqlite3.Connection,
    entity_type: str,
    camara: Optional[str] = None,
) -> str:
    """Genera el siguiente ID secuencial para una entidad.

    Para entidades con cámara (vote_event, vote, motion, membership):
        Requiere ``camara`` ("D" o "S") y genera IDs con prefijo por cámara.
        Ej: next_id(conn, "vote_event", "D") → "VE_D00001"

    Para entidades globales (person, count, post):
        Ignora ``camara`` y genera IDs sin prefijo de cámara.
        Ej: next_id(conn, "person") → "P00001"

    La función consulta el MAX existente en la BD para el prefijo dado
    y continúa desde max_num + 1.

    Args:
        conn: Conexión activa a SQLite.
        entity_type: Tipo de entidad ("vote_event", "vote", "motion",
            "membership", "person", "count", "post").
        camara: Cámara ("D" para Diputados, "S" para Senado).
            Requerido para entidades con prefijo por cámara.

    Returns:
        ID generado como string (ej: "VE_D00042", "P00001").

    Raises:
        ValueError: Si entity_type no es reconocido.
        ValueError: Si camara es requerido pero no proporcionado.
    """
    # Determinar prefijo
    if entity_type in _PREFIXES:
        if camara is None:
            raise ValueError(f"entity_type '{entity_type}' requiere camara ('D' o 'S')")
        prefix = _PREFIXES[entity_type].get(camara)
        if prefix is None:
            raise ValueError(
                f"Cámara '{camara}' no reconocida para '{entity_type}'. Usar 'D' o 'S'."
            )
    elif entity_type in _GLOBAL_PREFIXES:
        prefix = _GLOBAL_PREFIXES[entity_type]
    else:
        raise ValueError(
            f"entity_type '{entity_type}' no reconocido. "
            f"Usar: {list(_PREFIXES.keys()) + list(_GLOBAL_PREFIXES.keys())}"
        )

    # Obtener el máximo número actual para este prefijo
    table = _ENTITY_TABLES[entity_type]
    max_num = _get_max_for_prefix(conn, table, prefix)

    # Generar siguiente ID
    next_num = max_num + 1
    return f"{prefix}{next_num:0{_PAD_WIDTH}d}"


def _get_max_for_prefix(conn: sqlite3.Connection, table: str, prefix: str) -> int:
    """Obtiene el número máximo para un prefijo dado en una tabla.

    Busca IDs que empiezan con ``prefix`` y extrae el número.
    Retorna 0 si no hay IDs con ese prefijo.

    Args:
        conn: Conexión activa a SQLite.
        table: Nombre de la tabla.
        prefix: Prefijo de ID (ej: "VE_D", "P").

    Returns:
        Número máximo encontrado (0 si no hay IDs).
    """
    try:
        row = conn.execute(
            f"SELECT id FROM {table} WHERE id LIKE ? "
            f"ORDER BY LENGTH(id) DESC, id DESC LIMIT 1",
            (prefix + "%",),
        ).fetchone()

        if row is None:
            return 0

        id_val = row[0]
        num_str = id_val[len(prefix) :].lstrip("0") or "0"
        return int(num_str)
    except Exception:
        # Tabla vacía o sin IDs con este prefijo
        return 0


def get_next_id_batch(
    conn: sqlite3.Connection,
    entity_type: str,
    camara: Optional[str] = None,
    count: int = 1,
) -> list[str]:
    """Genera un batch de IDs secuenciales sin consultar la BD por cada uno.

    Útil para generar múltiples IDs en una sola transacción
    (ej: insertar 100 votos de una sola votación).

    Args:
        conn: Conexión activa a SQLite.
        entity_type: Tipo de entidad.
        camara: Cámara ("D" o "S").
        count: Cantidad de IDs a generar.

    Returns:
        Lista de IDs generados en orden secuencial.
    """
    if entity_type in _PREFIXES:
        if camara is None:
            raise ValueError(f"entity_type '{entity_type}' requiere camara ('D' o 'S')")
        prefix = _PREFIXES[entity_type][camara]
    elif entity_type in _GLOBAL_PREFIXES:
        prefix = _GLOBAL_PREFIXES[entity_type]
    else:
        raise ValueError(f"entity_type '{entity_type}' no reconocido")

    table = _ENTITY_TABLES[entity_type]
    max_num = _get_max_for_prefix(conn, table, prefix)

    return [f"{prefix}{max_num + i + 1:0{_PAD_WIDTH}d}" for i in range(count)]
