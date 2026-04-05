# Documento de Arquitectura: Migración httpx → curl_cffi

## 1. Resumen Ejecutivo

**Qué cambia:**
- Reemplazar `httpx` por `curl_cffi` en `SenateClientWithLegacyHeaders`
- Agregar detección de WAF Incapsula
- Implementar backoff exponencial con recreación de sesión
- Persistir cookies con pickle
- Manejar encoding iso-8859-1 manualmente

**Qué NO cambia:**
- Parser `legacy.py` (no toca HTTP)
- Modelos `models.py` (no toca HTTP)
- Loader `congreso_loader.py` (no toca HTTP)
- Estructura del pipeline `SenadoCongresoPipeline`
- CLI y argumentos del script

**Impacto:** Solo `cli.py` y `requirements.txt`

---

## 2. Diagrama de Arquitectura

### Flujo Actual (httpx)
```
┌─────────────────────────────────────────────────────────┐
│ SenadoCongresoPipeline                                  │
│  └─ SenateClientWithLegacyHeaders                       │
│      └─ httpx.Client                                     │
│          ├─ headers=SENADO_LEGACY_HEADERS                │
│          ├─ timeout=30.0                                 │
│          └─ follow_redirects=True                        │
│              │                                           │
│              ▼                                           │
│      get_html(url) → response.text (UTF-8 default)      │
│              │                                           │
│              ▼                                           │
│      parse_legacy_votacion(html, id)                    │
└─────────────────────────────────────────────────────────┘
```

### Flujo Nuevo (curl_cffi)
```
┌─────────────────────────────────────────────────────────┐
│ SenadoCongresoPipeline                                  │
│  └─ SenateClientWithLegacyHeaders                       │
│      └─ curl_cffi.Session                                │
│          ├─ impersonate="chrome"                         │
│          ├─ headers=SENADO_LEGACY_HEADERS                │
│          ├─ timeout=30.0                                 │
│          └─ http_version="v1" (workaround error 92)     │
│              │                                           │
│              ▼                                           │
│      get_html(url)                                       │
│          ├─ Rate limit                                   │
│          ├─ Session.get(url)                             │
│          ├─ WAF detection (size + markers)               │
│          ├─ Backoff exponencial si WAF                   │
│          ├─ Recreación de sesión si WAF                  │
│          └─ response.content.decode('iso-8859-1')        │
│              │                                           │
│              ▼                                           │
│      parse_legacy_votacion(html, id)                    │
└─────────────────────────────────────────────────────────┘
```

### Anti-WAF Flow
```
Request → ¿WAF detectado? ─Sí─→ Backoff exponencial
    │                              │
    No                           Recrear sesión
    │                              │
    ▼                              ▼
Retornar HTML                  Reintentar (max 3)
```

---

## 3. Cambios por Archivo

### 3.1 `requirements.txt`

**Cambio:** Reemplazar `httpx` por `curl_cffi`

```diff
 # Scraping
-httpx>=0.27
+curl_cffi>=0.15.0
 beautifulsoup4>=4.12
 lxml>=5.0
```

### 3.2 `cli.py` — Cambios en `SenateClientWithLegacyHeaders`

#### 3.2.1 Imports

```diff
-import httpx
+from curl_cffi import requests as curl_requests
+from curl_cffi.requests import Session
+import pickle
```

#### 3.2.2 Constantes nuevas

```python
# =============================================================================
# Configuración anti-WAF
# =============================================================================

WAF_MARKERS = [
    "incident_id",
    "waf block",
    "forbidden",
    "access denied",
    "imperva",
    "incapsula",
    "_Incapsula_Resource",
]

WAF_MAX_SIZE = 5 * 1024  # 5KB — respuestas menores son sospechosas

COOKIE_PATH = Path(__file__).resolve().parent.parent.parent / "cache" / "senado_cookies.pkl"

MAX_RETRIES = 3
BASE_BACKOFF = 2.0  # segundos
```

#### 3.2.3 Clase `SenateClientWithLegacyHeaders` — Versión completa

