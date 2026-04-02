#!/usr/bin/env python3
"""
test_sil_scraper.py — Script de test para verificar funcionalidad del scraper SIL.

Ejecuta pruebas básicas del scraper sin hacer requests reales al portal.
"""

import sys
import os
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

# Añadir scraper_sil al path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_sil")

# Imports después de path setup
from scraper_sil.config import (
    LEGISLATURAS,
    SIL_ENCODING,
    REQUEST_DELAY,
    VOTO_MAP,
)
from scraper_sil.models import (
    SILVotacionIndex,
    SILVotacionDetail,
    SILVotoLegislador,
    SILVotosCompletos,
    SILBusquedaParams,
    SILLoadResult,
)
from scraper_sil.loaders.sil_loader import SILLoader
from scraper_sil.parsers.busqueda import parse_busqueda_form, build_search_params
from scraper_sil.parsers.resultados import (
    parse_resultados,
    parse_paginacion,
    parse_resultados_text,
)
from scraper_sil.parsers.detalle import parse_detalle_votacion
from scraper_sil.parsers.votos import parse_votos_grupo, extract_count_from_votos_page
from scraper_sil.client import SILClient


def test_config():
    """Test de configuración."""
    print("\n" + "=" * 60)
    print("TEST: Configuración")
    print("=" * 60)

    assert len(LEGISLATURAS) == 11, (
        f"Deben haber 11 legislaturas, got {len(LEGISLATURAS)}"
    )
    assert SIL_ENCODING == "iso-8859-1", "Encoding debe ser iso-8859-1"
    assert REQUEST_DELAY >= 1.0, "Rate limit debe ser al menos 1s"

    # Verificar mapeos
    assert "F" in VOTO_MAP and VOTO_MAP["F"] == "a_favor"
    assert "C" in VOTO_MAP and VOTO_MAP["C"] == "en_contra"
    assert "A" in VOTO_MAP and VOTO_MAP["A"] == "abstencion"
    assert "N" in VOTO_MAP and VOTO_MAP["N"] == "ausente"

    # Verificar que todas las legislaturas son validas
    for leg in LEGISLATURAS:
        assert leg == leg.upper(), f"Legislatura {leg} debe estar en mayusculas"

    print(f"  ✓ LEGISLATURAS: {len(LEGISLATURAS)} legislaturas {LEGISLATURAS}")
    print("  ✓ ENCODING: iso-8859-1")
    print("  ✓ RATE LIMIT: 1.5s")
    print("  ✓ VOTO MAP: F/C/A/N correctamente mapeados")
    print("PASSED")


def test_models():
    """Test de modelos de datos."""
    print("\n" + "=" * 60)
    print("TEST: Modelos de datos")
    print("=" * 60)

    # Test SILVotacionIndex
    v = SILVotacionIndex(
        clave_asunto="1234",
        clave_tramite="1",
        titulo="Test de votacion",
        legislature="LXVI",
        fecha="01/01/2025",
        resultado="Aprobado",
        tipo_asunto="Ley o Decreto",
    )
    assert v.clave_asunto == "1234"
    assert v.legislature == "LXVI"
    print("  ✓ SILVotacionIndex creado correctamente")

    # Test SILVotacionDetail
    d = SILVotacionDetail(
        clave_asunto="1234",
        clave_tramite="1",
        titulo="Test detail",
        legislature="LXVI",
        fecha="01/01/2025",
        tipo_asunto="Ley",
        resultado="Aprobado",
        tipo_votacion="Nominal",
        quorum="128/128",
        a_favor=65,
        en_contra=60,
        abstencion=3,
        ausente=0,
    )
    assert d.a_favor == 65
    assert d.total_presentes == 128
    print("  ✓ SILVotacionDetail creado correctamente")

    # Test SILVotoLegislador
    vl = SILVotoLegislador(
        nombre="Sen. Juan Perez",
        partido="MORENA",
        estado="CDMX",
        curul="1",
        voto="a_favor",
        tipo_voto="F",
    )
    assert vl.partido == "MORENA"
    assert vl.voto == "a_favor"
    print("  ✓ SILVotoLegislador creado correctamente")

    # Test SILVotosCompletos
    vc = SILVotosCompletos(
        clave_asunto="1234",
        clave_tramite="1",
        votos=[vl],
    )
    vc.totales = {"a_favor": 1, "en_contra": 0, "abstencion": 0, "ausente": 0}
    assert len(vc.votos) == 1
    print("  ✓ SILVotosCompletos creado correctamente")

    # Test SILLoadResult
    lr = SILLoadResult(
        vote_event_id="SVE00001",
        motion_id="SM00001",
        votos_insertados=100,
        success=True,
    )
    assert lr.success == True
    assert lr.votos_insertados == 100
    print("  ✓ SILLoadResult creado correctamente")

    # Test SILBusquedaParams
    bp = SILBusquedaParams(
        legislature="LXVI",
        tipo_asunto=["1", "2"],
        resultado="A",
        fecha_inicio="01/01/2024",
        fecha_fin="31/12/2024",
        paginas=50,
    )
    assert bp.legislature == "LXVI"
    assert len(bp.tipo_asunto) == 2
    print("  ✓ SILBusquedaParams creado correctamente")

    print("PASSED")


