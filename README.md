# Observatorio del Congreso

Análisis cuantitativo del poder legislativo mexicano — Cámara de Diputados y Senado de la República. Scraping sistemático, modelado Popolo-Graph, análisis de redes de co-votación, detección de comunidades e índices de poder formal y empírico.

## Qué hace

1. **Scraping**: Descarga votaciones nominales y perfiles legislativos del SITL/INFOPAL (Diputados) y del sitio del Senado, con caché local, manejo de reintentos y evasión de WAF.
2. **Modelado**: Almacena legisladores, partidos, votaciones y votos en SQLite con un esquema basado en el estándar [Popolo](https://www.popoloproject.com/) con extensiones para redes de poder.
3. **Análisis de redes**: Construye grafos de co-votación ponderados, detecta comunidades con Louvain, calcula centralidad y evolución temporal.
4. **Índices de poder**: Calcula Shapley-Shubik y Banzhaf para mayoría simple, calificada (2/3) y tres cuartos. También un índice de poder empírico basado en votaciones reales.
5. **NOMINATE**: Implementa análisis NOMINATE simplificado para estimar posiciones ideales de legisladores.
6. **Visualización**: Genera grafos, heatmaps, trayectorias NOMINATE y diagramas de transiciones de comunidades.

## Dataset

| Métrica | Valor |
|---------|-------|
| Votos individuales | ~3.5M |
| Votaciones nominales | ~9,400 |
| Personas | ~4,800 |
| Legislaturas cubiertas | LX–LXVI (7 legislaturas) |
| Cámaras | Diputados + Senado |

### Hallazgos clave (LXVI Legislatura)

Los primeros análisis sobre la LXVI Legislatura revelan patrones extremos:

- **Disciplina perfecta**: La co-votación intra-partido es ≥99.74% para todos los partidos. El algoritmo Louvain detecta exactamente **2 comunidades** sin errores de clasificación.
- **Dos bloques, sin matices**: Bloque coalición (Morena + PT + PVEM) y bloque oposición (PAN + PRI + MC). No hay legisladores "swing".
- **83% del poder con 51% de escaños**: Morena concentra 83.33% del poder formal (Shapley-Shubik) en mayoría simple con 50.87% de los escaños.
- **Oposición con poder empírico 0%**: En las votaciones analizadas, ningún partido de oposición fue crítico para cambiar un resultado.
- **Congreso congelado**: El análisis dinámico muestra comunidades idénticas entre periodos (ARI = 1.0). La frontera entre bloques cayó a su mínimo histórico (0.50).

El dataset completo (7 legislaturas, ambas cámaras) permite contrastar estos hallazgos con legislaturas anteriores donde la dinámica de poder fue diferente.

## Stack tecnológico

| Capa | Herramientas |
|------|-------------|
| **Runtime** | Python 3.12+ |
| **Scraping** | curl_cffi (Senado, evasión WAF), httpx (Diputados), BeautifulSoup4, lxml |
| **Datos** | SQLite (WAL mode), Pydantic v2 |
| **Análisis** | NumPy, SciPy, NetworkX, pandas, polars |
| **Comunidades** | NetworkX (nx.community.louvain) |
| **Visualización** | Matplotlib |
| **Gestor de paquetes** | [uv](https://docs.astral.sh/uv/) (uv.lock) |
| **Linter** | ruff |
| **Tests** | pytest |

## Instalación

```bash
git clone https://github.com/cachorroink/observatorio-congreso.git
cd observatorio-congreso
uv sync
```

Para dependencias de análisis:

```bash
uv sync --group analysis
```

## Uso

```bash
# Diputados — scrape por legislatura
python -m scraper_congreso.diputados --leg LXVI --periodo 1
python -m scraper_congreso.diputados --leg LXVI --all-periods
python -m scraper_congreso.diputados --stats

# Senado — votaciones
python -m scraper_congreso.senadores.votaciones --range 1 5070
python -m scraper_congreso.senadores.votaciones --stats

# Senado — perfiles
python -m scraper_congreso.senadores.perfiles --from-listing
python -m scraper_congreso.senadores.perfiles --range 1 1754 --delay 2.0

# Scripts de operación
bash scripts/scrape_diputados_all.sh          # Todas las legislaturas
bash scripts/backup_db.sh                      # Backup con rotación
```

> **Nota**: El scraper descarga HTML y lo cachea localmente en `cache/` (nombres SHA256, ~600MB). La base de datos no se incluye en el repo — se regenera con los pasos anteriores.

## Estructura del proyecto

```
├── scraper_congreso/         # Paquete scraper principal
│   ├── diputados/            # Scraper Cámara de Diputados (httpx + SITL)
│   │   ├── client.py
│   │   ├── pipeline.py       # Orquestador + CLI
│   │   ├── transformers.py
│   │   ├── loader.py
│   │   ├── parsers/
│   │   └── legislatura.py
│   ├── senadores/            # Scraper Senado (curl_cffi + WAF)
│   │   ├── client.py
│   │   ├── config.py
│   │   ├── votaciones/       # Votaciones nominales
│   │   │   ├── cli.py        # CLI principal
│   │   │   ├── loader.py
│   │   │   ├── transformers.py
│   │   │   └── parsers/
│   │   └── perfiles/         # Perfiles de senadores
│   │       ├── scraper.py    # CLI principal
│   │       └── parsers/
│   └── utils/                # Utilidades compartidas
│       ├── db_helpers.py
│       ├── db_utils.py
│       ├── id_generator.py
│       └── text_utils.py
├── db/                       # BD + schema Popolo-Graph
│   ├── congreso.db           # SQLite (~336MB)
│   ├── schema.sql            # Schema completo (12 tablas)
│   ├── backups/              # Backups automáticos
│   ├── constants.py          # Constantes del schema
│   └── migrations/           # Scripts de migración históricos
├── analysis/                 # Análisis cuantitativo (exploratorio)
├── tests/                    # Tests (scraping + validación)
├── scripts/                  # Shell scripts de operación
│   ├── backup_db.sh
│   ├── scrape_diputados_all.sh
│   ├── scrape_senado_votaciones.sh
│   ├── scrape_senado_perfiles.sh
│   └── run_backfill_fichas.sh
├── cache/                    # Cache HTML (SHA256 filenames, ~604MB)
├── logs/                     # Logs con rotación
├── docs/                     # Metodología y artículos
├── pyproject.toml            # Config del proyecto + ruff + pytest
└── uv.lock
```

## Modelo de datos

El esquema `db/schema.sql` implementa 12 tablas basadas en el estándar Popolo con extensiones para análisis de poder:

| Tabla | Descripción |
|-------|-------------|
| `area` | Divisiones geográficas (estados, distritos, circunscripciones) |
| `person` | Legisladores con metadatos (género, tipo de curul, corriente interna) |
| `organization` | Partidos, bancadas, coaliciones |
| `membership` | Pertenencia persona-organización con fechas |
| `post` | Cargos y curules |
| `motion` | Iniciativas y asuntos legislativos |
| `vote_event` | Votaciones nominales (sesión, resultado, quórum) |
| `vote` | Votos individuales (a favor, en contra, abstención, ausente) |
| `count` | Desglose de votos por partido |
| `relacion_poder` | Redes de poder informales (lealtad, presión, alianza) |
| `actor_externo` | Actores fuera del Congreso (gobernadores, etc.) |
| `evento_politico` | Eventos que afectan dinámicas de poder |

Convenciones del schema:
- IDs legibles con prefijos (A01, O01, P01, AE01, etc.)
- Fechas en formato ISO 8601 (YYYY-MM-DD)
- Foreign keys habilitadas, WAL mode, UTF-8

## Tests

```bash
uv run pytest tests/ -v
```

Los tests cubren transformers de Diputados y Senado, validación de scraping, schema de la base de datos y utilidades.

## Fuentes de datos

- **Cámara de Diputados**: [SITL](https://sitl.diputados.gob.mx) / [INFOPAL](https://infopal.diputados.gob.mx)
- **Senado de la República**: [Senado](https://www.senado.gob.mx)

Los datos legislativos son públicos y provienen de fuentes oficiales del Congreso de la Unión.

## Licencia

GNU General Public License v3.0. Ver [LICENSE](LICENSE).