```python
class SenateClientWithLegacyHeaders:
    """Cliente HTTP del Senado con headers específicos para el portal legacy.

    Portal: https://www.senado.gob.mx/informacion/votaciones/vota/{id}
    Sistema legacy (LX-LXV).

    Usa curl_cffi con impersonate="chrome" para evadir WAF Incapsula.
    """

    def __init__(
        self,
        use_cache: bool = True,
        delay: float = 2.0,
        cache_dir: Optional[Path] = None,
    ):
        """Inicializa el cliente.

        Args:
            use_cache: Si True, usa caché file-based.
            delay: Delay mínimo entre requests en segundos.
            cache_dir: Directorio de caché. Si None, usa CACHE_DIR.
        """
        self.use_cache = use_cache
        self.delay = delay
        self.cache_dir = cache_dir or CACHE_DIR
        self._last_request_time = 0.0
        self._retries = 0

        # Crear directorio de caché si es necesario
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Crear sesión con impersonate de Chrome
        self._session = self._create_session()

    def _create_session(self) -> Session:
        """Crea una nueva sesión curl_cffi con impersonate de Chrome.

        Returns:
            Sesión configurada con headers y cookies.
        """
        session = Session(
            impersonate="chrome",  # TLS fingerprint de Chrome latest
            headers=SENADO_LEGACY_HEADERS,
        )

        # Cargar cookies persistidas si existen
        if COOKIE_PATH.exists():
            try:
                with open(COOKIE_PATH, "rb") as f:
                    session.cookies.update(pickle.load(f))
                logger.debug("Cookies cargadas desde disco")
            except Exception as e:
                logger.warning(f"Error cargando cookies: {e}")

        return session

    def _save_cookies(self) -> None:
        """Persiste cookies de la sesión actual a disco."""
        try:
            COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(COOKIE_PATH, "wb") as f:
                pickle.dump(self._session.cookies, f)
            logger.debug("Cookies guardadas en disco")
        except Exception as e:
            logger.warning(f"Error guardando cookies: {e}")

    def _is_waf_response(self, html: str, status_code: int) -> bool:
        """Detecta si la respuesta es un bloqueo del WAF Incapsula.

        Criterios:
        1. Tamaño < 5KB (respuestas legítimas son más grandes)
        2. Contiene marcadores conocidos de WAF

        Args:
            html: Contenido HTML de la respuesta.
            status_code: Código HTTP de la respuesta.

        Returns:
            True si se detecta bloqueo WAF.
        """
        # Criterio 1: Tamaño sospechosamente pequeño
        if len(html) < WAF_MAX_SIZE:
            logger.warning(f"Respuesta sospechosamente pequeña: {len(html)} bytes")

        # Criterio 2: Marcadores de WAF
        html_lower = html.lower()
        for marker in WAF_MARKERS:
            if marker.lower() in html_lower:
                logger.warning(f"WAF marker detectado: {marker}")
                return True

        # Criterio 3: Status codes de bloqueo
        if status_code in (403, 406, 429, 503):
            logger.warning(f"Status code de bloqueo: {status_code}")
            return True

        return False

    def _backoff(self, attempt: int) -> None:
        """Aplica backoff exponencial.

        Args:
            attempt: Número de intento actual (0-indexed).
        """
        wait_time = BASE_BACKOFF * (2 ** attempt)
        logger.info(f"Backoff: esperando {wait_time:.1f}s (intento {attempt + 1})")
        time.sleep(wait_time)

    def _recreate_session(self) -> None:
        """Recrea la sesión HTTP (nuevo TLS handshake)."""
        logger.info("Recreando sesión HTTP...")
        try:
            self._session.close()
        except Exception:
            pass
        self._session = self._create_session()

    def _cache_path(self, url: str) -> Path:
        """Genera path SHA256 para caché de una URL."""
        h = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f"{h}.html"

    def _rate_limit(self) -> None:
        """Aplica delay mínimo entre requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def get_html(self, url: str) -> str:
        """Obtiene HTML de una URL con caché opcional y anti-WAF.

        Args:
            url: URL a fetchear.

        Returns:
            Contenido HTML como string (decodificado de iso-8859-1).

        Raises:
            RuntimeError: Si se agotan los reintentos por WAF.
            Exception: Si hay error de red no recuperable.
        """
        cache_path = self._cache_path(url)

        # Intentar leer de caché
        if self.use_cache and cache_path.exists():
            logger.debug(f"Cache hit: {url}")
            return cache_path.read_text(encoding="utf-8")

        # Fetch con rate limiting y anti-WAF
        self._rate_limit()

        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Fetching: {url} (intento {attempt + 1})")
                response = self._session.get(
                    url,
                    timeout=30.0,
                    http_version="v1",  # Workaround error 92 HTTP/2 stream 0
                )

                # Decodificar manualmente como iso-8859-1
                html = response.content.decode("iso-8859-1")

                # Verificar si es bloqueo WAF
                if self._is_waf_response(html, response.status_code):
                    if attempt < MAX_RETRIES - 1:
                        self._backoff(attempt)
                        self._recreate_session()
                        continue
                    else:
                        raise RuntimeError(
                            f"WAF bloqueó después de {MAX_RETRIES} intentos: {url}"
                        )

                # Verificar status code
                if response.status_code != 200:
                    response.raise_for_status()

                # Guardar cookies y caché
                self._save_cookies()

                if self.use_cache:
                    cache_path.write_text(html, encoding="utf-8")

                return html

            except KeyboardInterrupt:
                logger.warning("Interrumpido por usuario")
                raise
            except Exception as e:
                if "curl" in str(type(e).__name__).lower():
                    logger.error(f"Error curl_cffi: {e}")
                    if attempt < MAX_RETRIES - 1:
                        self._backoff(attempt)
                        self._recreate_session()
                        continue
                raise

        raise RuntimeError(f"Falló después de {MAX_RETRIES} intentos: {url}")

    def close(self) -> None:
        """Cierra la sesión HTTP y persiste cookies."""
        self._save_cookies()
        try:
            self._session.close()
        except Exception as e:
            logger.warning(f"Error cerrando sesión: {e}")
```