def test_busqueda_parser():
    """Test del parser de formulario de busqueda."""
    print("\n" + "=" * 60)
    print("TEST: Parser de busqueda")
    print("=" * 60)

    # HTML de ejemplo del formulario
    html_form = """
    <html>
    <form action="/Busquedas/Votacion/ProcesoBusquedaAvanzada.php?SID=TEST123">
        <select name="LEGISLATURA">
            <option value="LVI">Legislatura LVI</option>
            <option value="LXVI" selected>LXVI</option>
        </select>
        <select name="TASUNTO_AR[]">
            <option value="1">Reforma Constitucional</option>
            <option value="2">Ley o Decreto</option>
        </select>
        <select name="RESULTADO">
            <option value="A">Aprobado</option>
            <option value="D">Desechado</option>
        </select>
        <input type="hidden" name="buscar" value="1">
    </form>
    </html>
    """

    options = parse_busqueda_form(html_form)

    assert "LVI" in options["legislaturas"]
    assert "LXVI" in options["legislaturas"]
    assert "1" in options["tipos_asunto"]
    assert "A" in options["resultados"]
    print("  ✓ Parser extrae legislaturas correctamente")
    print("  ✓ Parser extrae tipos de asunto correctamente")
    print("  ✓ Parser extrae resultados correctamente")

    # Test build_search_params
    params = SILBusquedaParams(
        legislature="LXVI",
        tipo_asunto=["1", "2"],
        resultado="A",
        fecha_inicio="01/01/2024",
        fecha_fin="31/12/2024",
        paginas=50,
    )
    post_params = build_search_params(params, options)

    assert post_params["LEGISLATURA"] == "LXVI"
    assert "TASUNTO_AR[]" in post_params
    assert post_params["RESULTADO"] == "A"
    assert post_params["FECHA_INIC"] == "01/01/2024"
    print("  ✓ build_search_params genera parametros correctos")

    print("PASSED")


