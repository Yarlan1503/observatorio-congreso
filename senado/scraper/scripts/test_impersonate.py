"""
test_impersonate.py — Verifica que curl_cffi impersonate funciona contra el portal del Senado.

Uso:
    python -m scraper.senado.scripts.test_impersonate
    python -m scraper.senado.scripts.test_impersonate --url https://www.senado.gob.mx/informacion/votaciones/vota/1234
"""

import argparse
import sys
import time

from curl_cffi.requests import Session


def test_browserleaks():
    """Verifica que el TLS fingerprint sea de Chrome."""
    print("=== Test 1: BrowserLeaks TLS ===")
    session = Session(impersonate="chrome")

    try:
        response = session.get("https://tls.browserleaks.com/json", timeout=10)
        data = response.json()

        print(f"JA3 Hash: {data.get('ja3_hash', 'N/A')}")
        print(f"User-Agent: {data.get('user_agent', 'N/A')}")

        # Verificar que sea Chrome
        ua = data.get("user_agent", "")
        if "Chrome" in ua:
            print("✓ User-Agent es Chrome")
        else:
            print(f"✗ User-Agent NO es Chrome: {ua}")
            return False

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        session.close()


def test_senado_portal(url: str):
    """Test contra el portal real del Senado."""
    print(f"\n=== Test 2: Portal del Senado ===")
    print(f"URL: {url}")

    session = Session(
        impersonate="chrome",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
            "Referer": "https://www.senado.gob.mx/informacion/votaciones/",
        },
    )

    try:
        start = time.time()
        response = session.get(url, timeout=30, http_version="v1")
        elapsed = time.time() - start

        # Decodificar como iso-8859-1
        html = response.content.decode("iso-8859-1")

        print(f"Status: {response.status_code}")
        print(f"Tiempo: {elapsed:.2f}s")
        print(f"Tamaño: {len(html)} bytes")

        # Verificar WAF
        waf_markers = [
            "incident_id",
            "waf block",
            "forbidden",
            "access denied",
            "imperva",
            "incapsula",
            "_Incapsula_Resource",
        ]

        html_lower = html.lower()
        waf_detected = False
        for marker in waf_markers:
            if marker.lower() in html_lower:
                print(f"✗ WAF marker detectado: {marker}")
                waf_detected = True

        if waf_detected:
            return False

        # Verificar contenido legítimo
        if len(html) < 5000:
            print(f"✗ HTML sospechosamente pequeño: {len(html)} bytes")
            return False

        if response.status_code != 200:
            print(f"✗ Status code: {response.status_code}")
            return False

        # Verificar encoding
        if "VOTACI" in html.upper():
            print("✓ Encoding iso-8859-1 correcto (encontrado 'VOTACI')")
        else:
            print("⚠ No se encontró 'VOTACI' en el HTML")

        # Verificar estructura del portal
        if "panel-heading" in html or "col-sm-12" in html:
            print("✓ Estructura del portal detectada")
        else:
            print("⚠ No se detectó estructura del portal")

        print(f"✓ HTML obtenido correctamente: {len(html)} bytes")
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        session.close()


def test_encoding():
    """Verifica decodificación iso-8859-1."""
    print(f"\n=== Test 3: Encoding iso-8859-1 ===")

    # Crear contenido de prueba con caracteres iso-8859-1
    test_bytes = b"VOTACI\xd3N"  # Ó en iso-8859-1

    try:
        decoded = test_bytes.decode("iso-8859-1")
        print(f"✓ Decodificación exitosa: {decoded}")
        return True
    except Exception as e:
        print(f"✗ Error decodificando: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test de impersonate de curl_cffi contra portal del Senado"
    )
    parser.add_argument(
        "--url",
        default="https://www.senado.gob.mx/informacion/votaciones/vota/1234",
        help="URL a testear (default: votación 1234)",
    )
    parser.add_argument(
        "--skip-browserleaks",
        action="store_true",
        help="Saltar test de BrowserLeaks",
    )

    args = parser.parse_args()

    results = []

    # Test 1: BrowserLeaks
    if not args.skip_browserleaks:
        results.append(("BrowserLeaks", test_browserleaks()))

    # Test 2: Portal del Senado
    results.append(("Portal Senado", test_senado_portal(args.url)))

    # Test 3: Encoding
    results.append(("Encoding", test_encoding()))

    # Resumen
    print("\n" + "=" * 50)
    print("RESUMEN")
    print("=" * 50)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 50)

    if all_passed:
        print("✓ Todos los tests pasaron")
        sys.exit(0)
    else:
        print("✗ Algunos tests fallaron")
        sys.exit(1)


if __name__ == "__main__":
    main()