---

## 4. Anti-WAF Strategy

### 4.1 Configuración de Session

```python
session = Session(
    impersonate="chrome",  # TLS fingerprint de Chrome latest
    headers=SENADO_LEGACY_HEADERS,
)
```

**Por qué funciona:**
- `impersonate="chrome"` replica el TLS fingerprint de Chrome
- Incapsula confía en el fingerprint y no bloquea
- Headers adicionales (User-Agent, Accept, etc.) son consistentes

### 4.2 WAF Detection

**Criterios de detección:**
1. **Tamaño < 5KB**: Respuestas legítimas del portal son más grandes
2. **Marcadores conocidos**: `incident_id`, `waf block`, `forbidden`, etc.
3. **Status codes**: 403, 406, 429, 503

### 4.3 Backoff Exponencial

```python
wait_time = BASE_BACKOFF * (2 ** attempt)
# Intento 0: 2s
# Intento 1: 4s
# Intento 2: 8s
```

### 4.4 Recreación de Sesión

Al detectar WAF:
1. Cerrar sesión actual
2. Crear nueva sesión (nuevo TLS handshake)
3. Reintentar con backoff

### 4.5 Cookie Persistence

```python
# Guardar después de cada request exitoso
with open(COOKIE_PATH, "wb") as f:
    pickle.dump(session.cookies, f)

# Cargar al crear sesión
if COOKIE_PATH.exists():
    with open(COOKIE_PATH, "rb") as f:
        session.cookies.update(pickle.load(f))
```

### 4.6 HTTP/1.1 Workaround

```python
response = self._session.get(
    url,
    http_version="v1",  # Evita error 92 HTTP/2 stream 0
)
```

---

## 5. Error Handling

### 5.1 Exceptions a Capturar

| Exception | Causa | Acción |
|-----------|-------|--------|
| `KeyboardInterrupt` | Usuario interrumpe | Re-raise inmediatamente |
| `CurlError` | Error de red curl_cffi | Backoff + recrear sesión |
| `RuntimeError` | WAF bloqueó | Backoff + recrear sesión |
| `Exception` | Otro error | Re-raise |

### 5.2 Manejo de WAF

```python
if self._is_waf_response(html, response.status_code):
    if attempt < MAX_RETRIES - 1:
        self._backoff(attempt)
        self._recreate_session()
        continue
    else:
        raise RuntimeError(f"WAF bloqueó después de {MAX_RETRIES} intentos")
```

### 5.3 Manejo de Encoding

```python
# NO usar response.text (asume UTF-8)
# SI usar response.content.decode('iso-8859-1')
html = response.content.decode("iso-8859-1")
```

### 5.4 Session Lifecycle

```python
# En finally de scrape_range o main
try:
    # ... scraping ...
finally:
    client.close()  # Guarda cookies y cierra sesión
```

---

## 6. Testing Plan

### 6.1 Verificar impersonate funciona

```python
# test_impersonate.py
from curl_cffi.requests import Session

def test_chrome_impersonate():
    """Verifica que el TLS fingerprint sea de Chrome."""
    session = Session(impersonate="chrome")
    response = session.get("https://tls.browserleaks.com/json")
    data = response.json()
    
    # Verificar que el JA3 hash sea de Chrome
    assert "ja3_hash" in data
    print(f"JA3 Hash: {data['ja3_hash']}")
    
    # Verificar User-Agent
    assert "Chrome" in data.get("user_agent", "")
    print(f"User-Agent: {data['user_agent']}")
```