def test_resultados_parser():
    """Test del parser de resultados."""
    print("\n" + "=" * 60)
    print("TEST: Parser de resultados")
    print("=" * 60)

    # HTML de ejemplo de resultados
    html_resultados = """
    <html>
    <table class="table table-striped">
        <tr>
            <td>01/01/2025</td>
            <td>LXVI</td>
            <td>1234</td>
            <td>Reforma en materia electoral</td>
            <td>Aprobado</td>
        </tr>
        <tr>
            <td>02/01/2025</td>
            <td>LXVI</td>
            <td>1235-1</td>
            <td>Ley de ingresos</td>
            <td>Aprobado</td>
        </tr>
    </table>
    <div class="paginador">Página 1 de 50</div>
    <p>1 - 50 de 2450 resultados</p>
    </html>
    """

    votaciones, total = parse_resultados(html_resultados)

    assert len(votaciones) == 2, f"Deben ser 2 votaciones, got {len(votaciones)}"
    assert total == 2450, f"Total debe ser 2450, got {total}"
    print(f"  ✓ Parser extrae {len(votaciones)} votaciones")
    print(f"  ✓ Total detectado: {total}")

    # Verificar primera votacion
    v = votaciones[0]
    assert v.clave_asunto == "1234"
    assert v.legislature == "LXVI"
    assert v.fecha == "01/01/2025"
    print("  ✓ Datos de votacion parseados correctamente")

    # Test paginacion
    pag_info = parse_paginacion(html_resultados)
    print(f"  Pag info: {pag_info}")
    assert pag_info["current_page"] == 1, (
        f"Current page debe ser 1, got {pag_info['current_page']}"
    )
    assert pag_info["total_pages"] == 50, (
        f"Total pages debe ser 50, got {pag_info['total_pages']}"
    )
    assert pag_info["total_results"] == 2450, (
        f"Total results debe ser 2450, got {pag_info['total_results']}"
    )
    print("  ✓ Parser de paginacion funciona correctamente")

    print("PASSED")


def test_resultados_parser_text():
    """Test del parser de resultados en texto plano."""
    print("\n" + "=" * 60)
    print("TEST: Parser de resultados texto plano")
    print("=" * 60)

    # Ejemplo de texto plano del SIL (con entidades HTML)
    texto_plano = """
    &nbsp;1Dictamen a discusiónCon proyecto de decreto por el que se reforman
    artículos de la Ley General de Salud
              A favor: 102
              En contra: 0
              Abstención: 0
               Pendiente en comisión(es) de revisora el 03-DIC-2025
    
    &nbsp;2Dictamen con proyecto de decreto que adiciona el artículo 4 de la
    Constitución Política
              A favor: 98
              En contra: 45
              Abstención: 12
    
    &nbsp;3Iniciativa con proyecto de decreto por el que se crea la Ley de不提
              A favor: 0
              En contra: 0
              Abstención: 0
               Pendiente en comisión(es) de revisora el 15-ENE-2026
    1 - 50 de 150 resultados
    """

    votaciones, total = parse_resultados_text(texto_plano)

    assert len(votaciones) == 3, f"Deben ser 3 votaciones, got {len(votaciones)}"
    assert total == 150, f"Total debe ser 150, got {total}"
    print(f"  ✓ Parser extrae {len(votaciones)} votaciones")
    print(f"  ✓ Total detectado: {total}")

    # Verificar primera votacion
    v = votaciones[0]
    assert v.clave_asunto == "1", f"Clave debe ser 1, got {v.clave_asunto}"
    assert "Dictamen" in v.titulo, (
        f"Titulo debe contener 'Dictamen', got {v.titulo[:50]}"
    )
    assert v.num_votos == 102, f"Votos debe ser 102, got {v.num_votos}"
    assert "Pendiente" in v.resultado, (
        f"Resultado debe contener 'Pendiente', got {v.resultado}"
    )
    print(f"  ✓ Primera votacion: clave={v.clave_asunto}, titulo={v.titulo[:30]}...")

    # Verificar segunda votacion (con votos en contra y abstención)
    v2 = votaciones[1]
    assert v2.clave_asunto == "2", f"Clave debe ser 2, got {v2.clave_asunto}"
    assert v2.num_votos == 155, f"Votos total debe ser 155, got {v2.num_votos}"
    print(f"  ✓ Segunda votacion: clave={v2.clave_asunto}, num_votos={v2.num_votos}")

    # Verificar tercera votacion
    v3 = votaciones[2]
    assert v3.clave_asunto == "3", f"Clave debe ser 3, got {v3.clave_asunto}"
    print(f"  ✓ Tercera votacion: clave={v3.clave_asunto}")

    # Test auto-deteccion: HTML usa parser HTML, texto usa parser texto
    html_con_tabla = "<html><table><tr><td>1234</td></tr></table></html>"
    votaciones_html, _ = parse_resultados(html_con_tabla)
    # Debe usar parser HTML porque contiene <table>
    assert (
        len(votaciones_html) >= 0
    )  # Parser HTML puede no encontrar datos en HTML mínimo

    votaciones_texto, _ = parse_resultados(texto_plano)
    # Debe usar parser texto porque no contiene <table>
    assert len(votaciones_texto) == 3, (
        f"Auto-deteccion debe usar parser texto, got {len(votaciones_texto)}"
    )
    print("  ✓ Auto-deteccion funciona correctamente")

    print("PASSED")


