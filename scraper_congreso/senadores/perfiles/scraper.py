"""scraper.py — Scraper de perfiles de senadores para enriquecer congreso.db.

Portal: https://senado.gob.mx/66/senador/{id}
Rango de IDs: 1 a 1754 (modo --range), o IDs extraídos de listado (modo --from-listing)

Enriquece la base de datos con:
- genero (M/F) inferido del título del perfil
- curul_tipo (mayoria_relativa, plurinominal, suplente)
- identifiers_json con el ID del portal
- Fechas de membresía por legislatura (fechas constitucionales)

Uso:
    python -m scraper_congreso.senadores.perfiles --from-listing
    python -m scraper_congreso.senadores.perfiles --from-listing --limit 10 --dry-run
    python -m scraper_congreso.senadores.perfiles --range 1 1754 --delay 2.0
    python -m scraper_congreso.senadores.perfiles --test-id 1
    python -m scraper_congreso.senadores.perfiles --test-id 1575 --dry-run
    python -m scraper_congreso.senadores.perfiles --stats
"""

import argparse
import json
import random
import re
import sqlite3
import time
from pathlib import Path

from scraper_congreso.senadores.config import (
    BASE_URL_LXVI,
    COOKIE_PATH,
    DB_PATH,
    SENADO_ORG_ID,
)
from scraper_congreso.utils.logging_config import setup_logging

from .parsers.perfil_parser import SenPerfil, parse_perfil_html

# --- Constants ---

PERFIL_URL_TEMPLATE = f"{BASE_URL_LXVI}/66/senador/{{id}}"

FECHAS_LEGISLATURA: dict[str, tuple[str, str]] = {
    "LIX": ("2003-08-29", "2006-08-31"),
    "LX": ("2006-09-01", "2009-08-31"),
    "LXI": ("2009-09-01", "2012-08-31"),
    "LXII": ("2012-09-01", "2015-08-31"),
    "LXIII": ("2015-09-01", "2018-08-31"),
    "LXIV": ("2018-09-01", "2021-08-31"),
    "LXV": ("2021-09-01", "2024-08-31"),
    "LXVI": ("2024-09-01", "2027-08-31"),
}

logger = setup_logging("senado_perfiles")


# =============================================================================
# HTTP Client (httpx async → sync wrapper)
# =============================================================================


def _extract_ids_from_listing(html: str) -> set[int]:
    """Extrae IDs de senador de una página de listado del Senado.

    Busca links del tipo:
        href="http://senado.gob.mx/66/senador/1579"
        href="/66/senador/1587"

    Returns:
        Set de IDs únicos encontrados.
    """
    pattern = r'href=["\'](?:https?://[^"\']*senado\.gob\.mx)?/66/senador/(\d+)["\']'
    matches = re.findall(pattern, html)
    return {int(m) for m in matches}


