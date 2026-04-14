"""
test_waf_detection.py — Tests unitarios para detección de WAF Incapsula.

Uso:
    pytest tests/senadores/test_waf_detection.py -v
"""

from unittest.mock import MagicMock, patch

import pytest


class TestWafDetection:
    """Tests para SenadoLXVIClient._is_waf_response()."""

    def _create_client(self):
        """Crea un cliente mock para testing."""
        with patch("scraper_congreso.senadores.client.Session") as mock_session:
            mock_session.return_value = MagicMock()

            from scraper_congreso.senadores.client import SenadoLXVIClient

            client = SenadoLXVIClient(use_cache=False)
            return client

    def test_waf_marker_incident_id(self):
        """Detecta marcador 'incident_id'."""
        client = self._create_client()

        html = "<html><body>incident_id: 12345</body></html>"
        assert client._is_waf_response(html, 200)

    def test_waf_marker_waf_block(self):
        """Detecta marcador 'waf block'."""
        client = self._create_client()

        html = "<html><body>WAF BLOCK detected</body></html>"
        assert client._is_waf_response(html, 200)

    def test_waf_marker_forbidden(self):
        """Detecta marcador 'forbidden'."""
        client = self._create_client()

        html = "<html><body>Forbidden access</body></html>"
        assert client._is_waf_response(html, 200)

    def test_waf_marker_access_denied(self):
        """Detecta marcador 'access denied'."""
        client = self._create_client()

        html = "<html><body>Access Denied</body></html>"
        assert client._is_waf_response(html, 200)

    def test_waf_status_403(self):
        """Detecta status code 403."""
        client = self._create_client()

        html = "<html><body>OK</body></html>"
        assert client._is_waf_response(html, 403)

    def test_waf_status_429(self):
        """Detecta status code 429 (rate limit)."""
        client = self._create_client()

        html = "<html><body>OK</body></html>"
        assert client._is_waf_response(html, 429)

    def test_waf_status_503(self):
        """Detecta status code 503."""
        client = self._create_client()

        html = "<html><body>OK</body></html>"
        assert client._is_waf_response(html, 503)

    def test_legitimate_response(self):
        """No detecta WAF en respuesta legítima."""
        client = self._create_client()

        # HTML grande sin marcadores
        html = "<html><body>" + "x" * 10000 + "</body></html>"
        assert not client._is_waf_response(html, 200)

    def test_small_response_no_markers(self):
        """Respuesta pequeña sin marcadores NO es WAF."""
        client = self._create_client()

        html = "<html><body>OK</body></html>"
        assert not client._is_waf_response(html, 200)

    def test_case_insensitive(self):
        """Detección es case-insensitive."""
        client = self._create_client()

        html = "<html><body>INCIDENT_ID: 123</body></html>"
        assert client._is_waf_response(html, 200)


class TestCircuitBreaker:
    """Tests para el circuit breaker de WAFs consecutivos."""

    def _create_client(self):
        with patch("scraper_congreso.senadores.client.Session") as mock_session:
            mock_session.return_value = MagicMock()

            from scraper_congreso.senadores.client import SenadoLXVIClient

            client = SenadoLXVIClient(use_cache=False)
            return client

    def test_circuit_breaker_triggers_on_consecutive_wafs(self):
        """Lanza SessionBurnedError al alcanzar el umbral."""
        from scraper_congreso.senadores.client import SessionBurnedError

        client = self._create_client()
        waf_html = "<html><body>incident_id: 123</body></html>"

        # Primer WAF: incrementa pero no lanza
        assert client._is_waf_response(waf_html, 200)
        assert client._consecutive_wafs == 1

        # Segundo WAF: lanza SessionBurnedError
        with pytest.raises(SessionBurnedError):
            client._is_waf_response(waf_html, 200)

    def test_circuit_breaker_resets_on_valid_response(self):
        """Resetea el contador ante respuesta válida."""
        client = self._create_client()
        waf_html = "<html><body>incident_id: 123</body></html>"
        legit_html = "<html><body>" + "x" * 10000 + "</body></html>"

        # Un WAF incrementa el contador
        client._is_waf_response(waf_html, 200)
        assert client._consecutive_wafs == 1

        # Respuesta válida lo resetea
        assert not client._is_waf_response(legit_html, 200)
        assert client._consecutive_wafs == 0

    def test_reset_waf_counter(self):
        """reset_waf_counter() reinicia el contador."""
        client = self._create_client()
        client._consecutive_wafs = 5
        client.reset_waf_counter()
        assert client._consecutive_wafs == 0


class TestBackoff:
    """Tests para _backoff()."""

    def test_backoff_timing(self):
        """Verifica cálculo de backoff exponencial."""
        with patch("scraper_congreso.senadores.client.Session") as mock_session:
            mock_session.return_value = MagicMock()

            from scraper_congreso.senadores.client import SenadoLXVIClient

            client = SenadoLXVIClient(use_cache=False)

            with patch("time.sleep") as mock_sleep:
                client._backoff(0)
                mock_sleep.assert_called_with(2.0)

                client._backoff(1)
                mock_sleep.assert_called_with(4.0)

                client._backoff(2)
                mock_sleep.assert_called_with(8.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