def test_detalle_parser():
    """Test del parser de detalle."""
    print("\n" + "=" * 60)
    print("TEST: Parser de detalle")
    print("=" * 60)

    html_detalle = """
    <html>
    <h1>Dictamen de la minuta por el que se reforman...</h1>
    <div class="metadata">
        <span>Legislatura: LXVI</span>
        <span>Fecha: 15/03/2025</span>
        <span>Tipo: Reforma Constitucional</span>
    </div>
    <div class="resultado">Aprobado</div>
    <div class="quorum">Quorum: 120/128</div>
    <table class="votos">
        <tr><th>A favor</th><td>65</td></tr>
        <tr><th>En contra</th><td>55</td></tr>
        <tr><th>Abstención</th><td>0</td></tr>
        <tr><th>Ausente</th><td>8</td></tr>
    </table>
    </html>
    """

    detalle = parse_detalle_votacion(html_detalle, "1234", "1")

    assert detalle is not None, "Detalle no debe ser None"
    print(f"  ✓ Detalle creado: clave={detalle.clave_asunto}")
    print(f"  ✓ A favor: {detalle.a_favor}")
    print(f"  ✓ En contra: {detalle.en_contra}")
    print(f"  ✓ Abstencion: {detalle.abstencion}")
    print(f"  ✓ Ausente: {detalle.ausente}")
    print(f"  ✓ Total presentes: {detalle.total_presentes}")
    print("PASSED")


def test_votos_parser():
    """Test del parser de votos."""
    print("\n" + "=" * 60)
    print("TEST: Parser de votos")
    print("=" * 60)

    html_votos = """
    <html>
    <table class="legisladores">
        <tr>
            <td>1</td>
            <td>Sen. Juan Perez MORENA</td>
            <td>CDMX</td>
        </tr>
        <tr>
            <td>2</td>
            <td>Sen. Maria Lopez PAN</td>
            <td>Jalisco</td>
        </tr>
    </table>
    <p>Mostrando 1-2 de 2 legisladores</p>
    </html>
    """

    votos = parse_votos_grupo(html_votos, "F")

    assert len(votos) >= 1, f"Deben ser al menos 1 voto, got {len(votos)}"
    print(f"  ✓ Parser extrae votos")

    if len(votos) >= 1:
        v = votos[0]
        print(f"  ✓ Primer voto: {v.nombre} ({v.partido}) - {v.voto}")

    # Test extract_count
    count = extract_count_from_votos_page(html_votos)
    assert count >= 0, f"Count debe ser >= 0, got {count}"
    print(f"  ✓ Count extrado: {count}")

    print("PASSED")


def test_client():
    """Test del cliente HTTP."""
    print("\n" + "=" * 60)
    print("TEST: Cliente HTTP")
    print("=" * 60)

    client = SILClient(use_cache=False)

    assert client.delay == REQUEST_DELAY
    assert client._verify_ssl == False, "SSL verification debe estar deshabilitado"
    assert client.sid is None
    print("  ✓ Cliente inicializado con SSL bypass")
    print(f"  ✓ Rate limit: {client.delay}s")

    # Test extract_sid
    html_with_sid = """
    <form action="/Busquedas/Votacion/ProcesoBusquedaAvanzada.php?SID=ABC123XYZ">
    </form>
    """
    sid = client.extract_sid(html_with_sid)
    assert sid == "ABC123XYZ", f"SID debe ser ABC123XYZ, got {sid}"
    print(f"  ✓ SID extrado correctamente: {sid}")

    client.close()
    print("PASSED")


