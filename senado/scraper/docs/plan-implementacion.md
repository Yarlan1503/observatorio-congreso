# Plan de Implementación: curl_cffi en Scraper del Senado

## Resumen

Migración de `httpx` a `curl_cffi` para evadir WAF Incapsula en el portal del Senado.

**Archivos afectados:**
- `requirements.txt` — agregar curl_cffi
- `cli.py` — reemplazar httpx por curl_cffi
- `scripts/test_impersonate.py` — nuevo (testing)
- `scripts/verify_curl_cffi.py` — nuevo (verificación)
- `tests/test_waf_detection.py` — nuevo (tests unitarios)

---

## Paso 1: Instalar curl_cffi

```bash
# Instalar curl_cffi
pip install curl_cffi>=0.15.0

# Verificar instalación
python senado/scraper/scripts/verify_curl_cffi.py
```

**Verificación:** Todos los checks pasan.

---

## Paso 2: Test de impersonate

```bash
# Test contra BrowserLeaks y portal del Senado
python -m senado.scraper.scripts.test_impersonate

# Test con URL específica
python -m senado.scraper.scripts.test_impersonate --url https://www.senado.gob.mx/informacion/votaciones/vota/1
```

**Verificación:**
- ✓ JA3 Hash es de Chrome
- ✓ User-Agent es Chrome
- ✓ HTML obtenido del portal (no bloqueo WAF)
- ✓ Encoding iso-8859-1 correcto

---

## Paso 3: Tests unitarios

```bash
# Ejecutar tests de detección WAF
pytest senado/scraper/tests/test_waf_detection.py -v
```

**Verificación:** Todos los tests pasan.

---

## Paso 4: Reemplazar cli.py

```bash
# Backup del archivo original
cp senado/scraper/cli.py senado/scraper/cli.py.backup

# Reemplazar con versión curl_cffi
cp senado/scraper/cli_curl_cffi.py senado/scraper/cli.py
```

**Verificación:** Código compila sin errores.

---

## Paso 5: Test con --test-id

```bash
# Test con un solo ID
python -m senado.scraper.cli --test-id 1234 --no-cache

# Verificar:
# - HTML obtenido correctamente
# - No bloqueo WAF
# - Encoding correcto (acentos, ñ)
# - Cookies guardadas en cache/senado_cookies.pkl
```

**Verificación:** Votación 1234 parseada e insertada correctamente.

---

## Paso 6: Test con rango pequeño

```bash
# Test con 10 IDs
python -m senado.scraper.cli --range 1 10 --no-cache

# Verificar:
# - Todos los IDs procesados
# - No errores de WAF
# - Rate limiting funciona (2s entre requests)
# - Backoff si hay bloqueo
```

**Verificación:** 10 votaciones procesadas sin errores.

---

## Paso 7: Test con rango completo (con caché)

```bash
# Test con caché activado
python -m senado.scraper.cli --range 1 100

# Verificar:
# - Usa caché existente
# - No hace requests innecesarios
# - Procesa correctamente
```

**Verificación:** 100 votaciones procesadas.

---

## Paso 8: Actualizar requirements.txt

```diff
 # Scraping
-httpx>=0.27
+curl_cffi>=0.15.0
 beautifulsoup4>=4.12
 lxml>=5.0
```

---

## Paso 9: Commit

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

## Rollback Plan

Si curl_cffi NO funciona:

### Escenario 1: Incapsula requiere JS challenge
```bash
# Revertir
git checkout HEAD -- senado/scraper/cli.py
git checkout HEAD -- requirements.txt

# Solución alternativa: usar Playwright
pip install playwright
playwright install chromium
```

### Escenario 2: TLS fingerprint sigue bloqueado
```bash
# Probar otro impersonate
# En cli.py cambiar:
impersonate="chrome120"  # o "edge"

# Si no funciona, revertir
git checkout HEAD -- senado/scraper/cli.py
git checkout HEAD -- requirements.txt
```

### Escenario 3: Memory crash
```bash
# Verificar que close() se llama en finally
# Si persiste, revertir
git checkout HEAD -- senado/scraper/cli.py
git checkout HEAD -- requirements.txt
```

---

## Monitoreo

### Logs a vigilar

```
# WAF detectado
WAF marker detectado: incident_id
Status code de bloqueo: 403

# Backoff
Backoff: esperando 2.0s (intento 1)
Backoff: esperando 4.0s (intento 2)

# Recreación de sesión
Recreando sesión HTTP...

# Cookies
Cookies cargadas desde disco
Cookies guardadas en disco
```

### Métricas de éxito

- ✓ Tasa de éxito > 95%
- ✓ Sin bloqueos WAF sostenidos
- ✓ Backoff < 5% de requests
- ✓ Cookies persistidas correctamente

---

## Referencias

- Documento de arquitectura: `docs/arquitectura-curl_cffi.md`
- Test de impersonate: `scripts/test_impersonate.py`
- Verificación: `scripts/verify_curl_cffi.py`
- Tests unitarios: `tests/test_waf_detection.py`