class PerfilClient:
    """Cliente HTTP para perfiles del Senado.

    Composición sobre SenadoLXVIClient — reusa toda la maquinaria anti-WAF
    (curl_cffi + impersonate + backoff + session recreation).

    Comparte cookies con el scraper de votaciones (senado_cookies.pkl)
    para aprovechar la reputación acumulada ante Incapsula.

    Gestión de sesiones:
    - Sesión activa: fingerprint fijo, cookies compartidas y persistentes.
    - WAF bloquea: sesión quemada → fingerprint nuevo, cookies descartadas,
      warm-up a la página principal.
    - Rotación proactiva: cada MAX_REQUESTS_PER_SESSION requests, cierra sesión
      y abre nueva con fingerprint rotado (cookies conservadas).
    """

    def __init__(self, delay: float = 2.0) -> None:
        from scraper_congreso.senadores.client import SenadoLXVIClient

        project_root = Path(__file__).resolve().parent.parent.parent.parent
        cache_dir = project_root / "cache" / "senado_perfiles"
        cache_dir.mkdir(parents=True, exist_ok=True)

        self._client: SenadoLXVIClient = SenadoLXVIClient(
            use_cache=True,
            delay=delay,
            cache_dir=cache_dir,
            cookie_path=COOKIE_PATH,
        )

    def get_perfil(self, portal_id: int) -> str | None:
        """Obtiene el HTML de un perfil de senador.

        Args:
            portal_id: ID del perfil en el portal.

        Returns:
            HTML de la página, o None si falla.

        Raises:
            SessionBurnedError: Si el WAF quemó la sesión (2+ bloqueos consecutivos).
        """
        url = PERFIL_URL_TEMPLATE.format(id=portal_id)
        try:
            return self._client.get(url, cache_key=f"perfil_{portal_id}")
        except RuntimeError as e:
            # Distinguir SessionBurnedError (dejar que suba) de otros RuntimeError
            from scraper_congreso.senadores.client import SessionBurnedError

            if isinstance(e, SessionBurnedError):
                raise
            logger.error(f"WAF bloqueó perfil {portal_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error HTTP para perfil {portal_id}: {e}")
            return None

    def get_listing_ids(self) -> list[int]:
        """Scrapea las páginas de listado del Senado LXVI y extrae IDs de senadores.

        Visita las 3 páginas de listado:
          - por_grupo_parlamentario
          - por_principio_de_eleccion
          - por_orden_alfabetico

        Returns:
            Lista ordenada de IDs únicos de senadores LXVI.
        """
        listing_paths = [
            "/66/senadores/por_grupo_parlamentario",
            "/66/senadores/por_principio_de_eleccion",
            "/66/senadores/por_orden_alfabetico",
        ]

        all_ids: set[int] = set()

        for path in listing_paths:
            url = f"{BASE_URL_LXVI}{path}"
            logger.info(f"Scrapeando listado: {url}")

            try:
                html = self._client.get(url, cache_key=f"listing_{path.replace('/', '_')}")
                ids = _extract_ids_from_listing(html)
                logger.info(f"  {path}: {len(ids)} IDs encontrados")
                all_ids.update(ids)
            except Exception as e:
                logger.error(f"Error scrapeando listado {path}: {e}")
                continue

        result = sorted(all_ids)
        logger.info(f"Total IDs únicos de listados: {len(result)}")
        return result

    def warm_up(self) -> None:
        """Prepara la sesión HTTP con un GET a la página principal del Senado.

        Carga cookies ante Incapsula y verifica que la sesión está viva
        antes de iniciar el scrapeo masivo en --from-listing.
        """
        logger.info("Warm-up: GET a página principal del Senado para cargar cookies")
        try:
            self._client.get(f"{BASE_URL_LXVI}/66/")
            logger.info("Warm-up exitoso")
        except Exception as e:
            logger.warning(f"Warm-up falló (continuando de todas formas): {e}")

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        self._client.close()


# =============================================================================
# DB Enricher
# =============================================================================


