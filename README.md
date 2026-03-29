# Observatorio del Congreso

Análisis cuantitativo del poder legislativo mexicano a través de votaciones nominales. Construye redes de co-votación, detecta comunidades legislativas y calcula índices de poder formal (Shapley-Shubik, Banzhaf) y empírico para la Cámara de Diputados.

## Qué hace

1. **Scraping**: Descarga votaciones nominales del Sistema de Información Legislativa (SITL/INFOPAL) de la Cámara de Diputados, con caché local y manejo de reintentos.
2. **Modelado**: Almacena legisladores, partidos, votaciones y votos en SQLite con un esquema basado en el estándar [Popolo](https://www.popoloproject.com/) con extensiones para redes de poder.
3. **Análisis de redes**: Construye grafos de co-votación ponderados, detecta comunidades con Louvain, calcula centralidad y evolución temporal.
4. **Índices de poder**: Calcula Shapley-Shubik y Banzhaf para mayoría simple, calificada (2/3) y tres cuartos. También un índice de poder empírico basado en votaciones reales.
5. **NOMINATE**: Implementa análisis NOMINATE simplificado para estimar posiciones ideales de legisladores.
6. **Visualización**: Genera grafos, heatmaps, trayectorias NOMINATE y diagramas de transiciones de comunidades.

## Dataset (LXVI Legislatura)

| Métrica | Valor |
|---------|-------|
| Votaciones nominales analizadas | 199 |
| Votos individuales | 98,322 |
| Legisladores | 567 |
| Periodos legislativos | 4 |
| Partidos con bancada | 6 (Morena, PAN, PRI, PT, PVEM, MC) |

## Hallazgos clave

- **Disciplina perfecta**: La co-votación intra-partido es ≥99.74% para todos los partidos. El algoritmo Louvain detecta exactamente **2 comunidades** sin errores de clasificación.
- **Dos bloques, sin matices**: Bloque coalición (Morena + PT + PVEM) y bloque oposición (PAN + PRI + MC). No hay legisladores "swing".
- **83% del poder con 51% de escaños**: Morena concentra 83.33% del poder formal (Shapley-Shubik) en mayoría simple con 50.87% de los escaños.
- **Oposición con poder empírico 0%**: En 199 votaciones, ningún partido de oposición fue crítico para cambiar un resultado.
- **Congreso congelado**: El análisis dinámico muestra que las comunidades son idénticas entre legislaturas (ARI = 1.0). La frontera entre bloques cayó a su mínimo histórico (0.50).

## Stack tecnológico

- **Python 3.11+**
- **Scraping**: httpx, BeautifulSoup4, lxml
- **Datos**: SQLite, Pydantic (modelos), pandas
- **Análisis**: NumPy, SciPy (optimización NOMINATE), NetworkX
- **Visualización**: Matplotlib
- **Comunidades**: python-louvain (Louvain)

## Instalación

```bash
# Clonar
git clone https://github.com/cachorroink/observatorio-congreso.git
cd observatorio-congreso

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac

# Instalar dependencias
pip install -r requirements.txt
```

## Uso

```bash
# 1. Inicializar la base de datos
python -m db.init_db

# 2. Ejecutar el scraper (descarga votaciones del SITL)
python -m scraper.pipeline --leg LXVI --periodo 1

# 3. Análisis de co-votación completo
python -m analysis.run_analysis

# 4. Análisis dinámico temporal (cross-legislatura)
python -m analysis.run_covotacion_dinamica

# 5. Análisis NOMINATE
python -m analysis.run_nominate
```

> **Nota**: El scraper descarga HTML del SITL y lo cachea localmente en `cache/`. La base de datos no se incluye en el repo — se regenera con los pasos anteriores.

## Estructura del proyecto

```
├── scraper/           # Scraping del SITL/INFOPAL
│   ├── client.py      # Cliente HTTP con caché
│   ├── parsers/       # Parsers HTML por tipo de página
│   ├── pipeline.py    # Orquestador del scraping
│   └── ...
├── db/                # Modelo de datos (Popolo + redes de poder)
│   ├── schema.sql     # Esquema completo de la BD (12 tablas)
│   ├── init_db.py     # Inicialización
│   └── migrations/    # Scripts de migración históricos
├── analysis/          # Análisis cuantitativo
│   ├── covotacion.py          # Grafos de co-votación
│   ├── covotacion_dinamica.py # Evolución temporal cross-legislatura
│   ├── comunidades.py         # Detección Louvain
│   ├── poder_partidos.py      # Shapley-Shubik / Banzhaf
│   ├── poder_empirico.py      # Poder observado en votaciones reales
│   ├── nominate.py            # NOMINATE simplificado
│   ├── run_*.py               # Scripts de ejecución
│   ├── visualizacion*.py      # Generación de gráficas
│   └── output/                # Resultados (CSVs, PNGs, grafos)
├── docs/              # Artículos, análisis y metodología
│   └── metodologia/   # Fundamentos teóricos
└── data/              # Datos derivados (grafos Graphviz)
```

## Modelo de datos

El esquema `db/schema.sql` implementa 12 tablas basadas en Popolo con extensiones:

- **person**: Legisladores con metadatos (género, tipo de curul, corriente interna)
- **organization**: Partidos, bancadas, coaliciones
- **membership**: Pertenencia persona-organización con fechas
- **motion / vote_event / vote**: Iniciativas y votos individuales
- **count**: Desglose de votos por partido
- **relacion_poder**: Redes de poder informales (lealtad, presión, alianza)
- **actor_externo**: Actores fuera del Congreso (gobernadores, etc.)
- **evento_politico**: Eventos que afectan dinámicas de poder

## Fuente de datos

Los datos de votación se obtienen del Sistema de Información de Tasas y Legislación (SITL) y del sistema INFOPAL de la Cámara de Diputados:

- https://sitl.diputados.gob.mx
- https://infopal.diputados.gob.mx

## Licencia

GNU General Public License v3.0. Ver [LICENSE](LICENSE).

Los datos legislativos son públicos y provienen de fuentes oficiales del Congreso de la Unión.