### 6.2 Test contra portal real

```python
# test_senado_real.py
from senado.scraper.cli import SenateClientWithLegacyHeaders

def test_fetch_real_page():
    """Fetch real del portal del Senado."""
    client = SenateClientWithLegacyHeaders(use_cache=False, delay=1.0)
    
    try:
        # ID 1234 es una votación conocida
        html = client.get_html("https://www.senado.gob.mx/informacion/votaciones/vota/1234")
        
        # Verificar que no es bloqueo WAF
        assert len(html) > 5000, f"HTML muy corto: {len(html)} bytes"
        assert "incident_id" not in html.lower()
        assert "waf block" not in html.lower()
        
        # Verificar encoding
        assert "VOTACIONES" in html or "votaciones" in html.lower()
        
        print(f"✓ HTML obtenido: {len(html)} bytes")
        
    finally:
        client.close()
```

### 6.3 Tests unitarios

```python
# test_waf_detection.py
import pytest
from senado.scraper.cli import SenateClientWithLegacyHeaders

def test_waf_detection_markers():
    """Detecta marcadores de WAF."""
    client = SenateClientWithLegacyHeaders(use_cache=False)
    
    # HTML con marcador de WAF
    waf_html = "<html><body>incident_id: 12345</body></html>"
    assert client._is_waf_response(waf_html, 200) == True
    
    # HTML legítimo
    legit_html = "<html><body>" + "x" * 10000 + "</body></html>"
    assert client._is_waf_response(legit_html, 200) == False

def test_waf_detection_size():
    """Detecta respuestas sospechosamente pequeñas."""
    client = SenateClientWithLegacyHeaders(use_cache=False)
    
    # HTML muy pequeño (sin marcadores)
    small_html = "<html><body>OK</body></html>"
    # No debe marcar como WAF solo por tamaño (solo warning)
    assert client._is_waf_response(small_html, 200) == False

def test_waf_detection_status():
    """Detecta status codes de bloqueo."""
    client = SenateClientWithLegacyHeaders(use_cache=False)
    
    assert client._is_waf_response("<html></html>", 403) == True
    assert client._is_waf_response("<html></html>", 429) == True
    assert client._is_waf_response("<html></html>", 200) == False
```

### 6.4 Test de encoding

```python
# test_encoding.py
def test_iso_8859_1_encoding():
    """Verifica decodificación correcta de iso-8859-1."""
    from senado.scraper.cli import SenateClientWithLegacyHeaders
    
    client = SenateClientWithLegacyHeaders(use_cache=False)
    
    try:
        html = client.get_html("https://www.senado.gob.mx/informacion/votaciones/vota/1")
        
        # Verificar caracteres especiales (acentos, ñ)
        # El portal usa iso-8859-1 que tiene estos caracteres
        assert "VOTACI" in html.upper()  # VOTACIONES o VOTACIÓN
        
    finally:
        client.close()
```

---

## 7. Implementación Paso a Paso

### Paso 1: Agregar curl_cffi a requirements.txt

```bash
# Editar requirements.txt
# Reemplazar httpx>=0.27 por curl_cffi>=0.15.0

# Instalar
pip install curl_cffi>=0.15.0

# Verificar
python -c "from curl_cffi.requests import Session; print('OK')"
```

**Verificación:** Import exitoso sin errores.

### Paso 2: Crear función de detección WAF

```bash
# Agregar a cli.py:
# - Constantes WAF_MARKERS, WAF_MAX_SIZE, COOKIE_PATH, MAX_RETRIES, BASE_BACKOFF
# - Método _is_waf_response()

# Test unitario
pytest tests/test_waf_detection.py -v
```

**Verificación:** Tests pasan.

### Paso 3: Refactorizar SenateClientWithLegacyHeaders

```bash
# Reemplazar httpx.Client por curl_cffi.Session
# Agregar métodos:
# - _create_session()
# - _save_cookies()
# - _backoff()
# - _recreate_session()

# Modificar get_html():
# - Agregar loop de reintentos
# - Decodificar iso-8859-1
# - Detectar WAF
# - Backoff exponencial
```

**Verificación:** Código compila sin errores.

### Paso 4: Test contra portal real

```bash
# Ejecutar test manual
python -m senado.scraper.cli --test-id 1234 --no-cache

# Verificar:
# - HTML obtenido correctamente
# - No bloqueo WAF
# - Encoding correcto (acentos, ñ)
# - Cookies guardadas
```