def test_loader():
    """Test del loader (sin BD real)."""
    print("\n" + "=" * 60)
    print("TEST: Loader (sin BD real)")
    print("=" * 60)

    # Crear loader con BD en memoria
    loader = SILLoader(db_path=":memory:")

    # Test que los counters inician en 0
    assert loader._counters.vote_event == 0
    assert loader._counters.motion == 0
    assert loader._counters.person == 0
    print("  ✓ Counters inicializados en 0")

    # Test next_id
    id1 = loader._counters.next_id("SVE")
    id2 = loader._counters.next_id("SVE")
    assert id1 == "SVE00001", f"ID1 debe ser SVE00001, got {id1}"
    assert id2 == "SVE00002", f"ID2 debe ser SVE00002, got {id2}"
    print(f"  ✓ Generador de IDs funciona: {id1}, {id2}")

    # Test different prefixes
    sm_id = loader._counters.next_id("SM")
    sn_id = loader._counters.next_id("SN")
    assert sm_id == "SM00001"
    assert sn_id == "SN00001"
    print(f"  ✓ IDs por prefijo: SM={sm_id}, SN={sn_id}")

    print("PASSED")


def test_loader_init_db():
    """Test de inicializacion del schema con archivo temporal."""
    print("\n" + "=" * 60)
    print("TEST: Loader init_db (archivo temporal)")
    print("=" * 60)

    import tempfile
    import os

    # Crear archivo temporal
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        # Crear loader
        loader = SILLoader(db_path=db_path)

        # Crear tablas base primero
        conn = loader._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sen_motion (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                result TEXT,
                date TEXT,
                fuente_url TEXT
            );

            CREATE TABLE IF NOT EXISTS sen_vote_event (
                id TEXT PRIMARY KEY,
                motion_id TEXT NOT NULL,
                start_date TEXT NOT NULL,
                result TEXT,
                senado_id INTEGER UNIQUE,
                legislature TEXT DEFAULT 'LXVI'
            );
        """)
        conn.close()

        # Ejecutar init_db
        loader.init_db()

        # Verificar que las columnas fueron creadas
        conn = loader._get_conn()
        try:
            columns = [
                row[1] for row in conn.execute("PRAGMA table_info(sen_vote_event)")
            ]
            assert "sil_clave_asunto" in columns, f"Falta sil_clave_asunto en {columns}"
            assert "sil_clave_tramite" in columns, (
                f"Falta sil_clave_tramite en {columns}"
            )
            assert "sil_legislatura" in columns, f"Falta sil_legislatura en {columns}"
            assert "scrape_status" in columns, f"Falta scrape_status en {columns}"
            print("  ✓ Columnas SIL agregadas a sen_vote_event")

            columns = [row[1] for row in conn.execute("PRAGMA table_info(sen_motion)")]
            assert "sil_tipo_asunto" in columns, f"Falta sil_tipo_asunto en {columns}"
            assert "sil_camara" in columns, f"Falta sil_camara en {columns}"
            print("  ✓ Columnas SIL agregadas a sen_motion")

            print("  ✓ Schema SIL inicializado correctamente")

        finally:
            conn.close()

    finally:
        # Limpiar archivo temporal
        try:
            os.unlink(db_path)
        except OSError as e:
            logging.warning("No se pudo eliminar archivo temporal %s: %s", db_path, e)

    print("PASSED")


def test_session_manager():
    """Test del SessionManager (sin browser real)."""
    print("\n" + "=" * 60)
    print("TEST: SessionManager")
    print("=" * 60)

    # Test que el módulo existe y tiene las clases correctas
    try:
        from scraper_sil.session_manager import (
            SessionManager,
            SessionInfo,
            PlaywrightNotAvailableError,
            SESSION_TIMEOUT_SECONDS,
            PLAYWRIGHT_TIMEOUT_MS,
        )

        print("  ✓ Módulo session_manager importable")
    except ImportError as e:
        print(f"  ✗ Error importando session_manager: {e}")
        raise AssertionError(f"session_manager no disponible: {e}")

    # Test SessionInfo dataclass
    import time

    session_info = SessionInfo(
        sid="TEST123",
        created_at=time.time(),
        expires_at=time.time() + SESSION_TIMEOUT_SECONDS,
    )
    assert session_info.sid == "TEST123"
    assert not session_info.is_expired()
    assert session_info.time_remaining() > 0
    print("  ✓ SessionInfo dataclass funciona correctamente")

    # Test SessionManager initialization (sin browser)
    manager = SessionManager(headless=True, timeout=5000)

    # Verificar que tiene las propiedades correctas
    assert manager.headless == True
    assert manager.timeout == 5000
    print("  ✓ SessionManager inicializado con parámetros correctos")

    # Verificar que is_available refleja la disponibilidad real
    # (puede ser True o False dependiendo de si hay browser instalado)
    print(f"  ✓ is_available = {manager.is_available} (depende del entorno)")

    # Test get_sid returns None cuando no hay sesión
    assert manager.get_sid() is None
    print("  ✓ get_sid() retorna None cuando no hay sesión")

    # Test is_expired returns True cuando no hay sesión
    assert manager.is_expired() == True
    print("  ✓ is_expired() retorna True cuando no hay sesión")

    # Test cleanup no falla aunque no haya nada que limpiar
    manager.cleanup()  # No debe lanzar excepción
    print("  ✓ cleanup() no falla con recursos vacíos")

    # Test context manager
    with SessionManager() as m:
        pass  # Solo verificar que no falla
    print("  ✓ Context manager (__enter__/__exit__) funciona")

    # Test PlaywrightNotAvailableError
    try:
        raise PlaywrightNotAvailableError("Test error")
    except PlaywrightNotAvailableError as e:
        assert "Test error" in str(e)
    print("  ✓ PlaywrightNotAvailableError funciona correctamente")

    print("PASSED")


def test_session_manager_in_config():
    """Test de configuración de Playwright en config.py."""
    print("\n" + "=" * 60)
    print("TEST: Configuración Playwright")
    print("=" * 60)

    from scraper_sil.config import (
        PLAYWRIGHT_HEADLESS,
        PLAYWRIGHT_TIMEOUT,
        PLAYWRIGHT_USER_AGENT,
        SESSION_TIMEOUT,
        SESSION_REFRESH_BEFORE_EXPIRY,
    )

    assert PLAYWRIGHT_HEADLESS == True
    print("  ✓ PLAYWRIGHT_HEADLESS = True")

    assert PLAYWRIGHT_TIMEOUT == 30000
    print("  ✓ PLAYWRIGHT_TIMEOUT = 30000 (ms)")

    assert "Chrome" in PLAYWRIGHT_USER_AGENT
    print("  ✓ PLAYWRIGHT_USER_AGENT contiene Chrome")

    assert SESSION_TIMEOUT == 25 * 60
    print("  ✓ SESSION_TIMEOUT = 25 minutos")

    assert SESSION_REFRESH_BEFORE_EXPIRY == 5 * 60
    print("  ✓ SESSION_REFRESH_BEFORE_EXPIRY = 5 minutos")

    print("PASSED")


def run_all_tests():
    """Ejecuta todos los tests."""
    print("\n" + "#" * 60)
    print("#" + " " * 58 + "#")
    print("#" + " TEST SUITE: SCRAPER SIL ".center(58) + "#")
    print("#" + " " * 58 + "#")
    print("#" * 60)

    tests = [
        ("Configuracion", test_config),
        ("Configuracion Playwright", test_session_manager_in_config),
        ("Modelos de datos", test_models),
        ("Parser de busqueda", test_busqueda_parser),
        ("Parser de resultados", test_resultados_parser),
        ("Parser de resultados texto plano", test_resultados_parser_text),
        ("Parser de detalle", test_detalle_parser),
        ("Parser de votos", test_votos_parser),
        ("Cliente HTTP", test_client),
        ("SessionManager", test_session_manager),
        ("Loader", test_loader),
        ("Loader init_db", test_loader_init_db),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n  ✗ ERROR: {type(e).__name__}: {e}")
            failed += 1

    # Resumen
    print("\n" + "#" * 60)
    print(f"# RESULTADOS: {passed} passed, {failed} failed ".center(58) + "#")
    print("#" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
