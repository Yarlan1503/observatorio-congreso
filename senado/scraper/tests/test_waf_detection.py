"""
test_waf_detection.py — Tests unitarios para detección de WAF Incapsula.

Uso:
    pytest senado/scraper/tests/test_waf_detection.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Importar la clase (se probará con mock de curl_cffi)
# Nota: Estos tests verifican la lógica de detección, no la conexión real


class TestWafDetection:
    """Tests para _is_waf_response()."""

    def _create_client(self):
        """Crea un cliente mock para testing."""
        # Mock de curl_cffi.Session
        with patch("cli.Session") as mock_session:
            mock_session.return_value = MagicMock()

            from senado.scraper.cli import SenateClientWithLegacyHeaders

            client = SenateClientWithLegacyHeaders(use_cache=False)
            return client

    def test_waf_marker_incident_id(self):
        """Detecta marcador 'incident_id'."""
        client = self._create_client()

        html = "<html><body>incident_id: 12345</body></html>"
        assert client._is_waf_response(html, 200) == True

    def test_waf_marker_waf_block(self):
        """Detecta marcador 'waf block'."""
        client = self._create_client()

        html = "<html><body>WAF BLOCK detected</body></html>"
        assert client._is_waf_response(html, 200) == True

    def test_waf_marker_forbidden(self):
        """Detecta marcador 'forbidden'."""
        client = self._create_client()

        html = "<html><body>Forbidden access</body></html>"
        assert client._is_waf_response(html, 200) == True

    def test_waf_marker_access_denied(self):
        """Detecta marcador 'access denied'."""
        client = self._create_client()

        html = "<html><body>Access Denied</body></html>"
        assert client._is_waf_response(html, 200) == True

    def test_waf_marker_imperva(self):
        """Detecta marcador 'imperva'."""
        client = self._create_client()

        html = "<html><body>Powered by Imperva</body></html>"
        assert client._is_waf_response(html, 200) == True

    def test_waf_marker_incapsula(self):
        """Detecta marcador 'incapsula'."""
        client = self._create_client()

        html = "<html><body>Incapsula incident</body></html>"
        assert client._is_waf_response(html, 200) == True

    def test_waf_marker_incapsula_resource(self):
        """Detecta marcador '_Incapsula_Resource'."""
        client = self._create_client()

        html = "<html><body>_Incapsula_Resource?id=123</body></html>"
        assert client._is_waf_response(html, 200) == True

    def test_waf_status_403(self):
        """Detecta status code 403."""
        client = self._create_client()

        html = "<html><body>OK</body></html>"
        assert client._is_waf_response(html, 403) == True

    def test_waf_status_429(self):
        """Detecta status code 429 (rate limit)."""
        client = self._create_client()

        html = "<html><body>OK</body></html>"
        assert client._is_waf_response(html, 429) == True

    def test_waf_status_503(self):
        """Detecta status code 503."""
        client = self._create_client()

        html = "<html><body>OK</body></html>"
        assert client._is_waf_response(html, 503) == True

    def test_legitimate_response(self):
        """No detecta WAF en respuesta legítima."""
        client = self._create_client()

        # HTML grande sin marcadores
        html = "<html><body>" + "x" * 10000 + "</body></html>"
        assert client._is_waf_response(html, 200) == False

    def test_small_response_no_markers(self):
        """Respuesta pequeña sin marcadores NO es WAF (solo warning)."""
        client = self._create_client()

        # HTML pequeño pero sin marcadores
        html = "<html><body>OK</body></html>"
        # No debe marcar como WAF solo por tamaño
        assert client._is_waf_response(html, 200) == False

    def test_case_insensitive(self):
        """Detección es case-insensitive."""
        client = self._create_client()

        html = "<html><body>INCIDENT_ID: 123</body></html>"
        assert client._is_waf_response(html, 200) == True

        html = "<html><body>Incident_Id: 123</body></html>"
        assert client._is_waf_response(html, 200) == True


class TestBackoff:
    """Tests para _backoff()."""

    def test_backoff_timing(self):
        """Verifica cálculo de backoff exponencial."""
        with patch("cli.Session") as mock_session:
            mock_session.return_value = MagicMock()

            from senado.scraper.cli import SenateClientWithLegacyHeaders

            client = SenateClientWithLegacyHeaders(use_cache=False)

            # Intento 0: 2 * 2^0 = 2s
            # Intento 1: 2 * 2^1 = 4s
            # Intento 2: 2 * 2^2 = 8s

            # Verificar que time.sleep es llamado con el tiempo correcto
            with patch("time.sleep") as mock_sleep:
                client._backoff(0)
                mock_sleep.assert_called_with(2.0)

                client._backoff(1)
                mock_sleep.assert_called_with(4.0)

                client._backoff(2)
                mock_sleep.assert_called_with(8.0)


class TestCookiePersistence:
    """Tests para persistencia de cookies."""

    def test_save_cookies(self):
        """Verifica que cookies se guardan."""
        with patch("cli.Session") as mock_session:
            mock_session.return_value = MagicMock()
            mock_session.return_value.cookies = {"test": "value"}

            from senado.scraper.cli import SenateClientWithLegacyHeaders

            client = SenateClientWithLegacyHeaders(use_cache=False)

            with patch("builtins.open", create=True) as mock_open:
                with patch("pickle.dump") as mock_dump:
                    client._save_cookies()
                    mock_dump.assert_called_once()

    def test_load_cookies(self):
        """Verifica que cookies se cargan."""
        with patch("cli.Session") as mock_session:
            mock_session.return_value = MagicMock()

            with patch("pathlib.Path.exists", return_value=True):
                with patch("builtins.open", create=True):
                    with patch("pickle.load", return_value={"test": "value"}):
                        from senado.scraper.cli import SenateClientWithLegacyHeaders

                        client = SenateClientWithLegacyHeaders(use_cache=False)

                        # Verificar que cookies se actualizaron
                        mock_session.return_value.cookies.update.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