class PerfilEnricher:
    """Enriquece congreso.db con datos de perfiles del Senado.

    - Actualiza person.genero, person.curul_tipo, person.identifiers_json
    - Crea/actualiza memberships con fechas constitucionales por legislatura
    - Usa normalize_name() para matching de nombres
    - Idempotente: no sobrescribe valores no-NULL con nuevos datos
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(DB_PATH)
        self._name_cache: dict[str, list[tuple[str, str]]] | None = None

    def _get_conn(self) -> sqlite3.Connection:
        """Obtiene conexión a la BD."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _build_name_cache(self, conn: sqlite3.Connection) -> None:
        """Construye caché de nombres normalizados → [(person_id, nombre), ...]"""
        from scraper_congreso.utils.text_utils import normalize_name

        rows = conn.execute("SELECT id, nombre FROM person").fetchall()
        cache: dict[str, list[tuple[str, str]]] = {}
        for person_id, nombre in rows:
            key = normalize_name(nombre)
            if key not in cache:
                cache[key] = []
            cache[key].append((person_id, nombre))
        self._name_cache = cache
        logger.info(f"Caché de nombres construido: {len(rows)} personas")

    def _match_person(self, nombre: str, conn: sqlite3.Connection) -> tuple[str, str] | None:
        """Busca persona por nombre normalizado.

        Primero intenta match exacto por normalize_name(). Si no encuentra,
        intenta match por palabras compartidas (apellidos), manejando
        formatos invertidos como "Castro Castro, Imelda" vs "Imelda Castro Castro".

        Args:
            nombre: Nombre del senador del perfil.
            conn: Conexión activa.

        Returns:
            Tuple de (person_id, nombre_db) o None.
        """
        from scraper_congreso.utils.text_utils import normalize_name

        if self._name_cache is None:
            self._build_name_cache(conn)

        key = normalize_name(nombre)
        matches = self._name_cache.get(key, [])

        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            logger.warning(f"Múltiples matches exactos para '{nombre}': {[m[0] for m in matches]}")
            return matches[0]

        # Fallback: búsqueda por palabras compartidas
        # Maneja formatos invertidos: "Castro Castro, Imelda" vs "Imelda Castro Castro"
        return self._match_by_shared_words(nombre)

    def _match_by_shared_words(self, nombre: str) -> tuple[str, str] | None:
        """Busca persona por palabras compartidas (apellidos).

        Compara las palabras normalizadas del nombre del portal contra
        todos los nombres en la BD. Si comparten suficientes palabras
        significativas (>= 2 palabras de >= 4 chars), es un match.

        Args:
            nombre: Nombre del senador del perfil.

        Returns:
            Tuple de (person_id, nombre_db) o None.
        """
        from scraper_congreso.utils.text_utils import normalize_name

        if self._name_cache is None:
            return None

        portal_words = set(normalize_name(nombre).split())
        # Filtrar palabras muy cortas (de, la, el, etc.)
        portal_words = {w for w in portal_words if len(w) >= 3}

        best_match = None
        best_score = 0

        for cache_key, entries in self._name_cache.items():
            db_words = set(cache_key.split())
            db_words = {w for w in db_words if len(w) >= 3}

            # Palabras compartidas
            shared = portal_words & db_words
            score = len(shared)

            # Penalizar si no hay suficientes palabras compartidas
            if score < 2:
                continue

            # Bonus si las palabras son apellidos (más largas)
            long_shared = sum(1 for w in shared if len(w) >= 5)
            score_with_bonus = score + long_shared * 0.5

            if score_with_bonus > best_score:
                best_score = score_with_bonus
                best_match = entries[0]

        if best_match and best_score >= 3:
            return best_match

        return None

    def _get_legislaturas_for_person(self, person_id: str, conn: sqlite3.Connection) -> list[str]:
        """Obtiene las legislaturas en las que una persona tiene votos.

        Args:
            person_id: ID de la persona en la BD.
            conn: Conexión activa.

        Returns:
            Lista de legislaturas ordenadas (ej: ["LXIV", "LXV", "LXVI"]).
        """
        rows = conn.execute(
            """SELECT DISTINCT ve.legislatura
               FROM vote_event ve
               JOIN vote v ON v.vote_event_id = ve.id
               WHERE v.voter_id = ?
               AND ve.legislatura IS NOT NULL
               AND ve.legislatura != ''
               ORDER BY ve.legislatura""",
            (person_id,),
        ).fetchall()

        return [row[0] for row in rows]

    def enrich_person(
        self,
        perfil: SenPerfil,
        conn: sqlite3.Connection,
        dry_run: bool = False,
    ) -> dict:
        """Enriquece una persona en la BD con datos del perfil.

        Args:
            perfil: Datos parseados del perfil del senador.
            conn: Conexión activa a la BD.
            dry_run: Si True, no ejecuta cambios en la BD.

        Returns:
            Dict con estadísticas del enriquecimiento.
        """
        stats = {
            "portal_id": perfil.portal_id,
            "nombre_portal": perfil.nombre,
            "person_id": None,
            "nombre_db": None,
            "genero_actualizado": False,
            "curul_tipo_actualizado": False,
            "identifiers_actualizado": False,
            "membresias_creadas": 0,
            "membresias_actualizadas": 0,
            "status": "not_found",
        }

        if not perfil.nombre:
            stats["status"] = "empty_name"
            return stats

        # --- Match persona en la BD ---
        match = self._match_person(perfil.nombre, conn)
        if match is None:
            logger.info(f"Perfil {perfil.portal_id}: '{perfil.nombre}' no encontrado en BD")
            stats["status"] = "not_found"
            return stats

        person_id, nombre_db = match
        stats["person_id"] = person_id
        stats["nombre_db"] = nombre_db
        stats["status"] = "found"

        logger.info(f"Perfil {perfil.portal_id}: '{perfil.nombre}' → {person_id} ({nombre_db})")

        # --- Obtener valores actuales ---
        row = conn.execute(
            "SELECT genero, curul_tipo, identifiers_json FROM person WHERE id = ?",
            (person_id,),
        ).fetchone()

        if not row:
            stats["status"] = "db_error"
            return stats

        current_genero, current_curul, current_identifiers = row

        # --- Preparar actualizaciones ---
        updates = {}

        # Género: solo actualizar si el valor actual es NULL y tenemos uno nuevo
        if perfil.genero and not current_genero:
            updates["genero"] = perfil.genero
            stats["genero_actualizado"] = True
        elif perfil.genero and current_genero:
            if perfil.genero != current_genero:
                logger.warning(
                    f"Conflicto de género para {person_id}: "
                    f"DB={current_genero}, Portal={perfil.genero}"
                )

        # curul_tipo: solo actualizar si el valor actual es NULL y tenemos uno nuevo
        if perfil.curul_tipo and not current_curul:
            updates["curul_tipo"] = perfil.curul_tipo
            stats["curul_tipo_actualizado"] = True
        elif perfil.curul_tipo and current_curul:
            if perfil.curul_tipo != current_curul:
                logger.warning(
                    f"Conflicto de curul_tipo para {person_id}: "
                    f"DB={current_curul}, Portal={perfil.curul_tipo}"
                )

        # identifiers_json: merge con los existentes
        identifiers = {}
        if current_identifiers:
            try:
                identifiers = json.loads(current_identifiers)
                if isinstance(identifiers, list):
                    # Convertir lista de dicts a dict
                    identifiers = {
                        item.get("scheme", ""): item.get("identifier", "")
                        for item in identifiers
                        if isinstance(item, dict)
                    }
            except json.JSONDecodeError:
                identifiers = {}

        portal_key = "senado_gob_mx_perfil"
        if str(perfil.portal_id) not in identifiers.get(portal_key, ""):
            identifiers[portal_key] = str(perfil.portal_id)
            updates["identifiers_json"] = json.dumps(identifiers, ensure_ascii=False)
            stats["identifiers_actualizado"] = True

        # --- Ejecutar actualizaciones de person ---
        if updates and not dry_run:
            set_clauses = []
            values = []
            for col, val in updates.items():
                set_clauses.append(f"{col} = ?")
                values.append(val)

            values.append(person_id)
            sql = f"UPDATE person SET {', '.join(set_clauses)} WHERE id = ?"
            conn.execute(sql, values)
            logger.debug(f"  Actualizado person {person_id}: {list(updates.keys())}")

        # --- Membresías por legislatura ---
        legislaturas = self._get_legislaturas_for_person(person_id, conn)

        if legislaturas:
            from scraper_congreso.utils.db_helpers import get_or_create_organization

            for leg in legislaturas:
                fechas = FECHAS_LEGISLATURA.get(leg)
                if not fechas:
                    continue

                start_date, end_date = fechas

                # Determinar partido para la membership
                partido = perfil.partido if perfil.partido else None

                # Verificar si ya existe membership para esta combinación
                existing = conn.execute(
                    """SELECT id, start_date, end_date FROM membership
                       WHERE person_id = ? AND org_id = ? AND rol = ?
                       AND start_date = ?""",
                    (person_id, SENADO_ORG_ID, "senador", start_date),
                ).fetchone()

                if existing:
                    memb_id, _curr_start, curr_end = existing
                    # Si la membership existe pero no tiene end_date, actualizarla
                    if not curr_end and end_date and not dry_run:
                        conn.execute(
                            "UPDATE membership SET end_date = ? WHERE id = ?",
                            (end_date, memb_id),
                        )
                        stats["membresias_actualizadas"] += 1
                        logger.debug(f"  Actualizada membership {memb_id} con end_date={end_date}")
                else:
                    # Crear nueva membership
                    if not dry_run:
                        from scraper_congreso.utils.id_generator import next_id

                        memb_id = next_id(conn, "membership", camara="S")
                        label_parts = ["Senador"]
                        if perfil.estado:
                            label_parts.append(f"por {perfil.estado}")
                        if partido:
                            label_parts.append(f"({partido})")
                        if leg:
                            label_parts.append(f"[{leg}]")
                        label = ", ".join(label_parts)

                        org_id = SENADO_ORG_ID

                        conn.execute(
                            """INSERT OR IGNORE INTO membership
                               (id, person_id, org_id, rol, label, start_date, end_date)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (
                                memb_id,
                                person_id,
                                org_id,
                                "senador",
                                label,
                                start_date,
                                end_date,
                            ),
                        )
                        stats["membresias_creadas"] += 1
                        logger.debug(
                            f"  Creada membership {memb_id}: {start_date} → {end_date} ({leg})"
                        )

                        # También crear membership del partido si hay partido
                        if partido:
                            partido_org_id = get_or_create_organization(partido, conn)
                            existing_partido = conn.execute(
                                """SELECT id FROM membership
                                   WHERE person_id = ? AND org_id = ? AND rol = 'senador'
                                   AND start_date = ?""",
                                (person_id, partido_org_id, start_date),
                            ).fetchone()
                            if not existing_partido:
                                pmemb_id = next_id(conn, "membership", camara="S")
                                conn.execute(
                                    """INSERT OR IGNORE INTO membership
                                       (id, person_id, org_id, rol, label, start_date, end_date)
                                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                    (
                                        pmemb_id,
                                        person_id,
                                        partido_org_id,
                                        "senador",
                                        f"Senador, {partido} [{leg}]",
                                        start_date,
                                        end_date,
                                    ),
                                )
                                logger.debug(
                                    f"  Creada membership partido {pmemb_id}: {partido} [{leg}]"
                                )
                    else:
                        stats["membresias_creadas"] += 1

        return stats