**Verificación:** Votación 1234 parseada correctamente.

### Paso 5: Test de rango pequeño

```bash
# Test con rango pequeño (10 IDs)
python -m senado.scraper.cli --range 1 10 --no-cache

# Verificar:
# - Todos los IDs procesados
# - No errores de WAF
# - Rate limiting funciona
# - Backoff si hay bloqueo
```

**Verificación:** 10 votaciones procesadas sin errores.

### Paso 6: Test de rango completo (dry-run)

```bash
# Test con caché activado (no hace requests reales si ya hay caché)
python -m senado.scraper.cli --range 1 100

# Verificar:
# - Usa caché existente
# - No hace requests innecesarios
# - Procesa correctamente
```

**Verificación:** 100 votaciones procesadas.

### Paso 7: Commit y documentación

```bash
git add -A
git commit -m "feat: migrar scraper Senado de httpx a curl_cffi

- Reemplaza httpx por curl_cffi con impersonate='chrome'
- Agrega detección de WAF Incapsula
- Implementa backoff exponencial con recreación de sesión
- Persiste cookies con pickle
- Maneja encoding iso-8859-1 manualmente
- Workaround HTTP/1.1 para error 92

Fixes: bloqueo WAF Incapsula en portal del Senado"
```

---

## 8. Rollback Plan

### Si curl_cffi NO funciona

**Escenario 1: Incapsula requiere JS challenge**
- curl_cffi no ejecuta JavaScript
- **Solución:** Usar Playwright/Selenium como complemento
- **Rollback:** Revertir a httpx + agregar Playwright para obtener cookies

**Escenario 2: TLS fingerprint sigue bloqueado**
- Incapsula detecta curl_cffi a pesar de impersonate
- **Solución:** Probar `impersonate="chrome120"` o `impersonate="edge"`
- **Rollback:** Revertir a httpx y probar con proxy rotativo

**Escenario 3: Memory crash con retries**
- curl_cffi tiene memory leak con stream + retry
- **Solución:** Cerrar sesión en finally (ya implementado)
- **Rollback:** Revertir a httpx y agregar delay más largo

### Comando de rollback

```bash
# Revertir cambios
git checkout HEAD -- senado/scraper/cli.py
git checkout HEAD -- requirements.txt

# Reinstalar httpx
pip install httpx>=0.27

# Verificar
python -m senado.scraper.cli --test-id 1234
```

---

## 9. Decisiones a Persistir

### 9.1 Entidades en Knowledge Graph

```
Entidad: curl_cffi
  Tipo: library
  Observaciones:
    - v0.15.0+ soporta impersonate="chrome"
    - No soporta files= de requests → usar CurlMime()
    - No tiene response.history
    - User-Agent default es macOS → override manual
    - Error 92 HTTP/2 stream 0 → http_version="v1"
    - No ejecuta JavaScript
    - Encoding iso-8859-1 → response.content.decode('iso-8859-1')
    - KeyboardInterrupt genera CurlError → capturar ambas
    - Memory crash con stream + retry → cerrar en finally

Entidad: Incapsula WAF
  Tipo: security
  Observaciones:
    - Bloquea requests sin TLS fingerprint de navegador
    - Detección: tamaño <5KB + marcadores
    - Marcadores: incident_id, waf block, forbidden, access denied, imperva
    - Status codes de bloqueo: 403, 406, 429, 503
    - Requiere cookies para bypass
    - Puede requerir JS challenge (no soportado por curl_cffi)

Entidad: Senado Scraper
  Tipo: project
  Observaciones:
    - Portal: https://www.senado.gob.mx/informacion/votaciones/vota/{id}
    - Rango IDs: 1 a 4690
    - Encoding: iso-8859-1
    - Headers legacy: User-Agent, Accept, Accept-Language, Referer
    - Rate limiting: 2s entre requests
    - Caché file-based con SHA256
```

### 9.2 Relaciones sugeridas

```
Senado Scraper —[usa]→ curl_cffi
Senado Scraper —[protegido_por]→ Incapsula WAF
curl_cffi —[impersona]→ Chrome TLS
```

---

## 10. Referencias

- curl_cffi docs: https://curl-cffi.readthedocs.io/
- Impersonate: https://curl-cffi.readthedocs.io/en/latest/impersonate.html
- Gotchas: Documento interno `dom-curl_cffi` (si existe)
- Portal Senado: https://www.senado.gob.mx/informacion/votaciones/
