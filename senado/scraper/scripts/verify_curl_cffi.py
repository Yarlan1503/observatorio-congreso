"""
verify_curl_cffi.py — Verifica que curl_cffi está instalado y funciona.

Uso:
    python verify_curl_cffi.py
"""

import sys


def verify_import():
    """Verifica que curl_cffi se puede importar."""
    print("=== Verificación 1: Import ===")
    try:
        from curl_cffi.requests import Session

        print("✓ curl_cffi importado correctamente")
        return True
    except ImportError as e:
        print(f"✗ Error importando curl_cffi: {e}")
        print("  Instalar con: pip install curl_cffi>=0.15.0")
        return False


def verify_version():
    """Verifica la versión de curl_cffi."""
    print("\n=== Verificación 2: Versión ===")
    try:
        import curl_cffi

        version = getattr(curl_cffi, "__version__", "unknown")
        print(f"✓ Versión: {version}")

        # Verificar que sea >= 0.15.0
        if version != "unknown":
            parts = version.split(".")
            if len(parts) >= 2:
                major = int(parts[0])
                minor = int(parts[1])
                if major > 0 or (major == 0 and minor >= 15):
                    print("✓ Versión >= 0.15.0")
                    return True
                else:
                    print(f"⚠ Versión {version} < 0.15.0")
                    print("  Actualizar con: pip install curl_cffi>=0.15.0")
                    return False
        return True
    except Exception as e:
        print(f"✗ Error verificando versión: {e}")
        return False


def verify_impersonate():
    """Verifica que impersonate funciona."""
    print("\n=== Verificación 3: Impersonate ===")
    try:
        from curl_cffi.requests import Session

        session = Session(impersonate="chrome")
        print("✓ Sesión creada con impersonate='chrome'")

        # Test simple (sin hacer request real)
        session.close()
        print("✓ Sesión cerrada correctamente")
        return True
    except Exception as e:
        print(f"✗ Error con impersonate: {e}")
        return False


def verify_http_version():
    """Verifica que http_version se puede especificar."""
    print("\n=== Verificación 4: HTTP Version ===")
    try:
        from curl_cffi.requests import Session

        session = Session(impersonate="chrome")

        # Verificar que el método get acepta http_version
        # (no hacemos request real, solo verificamos que no hay error de sintaxis)
        import inspect

        sig = inspect.signature(session.get)
        params = list(sig.parameters.keys())

        if "http_version" in params:
            print("✓ http_version es un parámetro válido")
        else:
            print("⚠ http_version no encontrado en parámetros")
            print(f"  Parámetros disponibles: {params}")

        session.close()
        return True
    except Exception as e:
        print(f"✗ Error verificando http_version: {e}")
        return False


def main():
    """Ejecuta todas las verificaciones."""
    print("Verificación de curl_cffi para scraper del Senado")
    print("=" * 50)

    results = []
    results.append(("Import", verify_import()))
    results.append(("Versión", verify_version()))
    results.append(("Impersonate", verify_impersonate()))
    results.append(("HTTP Version", verify_http_version()))

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
        print("✓ curl_cffi está listo para usar")
        print("\nPróximos pasos:")
        print("1. Ejecutar: python -m senado.scraper.scripts.test_impersonate")
        print("2. Si pasa, reemplazar cli.py por cli_curl_cffi.py")
        sys.exit(0)
    else:
        print("✗ curl_cffi tiene problemas")
        print("\nSolución:")
        print("pip install curl_cffi>=0.15.0")
        sys.exit(1)


if __name__ == "__main__":
    main()
