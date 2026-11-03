# Fase B — proveedor de Pinnacle

Fecha: 2026-11-02
Rama: `feat/scrapers`

## Objetivo

Portar al paquete `surebets/` lo que funcione del scraper de Pinnacle, con el
scraper como `OddsProvider`, y aislar lo que no se pudo verificar.

## Qué se portó

| Pieza original | Destino | Estado |
|---|---|---|
| `markets.py` (equipos NBA) | `surebets/normalize.py` | Portado y ampliado (alias + acentos) |
| `parsing.py` (bloques de texto) | `surebets/providers/pinnacle.py` | Portado con tests offline |
| `browser.py` (Selenium) | `SeleniumPinnacleSource` | Adaptado, **no verificable en esta red** |
| `scraper.py` (recorrido de la página) | `SeleniumPinnacleSource` | Adaptado, **no verificable** |
| `DataFrame` de salida | `list[OddsQuote]` | Nuevo modelo con `start_time` y `captured_at` |

## Diseño

- `PinnacleProvider(source=...)` implementa `OddsProvider` y devuelve
  `list[OddsQuote]`; no devuelve DataFrames.
- El acceso a la página está detrás de `PinnacleSource` (`load_games` +
  `load_blocks`). Los tests usan una fuente falsa, así que la lógica se prueba
  sin red ni navegador.
- `parse_block` reconoce `moneyline`, `handicap`, `total`, `team_total` y props
  de jugador (`player_points`, `player_rebounds`, ...).
- Se descartan los mercados de 1.ª parte y de cuartos: el detector es prematch
  de partido completo.
- Cada cuota lleva `captured_at` del momento de la captura y `start_time` del
  evento.
- Un 403/429, captcha o página de cumplimiento lanza `ProviderBlockedError` y
  **no se reintenta**. El llamador debe dejar de usar Pinnacle en esa pasada.

## Acceso a red

`PoliteFetcher` (en `surebets/net.py`) implementa:

- mínimo 5 minutos entre peticiones por casa (configurable), con jitter;
- timeout de 30 s;
- máximo 2 reintentos con espera creciente (2 s, 4 s);
- 403/429/captcha: bloqueo inmediato, sin reintento;
- 5xx/timeout: reintento acotado y luego `ProviderUnavailableError`.

Todavía no lo usa Pinnacle (Selenium navega directamente); sí lo usará BetPlay.

## Tests

- `tests/test_pinnacle.py`: 8 tests de parsing y del proveedor.
- `tests/test_net.py`: 8 tests de ritmo, reintentos y bloqueos.
- `tests/test_normalize.py`: 18 tests de equipos, mercados y selecciones.
- Suite completa: **122 passed**.
- `ruff check .`: **All checks passed**.

## Qué falla / no se pudo verificar

- **Pinnacle sigue inaccesible desde esta red.** `www.pinnacle.com`,
  `api.arcadia.pinnacle.com` y `guest.api.arcadia.pinnacle.com` resetean TLS.
  No se ejecutó el recorrido real con Selenium, así que los selectores y la
  extracción de `start_time` son best-effort. Está marcado como no verificado en
  `reports/scrapers-asis.md`.
- El driver debe configurarse con `PINNACLE_CHROMEDRIVER_PATH` o
  `CHROMEDRIVER_PATH`; sin él, el proveedor lanza un error claro en vez de
  devolver una tabla vacía.
- No se copiaron tokens, cookies ni firmas de Pinnacle.

## Consecuencias para la Fase C

BetPlay/Kambi sí responde desde esta red y tiene un endpoint público JSON. La
Fase C puede ser un proveedor real, verificado con datos en vivo y fixtures.