# =============================================================================
# Pipeline
# =============================================================================


class PerfilPipeline:
    """Pipeline para enriquecer congreso.db desde perfiles del Senado.

    Flujo:
    1. Fetch HTML del perfil
    2. Parsear datos (nombre, género, curul_tipo, estado, partido)
    3. Match contra person en BD (por normalize_name)
    4. Actualizar person (genero, curul_tipo, identifiers_json)
    5. Crear/actualizar memberships con fechas constitucionales
    """

    def __init__(
        self,
        delay: float = 2.0,
        db_path: str | None = None,
        dry_run: bool = False,
    ):
        self.client = PerfilClient(delay=delay)
        self.enricher = PerfilEnricher(db_path=db_path)
        self.dry_run = dry_run

        # Configuración de pausa ante sesión quemada
        self._session_pause_base = (
            600  # 10 minutos base (dar tiempo a WAF a expirar bloqueo por IP)
        )
        self._session_pause_max = 1800  # 30 minutos máximo
        self._session_pause_attempts = 0

    def _handle_session_burned(self) -> bool:
        """Maneja una sesión quemada por el WAF.

        Pausa exponencialmente y reintenta con sesión limpia (nuevo fingerprint,
        sin cookies quemadas). Si se supera el máximo de pausas, retorna False
        para indicar que se debe abortar.

        Returns:
            True si se debe reintentar, False si se aborta.
        """

        self._session_pause_attempts += 1
        pause_time = min(
            self._session_pause_base * (2 ** (self._session_pause_attempts - 1)),
            self._session_pause_max,
        )
        minutes = pause_time / 60

        if self._session_pause_attempts > 3:
            logger.error(
                f"Sesión quemada {self._session_pause_attempts} veces, "
                f"abortando. El WAF no está liberando."
            )
            return False

        logger.warning(
            f"Sesión quemada (intento #{self._session_pause_attempts}). "
            f"Pausando {minutes:.0f} minutos antes de reanudar..."
        )
        time.sleep(pause_time)

        # Recrear sesión limpia: nuevo fingerprint, sin cookies quemadas, con warm-up
        self.client._client._recreate_session(skip_cookies=True)
        self.client._client.reset_waf_counter()
        logger.info("Sesión recreada (fingerprint rotado, cookies omitidas, warm-up hecho)")
        return True

    def process_one(self, portal_id: int) -> dict:
        """Procesa un solo perfil de senador.

        Args:
            portal_id: ID del perfil en el portal.

        Returns:
            Dict con estadísticas del procesamiento.
        """
        logger.info(f"Procesando perfil {portal_id}: {PERFIL_URL_TEMPLATE.format(id=portal_id)}")

        # 1. Fetch HTML
        html = self.client.get_perfil(portal_id)
        if not html:
            return {
                "portal_id": portal_id,
                "status": "fetch_failed",
            }

        # 2. Parse
        perfil = parse_perfil_html(html, portal_id)

        if not perfil.nombre:
            logger.info(f"Perfil {portal_id}: sin nombre (página inválida o vacía)")
            return {
                "portal_id": portal_id,
                "status": "empty_profile",
            }

        logger.info(
            f"  Parseado: {perfil.nombre} | "
            f"genero={perfil.genero} | curul={perfil.curul_tipo} | "
            f"estado={perfil.estado} | partido={perfil.partido}"
        )

        # 3. Enrich DB
        conn = self.enricher._get_conn()
        try:
            conn.execute("BEGIN TRANSACTION")
            stats = self.enricher.enrich_person(perfil, conn, dry_run=self.dry_run)
            conn.execute("COMMIT")
            return stats
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Error enriqueciendo perfil {portal_id}: {e}")
            return {
                "portal_id": portal_id,
                "status": "error",
                "error": str(e),
            }
        finally:
            conn.close()

    def process_range(
        self,
        start: int,
        end: int,
        limit: int | None = None,
        ids: list[int] | None = None,
    ) -> dict:
        """Itera IDs de senadores, procesando cada perfil.

        Si se pasa `ids`, usa esa lista directamente (modo --from-listing).
        Si se pasa rango (start, end), genera la secuencia. Si el rango
        excede 200 IDs, aleatoriza el orden para evadir WAF.

        Args:
            start: ID inicial (inclusive). Ignorado si se pasa `ids`.
            end: ID final (inclusive). Ignorado si se pasa `ids`.
            limit: Máximo de perfiles a procesar (None = todos).
            ids: Lista de IDs a procesar (modo --from-listing).

        Returns:
            Dict con estadísticas agregadas.
        """
        if ids is not None:
            # Modo --from-listing: usar IDs provistos
            id_list = list(ids)
            if limit:
                id_list = id_list[:limit]
            total = len(id_list)
            logger.info(
                f"Iniciando scrapeo de perfiles (from-listing) "
                f"({'DRY RUN' if self.dry_run else 'LIVE'}) ({total} IDs)"
            )
        else:
            # Modo --range
            effective_end = min(end, start + (limit - 1)) if limit else end
            total = effective_end - start + 1
            id_list = list(range(start, effective_end + 1))

            # Randomizar orden si rango amplio (>200 IDs)
            if total > 200:
                logger.info(f"Rango amplio ({total} IDs), aleatorizando orden")
                random.shuffle(id_list)
                logger.info("  orden aleatorizado")

            logger.info(
                f"Iniciando scrapeo de perfiles [{start}, {effective_end}] "
                f"({'DRY RUN' if self.dry_run else 'LIVE'}) ({total} IDs)"
            )

        stats_agg = {
            "total": total,
            "procesados": 0,
            "encontrados": 0,
            "no_encontrados": 0,
            "genero_actualizados": 0,
            "curul_actualizados": 0,
            "membresias_creadas": 0,
            "membresias_actualizadas": 0,
            "errores": 0,
            "sesiones_quemadas": 0,
        }

        from scraper_congreso.senadores.client import SessionBurnedError

        try:
            idx = 0
            while idx < len(id_list):
                portal_id = id_list[idx]
                idx += 1

                if idx % 50 == 1:
                    logger.info(f"Progreso: {portal_id} ({idx}/{total})")

                try:
                    result = self.process_one(portal_id)
                except SessionBurnedError:
                    stats_agg["sesiones_quemadas"] += 1
                    if not self._handle_session_burned():
                        logger.error(
                            f"Abortando: demasiadas sesiones quemadas "
                            f"({stats_agg['sesiones_quemadas']})"
                        )
                        break
                    # Reintentar el mismo ID con la nueva sesión
                    idx -= 1
                    continue

                stats_agg["procesados"] += 1

                if result.get("status") == "found":
                    stats_agg["encontrados"] += 1
                    stats_agg["genero_actualizados"] += int(result.get("genero_actualizado", False))
                    stats_agg["curul_actualizados"] += int(
                        result.get("curul_tipo_actualizado", False)
                    )
                    stats_agg["membresias_creadas"] += result.get("membresias_creadas", 0)
                    stats_agg["membresias_actualizadas"] += result.get("membresias_actualizadas", 0)
                elif result.get("status") == "not_found":
                    stats_agg["no_encontrados"] += 1
                elif result.get("status") in ("error", "fetch_failed"):
                    stats_agg["errores"] += 1

        finally:
            self.client.close()

        # Resumen
        logger.info(
            f"Completado: {stats_agg['encontrados']} encontrados, "
            f"{stats_agg['no_encontrados']} no encontrados, "
            f"{stats_agg['errores']} errores, "
            f"{stats_agg['sesiones_quemadas']} sesiones quemadas"
        )
        logger.info(
            f"  Géneros actualizados: {stats_agg['genero_actualizados']}, "
            f"Curules actualizados: {stats_agg['curul_actualizados']}, "
            f"Membresías creadas: {stats_agg['membresias_creadas']}"
        )

        return stats_agg

    def print_stats(self) -> None:
        """Imprime estadísticas de la BD relevantes para el scraper de perfiles."""
        conn = self.enricher._get_conn()
        try:
            # Total de personas
            total = conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
            print("\n=== Estadísticas de la BD ===")
            print(f"  Personas totales: {total}")

            # Personas sin género
            sin_genero = conn.execute(
                "SELECT COUNT(*) FROM person WHERE genero IS NULL"
            ).fetchone()[0]
            print(f"  Sin género (NULL): {sin_genero}")

            # Personas sin curul_tipo
            sin_curul = conn.execute(
                "SELECT COUNT(*) FROM person WHERE curul_tipo IS NULL"
            ).fetchone()[0]
            print(f"  Sin curul_tipo (NULL): {sin_curul}")

            # Personas con identifiers_json
            con_identifiers = conn.execute(
                "SELECT COUNT(*) FROM person WHERE identifiers_json IS NOT NULL"
            ).fetchone()[0]
            print(f"  Con identifiers_json: {con_identifiers}")

            # Desglose por género
            rows = conn.execute("SELECT genero, COUNT(*) FROM person GROUP BY genero").fetchall()
            if rows:
                print("\n--- Por Género ---")
                for genero, count in rows:
                    print(f"  {genero or 'NULL'}: {count}")

            # Desglose por curul_tipo
            rows = conn.execute(
                "SELECT curul_tipo, COUNT(*) FROM person GROUP BY curul_tipo"
            ).fetchall()
            if rows:
                print("\n--- Por Curul Tipo ---")
                for ct, count in rows:
                    print(f"  {ct or 'NULL'}: {count}")

            # Personas con identificador del portal
            con_portal = conn.execute(
                """SELECT COUNT(*) FROM person
                   WHERE identifiers_json LIKE '%senado_gob_mx_perfil%'"""
            ).fetchone()[0]
            print(f"\n  Con ID de perfil del portal: {con_portal}")

            # Membresías del Senado sin end_date
            sin_end = conn.execute(
                """SELECT COUNT(*) FROM membership
                   WHERE org_id = ? AND end_date IS NULL""",
                (SENADO_ORG_ID,),
            ).fetchone()[0]
            print(f"\n  Membresías Senado sin end_date: {sin_end}")

        finally:
            conn.close()


