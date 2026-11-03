# AGENTS.md

## Proyecto

Detector de surebets de NBA, SOLO PREMATCH, entre **Pinnacle y BetPlay**, que envía
alertas por Telegram. El usuario decide y apuesta a mano.
Base: los scrapers y la lógica de https://github.com/fernando-cortes-tejada/nba-surebets,
usados TAL CUAL primero y adaptados solo si fallan. Python 3.11+, pytest, ruff.

Decisión del usuario: la fuente de cuotas es el scraping de las páginas públicas de
Pinnacle y BetPlay. No se vuelve a discutir; se ejecuta y se mide.

## Forma de trabajo

1. Trabaja de forma autónoma por fases, sin esperar "continúa" entre ellas.
   Al terminar cada fase: commit, `pytest -q`, `ruff check .` y un resumen corto en
   reports/phase-N.md. Si una fase falla, documenta por qué y sigue con lo que no
   dependa de ella.
2. Pruebas primero cuando se toque lógica: escribe el test, confirma que falla,
   implementa, confirma que pasa.
3. Commits pequeños en ramas `feat/...`; nunca en main. Responde en español; código
   y comentarios en inglés.
4. No afirmes que algo funciona sin haberlo ejecutado. Si no se pudo verificar,
   dilo en el resumen de la fase.

## Orden de trabajo

- Fase A: clonar nba-surebets en una carpeta aparte, ejecutar su demo y sus tests, y
  probar su scraper de Pinnacle TAL CUAL. Registrar en reports/scrapers-asis.md qué
  funciona, qué falla y por qué. Sin modificarlo en esta fase.
- Fase B: portar o adaptar al paquete surebets/ lo que funcione. Ya existen
  OddsProvider, ManualProvider y MockProvider; los scrapers entran como proveedores.
- Fase C: proveedor de BetPlay. NO existe en el repo original: se escribe con el
  mismo patrón, apoyándose en la evidencia de recon/ (BetPlay usa Kambi) y en
  fixtures guardados. Tests offline con fixtures.
- Fase D: filtros prematch, detección y stakes, alertas Telegram, registro y reporte.

## Scraping: qué está permitido

5. Se permite consultar las páginas y endpoints PÚBLICOS de Pinnacle y BetPlay, sin
   iniciar sesión, solo para leer cuotas de NBA.
6. Ritmo conservador (es prematch): mínimo 5 minutos entre pasadas por casa, esperas
   aleatorias, timeout de 30 s, máximo 2 reintentos con espera creciente. Nunca
   sondeos por segundo ni por milisegundo.
7. Cada cuota se guarda con captured_at. Descartar datos de más de
   MAX_ODDS_AGE_MINUTES (defecto 10 con scraping).

## Límites que no se cruzan (no son pausas: definen qué se construye)

8. NO login, NO sesiones de usuario y NO colocación de apuestas desde el código.
   La única acción tras una alerta es registrar tu elección ("Apostado" / "Descartar").
9. NO evadir defensas: sin stealth, sin falsificar huellas del navegador, sin
   rotación de IPs, sin resolver captchas, sin copiar tokens o firmas de sesiones.
   Si una casa responde con captcha, 403/429 o una página de cumplimiento: marca esa
   casa como "bloqueada" en reports/, sigue con las demás y no reintentes más.
10. El código NO configura, gestiona ni conmuta la VPN ni proxies. Para Pinnacle
    puede lanzar Firefox con Selenium usando un perfil dedicado
    (PINNACLE_FIREFOX_PROFILE en .env) que el usuario prepara con su extensión de
    VPN ya conectada. Ese perfil nunca tiene sesión de usuario iniciada.
    10b. Si Pinnacle no carga, aborta esa pasada: no reintentes por otra vía ni uses la
    conexión directa como respaldo. Si aparece captcha, 403/429 o página de
    verificación, marca la casa como bloqueada y sigue. Sin stealth ni ajustes para
    ocultar la automatización. Un solo ritmo: mínimo 5 minutos entre pasadas.
11. Credenciales solo en `.env` (en .gitignore). Nunca en código, logs, mensajes ni
    commits. No imprimir el token de Telegram ni el chat id.
12. El commit 7c06dd0 contiene datos sensibles en recon/legal/. NO publicar ni
    subir este repositorio a ningún remoto sin limpiar antes el historial.
13. recon/ está archivado: se puede leer como evidencia, pero el detector no importa
    nada de él.
14. Antes de comandos destructivos (rm -rf, git reset --hard, sobrescribir) pide
    confirmación.

## Términos de uso (informativo, no bloquea)

15. Para Pinnacle y BetPlay, registra en reports/terms.md la cláusula (número y cita
    de máx. 25 palabras con enlace) sobre acceso automatizado, bots y bloqueo de
    fondos. Si no la encuentras, escribe "no localizada". El proyecto sigue igual.

## Lógica de arbitraje

16. Solo prematch: descartar eventos con inicio menor a ahora + PREMATCH_MIN_MINUTES
    (defecto 30).
17. Comparar solo líneas idénticas (hándicap y totales). Mismo evento = mismos
    equipos y hora de inicio con tolerancia de 10 min. Normalización determinista
    primero; coincidencia difusa solo como respaldo con umbral alto y aviso.
18. Descartar cuotas <= 1.0, datos incompletos y cruces entre filas de la misma casa.
    Validar que las selecciones sean mutuamente excluyentes.
19. Margen neto = 1 - suma de probabilidades implícitas, menos comisiones y costo de
    conversión de divisas. Exigir MIN_NET_MARGIN (defecto 1%). Si las casas operan
    en monedas distintas, usar una tasa configurable con fecha, nunca fija.
20. Filtro de persistencia: alertar solo si la oportunidad aparece en N capturas
    consecutivas (PERSISTENCE_N, defecto 2).
21. Respetar MAX_STAKE y el incremento de apuesta de cada casa; avisar si el
    redondeo elimina el margen.
22. Toda alerta incluye: "Verifica cuotas y reglas de ambas casas antes de apostar".
    En props de jugador, hándicap y totales, añade la advertencia de reglas
    (jugador que no juega, tiempo extra, apuestas anuladas).

## Alertas y registro

23. Telegram con evento, hora de inicio, mercado y línea, casa y cuota de cada lado,
    stakes sugeridos, margen neto y antigüedad del dato. Botones "Apostado" y
    "Descartar".
24. Sin duplicados: re-alertar solo si el margen mejora más de 0,5 puntos. Respetar
    QUIET_HOURS. Ordenar las alertas por margen neto.
25. Registrar todas las oportunidades en data/opportunities.jsonl y las decisiones en
    data/decisions.jsonl. `data/` y `logs/` van en .gitignore.

## Configuración (config.yaml / .env)

PREMATCH*MIN_MINUTES, MAX_ODDS_AGE_MINUTES, MIN_NET_MARGIN, PERSISTENCE_N, MAX_STAKE,
COMMISSION*<casa>, FX_RATE y su fecha, QUIET_HOURS, SCRAPE_INTERVAL_MINUTES (>= 5).
Solo en .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.

## Comandos

- Setup: `py -m venv .venv`, activar, `pip install -e ".[dev]"`
- Escaneo: `python -m surebets.cli scan`
- Bucle: `python -m surebets.cli watch --interval 300 --max-iter N`
- Estado y reporte: `python -m surebets.cli status` / `report`
- Tests: `pytest -q` y `ruff check .`
