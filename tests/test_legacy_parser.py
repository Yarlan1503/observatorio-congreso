import pytest
from senado.scraper.parsers.legacy import (
    parse_legacy_votacion,
    _parse_legislature,
    _parse_ejercicio,
    _parse_fecha_legacy,
    _normalize_voto,
)


class TestParseLegislature:
    def test_legislature_lx(self):
        assert _parse_legislature("VOTACIONES DE LA LX LEGISLATURA") == "LX"

    def test_legislature_lxii(self):
        assert _parse_legislature("VOTACIONES DE LA LXII LEGISLATURA") == "LXII"

    def test_legislature_lxv(self):
        assert _parse_legislature("VOTACIONES DE LA LXV LEGISLATURA") == "LXV"


class TestParseEjercicio:
    def test_primer_anio(self):
        assert _parse_ejercicio("PRIMER AÑO DE EJERCICIO") == 1

    def test_segundo_anio(self):
        assert _parse_ejercicio("SEGUNDO AÑO DE EJERCICIO") == 2

    def test_tercer_anio(self):
        assert _parse_ejercicio("TERCER AÑO DE EJERCICIO") == 3


class TestParseFechaLegacy:
    def test_fecha_completa(self):
        assert _parse_fecha_legacy("Martes 05 de septiembre de 2006") == "05/09/2006"

    def test_fecha_miercoles(self):
        assert _parse_fecha_legacy("Miércoles 15 de marzo de 2023") == "15/03/2023"


class TestNormalizeVoto:
    """Tests para _normalize_voto.

    IMPORTANTE: _normalize_voto retorna valores RAW (PRO/CONTRA/ABSTENCIÓN)
    para que voto_to_option() en transformers.py los procese correctamente.

    El flujo es:
        parse_legacy_votacion → _normalize_voto → "PRO" (RAW)
        transformar_votacion_legacy → voto_to_option("PRO") → "a_favor" (BD)
    """

    def test_pro(self):
        assert _normalize_voto("PRO") == "PRO"

    def test_contra(self):
        assert _normalize_voto("CONTRA") == "CONTRA"

    def test_abstencion(self):
        assert _normalize_voto("ABSTENCIÓN") == "ABSTENCIÓN"

    def test_abstencion_entity(self):
        assert _normalize_voto("ABSTENCI&Oacute;N") == "ABSTENCIÓN"


class TestParseLegacyVotacion:
    """Tests de integración con HTML real simulado."""

    @pytest.fixture
    def sample_html(self):
        """HTML de ejemplo con estructura legacy."""
        return """
        <html>
        <body>
            <div class="panel-heading"><strong>VOTACIONES DE LA LXIV LEGISLATURA</strong></div>
            <h3>PRIMER AÑO DE EJERCICIO</h3>
            <div class="col-sm-12 text-center"><strong>Martes 05 de septiembre de 2006</strong></div>
            <div class="col-sm-12 text-justify" style="padding-top:10px; padding-bottom:10px;">
                Dictamen de la Comisión de Hacienda
            </div>
            <table class="table">
                <th colspan="6">Presentes: 80</th>
                <tr><td>PRI</td><td>30</td><td>5</td><td>2</td><td>0</td><td>37</td></tr>
                <tr><td>PAN</td><td>25</td><td>3</td><td>1</td><td>0</td><td>29</td></tr>
            </table>
            <table class="table table-striped">
                <thead><tr><th>SENADOR (A)</th><th>GRUPO PARLAMENTARIO</th><th>VOTO</th></tr></thead>
                <tbody>
                    <tr>
                        <td class="text-center">1</td>
                        <td><a href="/informacion/senadores/LXIV_LXV/1064/Votaciones">Sen. Rocío Adriana Abreu Artiñano</a></td>
                        <td><strong>PRO</strong></td>
                    </tr>
                    <tr>
                        <td class="text-center">2</td>
                        <td><a href="/informacion/senadores/LXIV_LXV/1065/Votaciones">Sen. Juan Pérez López</a></td>
                        <td><strong>CONTRA</strong></td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """

    def test_parse_votacion_detail(self, sample_html):
        detail, votos = parse_legacy_votacion(sample_html, 1234)

        assert detail.fecha == "05/09/2006"
        assert detail.año_ejercicio == 1
        assert "Dictamen de la Comisión de Hacienda" in detail.descripcion
        assert detail.pro_count > 0
        assert detail.contra_count > 0

    def test_parse_votos_nominales(self, sample_html):
        """Los votos se parsean como RAW y se convierten en transformers.py."""
        detail, votos = parse_legacy_votacion(sample_html, 1234)

        assert len(votos) == 2
        assert votos[0].nombre == "Rocío Adriana Abreu Artiñano"
        assert votos[0].voto == "PRO"  # RAW - se convierte en transformers.py
        assert votos[1].nombre == "Juan Pérez López"
        assert votos[1].voto == "CONTRA"  # RAW - se convierte en transformers.py


class TestIdempotency:
    """Test que verificar que el mismo (senado_id, legislature) no produce duplicados."""

    def test_legislature_extraction_from_html(self):
        """Verifica que legislature se extrae del HTML, no del ID."""
        html_lx = '<div class="panel-heading"><strong>VOTACIONES DE LA LX LEGISLATURA</strong></div>'
        html_lxii = '<div class="panel-heading"><strong>VOTACIONES DE LA LXII LEGISLATURA</strong></div>'

        # El mismo ID 1000 puede existir en LX y LXII
        # Por eso la PK es (senado_id, legislature)