# =============================================================================
# CLI
# =============================================================================


def main() -> None:
    """Entry point del CLI."""
    parser = argparse.ArgumentParser(
        description="Scraper de perfiles de senadores → enriquecer congreso.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m scraper_congreso.senadores.perfiles --from-listing
  python -m scraper_congreso.senadores.perfiles --from-listing --limit 10 --dry-run
  python -m scraper_congreso.senadores.perfiles --range 1 1754
  python -m scraper_congreso.senadores.perfiles --range 1 1754 --delay 3.0
  python -m scraper_congreso.senadores.perfiles --range 1 100 --limit 10
  python -m scraper_congreso.senadores.perfiles --test-id 1
  python -m scraper_congreso.senadores.perfiles --test-id 1575 --dry-run
  python -m scraper_congreso.senadores.perfiles --stats
        """,
    )
    parser.add_argument(
        "--from-listing",
        action="store_true",
        help="Scrapea páginas de listado del Senado LXVI para obtener IDs reales de senadores",
    )
    parser.add_argument(
        "--range",
        type=int,
        nargs=2,
        metavar=("START", "END"),
        help="Rango de IDs a procesar (inicio y fin inclusivos)",
    )
    parser.add_argument(
        "--test-id",
        type=int,
        help="Procesar un solo ID para testing",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Mostrar estadísticas de la BD y salir",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No ejecuta cambios en la BD (solo simula)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay entre requests en segundos (default: 2.0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo de perfiles a procesar (default: todos)",
    )

    args = parser.parse_args()

    # Validar argumentos mutuamente exclusivos
    action_count = sum(bool(x) for x in [args.range, args.test_id, args.stats, args.from_listing])
    if action_count == 0:
        parser.error("Se requiere --from-listing, --range, --test-id o --stats")
    if action_count > 1:
        parser.error("Solo se permite una acción: --from-listing, --range, --test-id o --stats")

    if args.range and args.range[0] > args.range[1]:
        parser.error(f"Rango inválido: start={args.range[0]} > end={args.range[1]}")

    # Inicializar pipeline
    pipeline = PerfilPipeline(
        delay=args.delay,
        dry_run=args.dry_run,
    )

    # Ejecutar acción
    if args.stats:
        pipeline.print_stats()
        return

    if args.test_id:
        logger.info(f"Testeando perfil ID: {args.test_id}")
        result = pipeline.process_one(args.test_id)
        print(f"\nResultado: {json.dumps(result, indent=2, default=str)}")

        if result.get("person_id"):
            pipeline.print_stats()
        return

    if args.from_listing:
        # Warm-up antes de scrapeo
        pipeline.client.warm_up()

        # Obtener IDs de las páginas de listado
        listing_ids = pipeline.client.get_listing_ids()
        if not listing_ids:
            logger.error("No se encontraron IDs en las páginas de listado")
            return

        logger.info(f"Procesando {len(listing_ids)} IDs desde listado del Senado LXVI")
        result = pipeline.process_range(0, 0, limit=args.limit, ids=listing_ids)

        print(f"\n{'=' * 50}")
        print("Resumen (from-listing):")
        print(f"  Total IDs:              {result['total']}")
        print(f"  Procesados:             {result['procesados']}")
        print(f"  Encontrados en BD:      {result['encontrados']}")
        print(f"  No encontrados en BD:   {result['no_encontrados']}")
        print(f"  Errores:                {result['errores']}")
        print(f"  Sesiones quemadas:      {result['sesiones_quemadas']}")
        print(f"  Géneros actualizados:   {result['genero_actualizados']}")
        print(f"  Curules actualizados:   {result['curul_actualizados']}")
        print(f"  Membresías creadas:     {result['membresias_creadas']}")
        print(f"  Membresías actualiz.:   {result['membresias_actualizadas']}")
        print(f"{'=' * 50}")

        pipeline.print_stats()
        return

    if args.range:
        start, end = args.range
        result = pipeline.process_range(start, end, limit=args.limit)

        print(f"\n{'=' * 50}")
        print("Resumen:")
        print(f"  Total IDs:              {result['total']}")
        print(f"  Procesados:             {result['procesados']}")
        print(f"  Encontrados en BD:      {result['encontrados']}")
        print(f"  No encontrados en BD:   {result['no_encontrados']}")
        print(f"  Errores:                {result['errores']}")
        print(f"  Sesiones quemadas:      {result['sesiones_quemadas']}")
        print(f"  Géneros actualizados:   {result['genero_actualizados']}")
        print(f"  Curules actualizados:   {result['curul_actualizados']}")
        print(f"  Membresías creadas:     {result['membresias_creadas']}")
        print(f"  Membresías actualiz.:   {result['membresias_actualizadas']}")
        print(f"{'=' * 50}")

        pipeline.print_stats()


if __name__ == "__main__":
    main()
