# Scrapers de `nba-surebets` tal cual — Fase A

Fecha: 2026-11-02
Repositorio: https://github.com/fernando-cortes-tejada/nba-surebets
Commit probado: `4e90b26` ("Docs: execution was automated; note the execution bot is not in this repo")
Clon: `C:\Users\JuaneSnkrs\AppData\Local\Temp\opencode\nba-surebets`
Entorno: Windows 11, Python 3.14.6, Chrome 156, Selenium 4.52, pandas 3.1.0.
Red: Bogotá, sin VPN ni proxies.

## Qué se ejecutó

| Prueba | Comando | Resultado |
|---|---|---|
| Instalación | `pip install -e ".[dev,scrape]"` | OK |
| Demo | `python -m surebets.demo` | **OK**: 11 + 11 cuotas, 4 arbitrajes |
| Tests | `pytest -q` | **OK**: 24 passed en 1.63 s |
| Scraper Pinnacle tal cual | `python -c "from surebets.books.pinnacle.scraper import scrape; scrape('nba', 60)"` | **Falla** antes de abrir el navegador |
| Scraper con driver válido | misma llamada con `CHROMEDRIVER_PATH` apuntando al driver de Selenium Manager | **Falla** al navegar: `net::ERR_CONNECTION_RESET` |
| Comprobación de red independiente | `curl https://www.pinnacle.com/es/basketball/nba/matchups` | `curl: (35) Recv failure: Connection was reset` |
| Comprobación con navegador real | abrir la misma URL en Chrome | `ERR_CONNECTION_CLOSED (-100)` |

## Qué funciona

1. **La demo y la matemática del repositorio original funcionan** en Python 3.14:
   encuentra 4 arbitrajes en los CSV de ejemplo, con stakes y beneficio bloqueado.
   La salida coincide con el README (+1.96 %, +1.57 %, +0.86 %, +0.57 %).
2. **La suite original pasa entera** (24 tests) sin cambios.
3. **Las funciones de parsing son reutilizables de forma aislada.** `data_winner`,
   `data_handicap`, `data_total`, `data_total_team` y `data_players` convierten
   bloques de texto de la página en diccionarios con `website, game, market, line,
   more, less`. No dependen de Selenium para ejecutarse, solo reciben `list[str]`.
4. **El diccionario de equipos NBA** (`surebets/markets.py`) está completo para las
   30 franquicias y sus abreviaturas.

## Qué falla y por qué

### 1. Driver inexistente y dependiente de Linux (bloqueante en Windows)

`initiate_driver()` usa `Service(CHROMEDRIVER_PATH)` y el valor por defecto es
`src/execs/chromedriver-linux64/chromedriver`, una ruta relativa que no existe en
este clon ni en Windows. Resultado exacto:

```text
ValueError: The path is not a valid file: src/execs/chromedriver-linux64/chromedriver
selenium.common.exceptions.NoSuchDriverException
```

No hay fallback a Selenium Manager. El repositorio asume Linux/Docker y un
chromedriver empaquetado que **no está versionado** en el repo.

### 2. Pinnacle no es accesible desde esta red (bloqueante externo)

Aun corrigiendo el driver por variable de entorno (sin tocar el código), Chrome
no puede cargar la página:

```text
selenium.common.exceptions.WebDriverException: Message: unknown error: net::ERR_CONNECTION_RESET
```

`curl` recibe el mismo reset TLS en ~0,08 s y el navegador real devuelve
`ERR_CONNECTION_CLOSED`. El DNS resuelve `www.pinnacle.com` a Cloudflare
(172.64.145.56 / 104.18.42.200). Es un bloqueo de red/región, no un fallo del
scraper. **No se intentó evadir** con proxies, otras IPs ni cabeceras especiales.

Consecuencia: no se pudo verificar si los selectores CSS siguen vigentes.

### 3. Selectores frágiles de CSS Modules

El scraper depende de nombres de clase con hash generados por el bundler:

```text
contentBlock.square
style_filterBarContent__1Oe4N
style_button__3zn2w
style_primary__uMCOh.style_marketGroup__rIPR4
style_toggleMarkets__2IYz8
style_metadata__3MrIC
style_liveStatus__2pXfr
```

Cualquier despliegue de Pinnacle cambia esos hashes y el scraper deja de encontrar
la lista de partidos, los carruseles o las tablas. El propio README avisa que los
scrapers "break whenever a site changes its markup" y que no se mantienen.

### 4. Dependencia del idioma y de la estructura de URL

- URL fija `https://www.pinnacle.com/es/basketball/nba/matchups` y etiquetas de
  mercado en español ("Línea de dinero – Partido", "Hándicap – Partido", ...).
- `game_name = game.split("/")[-3]` y `game_name.split("vs")` asumen la forma
  `/es/basketball/nba/<equipo>-vs-<equipo>/<id>`.
- Si Pinnacle cambia el orden de la URL, el mercado o el idioma, el scraping
  devuelve datos vacíos o mal etiquetados sin lanzar error.

### 5. Sin los campos que exige el detector nuevo

La salida es un `DataFrame` con `website, game, market, team, player, line, more,
less`. **No incluye `start_time` ni `captured_at`**, no distingue prematch de live
salvo por un filtro best-effort de `LiveContainer`, y no tiene reintentos ni
espera configurable. Tampoco aplica ritmo conservador: abre un `driver.get()` por
cada partido y hace clic en cada carrusel de forma secuencial.

### 6. Errores silenciosos

`scrape()` envuelve todo en `try/except Exception` y solo imprime el error. Un
fallo de red o de DOM se convierte en un DataFrame vacío, indistinguible de "no
hay partidos".

## Veredicto

- **Ejecutable tal cual:** demo y tests, sí.
- **Scraper de Pinnacle tal cual:** **no**. Falla primero por el driver Linux y,
  corregido eso, por el bloqueo de red a `pinnacle.com` desde esta conexión.
- **Reutilizable para la Fase B:** la matemática, el diccionario de equipos y las
  funciones puras de parsing de texto. Los selectores y el arranque del navegador
  hay que reescribirlos.
- **No verificado:** si el DOM actual de Pinnacle conserva las clases y etiquetas
  que espera el scraper. No se puede afirmar que funcione en otra red sin probarlo.
