# Cambios (copiar sobre la carpeta del proyecto)

REEMPLAZAR/CREAR: pyproject.toml, surebets/{__init__,matching,filters,alerts,store,cli}.py,
surebets/providers/piwi.py, tests/test_detector.py
BORRAR: surebets/adapter.py, surebets/markets.py, test_pipeline.py, test_pipeline1.py, scripts/debug_piwi.py

Instalar:   pip install -e ".[dev,browser]"   (ya no se usa pandas)
Probar:     pytest -q ; ruff check .
Usar:       python -m surebets.cli scan | watch --interval 300 --max-iter 12 | piwi-sample
Variables (.env o entorno): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MIN_NET_MARGIN=0.01,
PERSISTENCE_N=2, MAX_STAKE=100, PREMATCH_MIN_MINUTES=30, MAX_ODDS_AGE_MINUTES=10, COMMISSION_<casa>=0.0
Piwi247 lanza error hasta que exista su parser real (ver piwi-sample).
