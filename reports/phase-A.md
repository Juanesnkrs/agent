# Fase A — scraper de Pinnacle del repo original, tal cual

Fecha: 2026-11-02
Rama: `feat/scrapers`

## Objetivo

Clonar `nba-surebets`, ejecutar su demo y sus tests, y probar su scraper de
Pinnacle **sin modificarlo**, dejando registro de qué funciona y qué falla.

## Hecho

- Clon en `%TEMP%\opencode\nba-surebets`, commit `4e90b26`.
- `pip install -e ".[dev,scrape]"` en venv aparte (Python 3.14.6).
- `python -m surebets.demo`: **4 arbitrajes**, salida coherente con el README.
- `pytest -q`: **24 passed**.
- `scrape("nba", 60)` tal cual: falla con `NoSuchDriverException` porque
  `CHROMEDRIVER_PATH` apunta a un binario Linux que no existe.
- Repetido con un chromedriver real de Selenium Manager (solo variable de
  entorno, código intacto): falla con `net::ERR_CONNECTION_RESET`.
- Confirmado con `curl` y con Chrome: `www.pinnacle.com` resetea la conexión
  desde esta red. Es un bloqueo externo, no del código.
- Revisión estática de `scraper.py`, `parsing.py`, `browser.py`, `config.py` y
  `markets.py`.

## Resultado

| Elemento | Estado |
|---|---|
| Demo / matemática | Funciona |
| Tests originales | 24/24 |
| Scraper Pinnacle en Windows | Falla (driver Linux hardcodeado) |
| Scraper Pinnacle con driver válido | Falla (red bloqueada) |
| Parsing puro de bloques de texto | Reutilizable |
| Selectores CSS Modules | No verificables; frágiles por diseño |

Detalle completo en [`scrapers-asis.md`](scrapers-asis.md).

## Consecuencias para la Fase B

1. No se puede portar el scraper "según funciona": no se pudo ejecutar contra la
   página real. Se porta la parte verificable (parsing y normalización) y se
   aísla el acceso a red detrás de una interfaz con fixtures.
2. El proveedor nuevo debe exponer `start_time` y `captured_at`, que el original
   no produce.
3. No se debe afirmar que el scraping de Pinnacle funciona hasta probarlo en una
   red donde el sitio responda.

## Tests y lint del proyecto

- `pytest -q`: 78 passed (scaffold heredado: modelos, proveedores manual/mock y
  guardas de arquitectura).
- `ruff check .`: All checks passed.
