import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()   
# ---------------------------------------------------------------------------
# Configuración de la API de Sofascore
# ---------------------------------------------------------------------------
BASE_URL = "https://api.sofascore.com/api/v1"
UNIQUE_TOURNAMENT_ID = 16       # Mundial
SEASON_ID = 58210               # World Cup 2026 (descubierto en exploración)

# ---------------------------------------------------------------------------
# Headers HTTP
# ---------------------------------------------------------------------------
# NOTA: curl_cffi con impersonate="chrome" es la estrategia que funcionó.
# Si usas requests puro, estos headers ayudan pero pueden dar 403.
HEADERS = {
    "User-Agent": os.getenv(
        "SOFASCORE_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36",
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.sofascore.com/",
    "Connection": "keep-alive",
}

# ---------------------------------------------------------------------------
# Rutas de almacenamiento local
# ---------------------------------------------------------------------------
RAW_DATA_PATH = Path(os.getenv("RAW_DATA_PATH", "data/raw"))
SILVER_DATA_PATH = Path(os.getenv("SILVER_DATA_PATH", "data/silver"))
GOLD_DATA_PATH = Path(os.getenv("GOLD_DATA_PATH", "data/gold"))

# Asegurar que existan los directorios al importar el módulo
RAW_DATA_PATH.mkdir(parents=True, exist_ok=True)
SILVER_DATA_PATH.mkdir(parents=True, exist_ok=True)
GOLD_DATA_PATH.mkdir(parents=True, exist_ok=True)
