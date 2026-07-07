"""
Cliente HTTP para la API de Sofascore con manejo de reintentos,
backoff exponencial y persistencia de datos crudos (capa bronze).

Estrategia HTTP:
  1. curl_cffi (impersonate="chrome") — primary, evita 403
  2. requests estándar — fallback si curl_cffi no está instalado
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Selección de cliente HTTP
# ---------------------------------------------------------------------------
try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    curl_requests = None
    _HAS_CURL_CFFI = False

import requests as std_requests

from src.utils import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------
class SofascoreAPIError(Exception):
    """Error personalizado para fallos persistentes de la API de Sofascore."""
    pass


# ---------------------------------------------------------------------------
# Wrapper HTTP con backoff exponencial
# ---------------------------------------------------------------------------
def _http_get(url: str, headers: dict, timeout: int = 30, impersonate: bool = True):
    """Wrapper interno que usa curl_cffi si está disponible."""
    if _HAS_CURL_CFFI and impersonate:
        return curl_requests.get(url, headers=headers, impersonate="chrome", timeout=timeout)
    return std_requests.get(url, headers=headers, timeout=timeout)


def fetch_with_backoff(
    url: str,
    headers: Optional[dict] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: int = 30,
) -> dict:
    """
    Realiza GET a la API con backoff exponencial y persistencia.

    - Reintento solo en 429, 500, 502, 503, 504
    - Timeout de 30 segundos
    - Delay de cortesía 0.5s entre llamadas exitosas
    - Retorna dict parseado del JSON

    Raises
    ------
    SofascoreAPIError
        Si se agotan los reintentos.
    """
    if headers is None:
        headers = config.HEADERS

    retryable_statuses = {429, 500, 502, 503, 504}
    delay = base_delay

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("GET %s (intento %d/%d)", url, attempt, max_retries)
            response = _http_get(url, headers=headers, timeout=timeout)

            # Éxito
            if response.status_code == 200:
                time.sleep(0.5)  # cortesía
                try:
                    return response.json()
                except json.JSONDecodeError as exc:
                    raise SofascoreAPIError(f"Respuesta no es JSON válido: {url}") from exc

            # Errores reintentables
            if response.status_code in retryable_statuses and attempt < max_retries:
                logger.warning(
                    "Status %d en %s. Reintentando en %.1fs...",
                    response.status_code, url, delay,
                )
                time.sleep(delay)
                delay *= 2
                continue

            # Error no reintentable o último intento
            response.raise_for_status()

        except (TimeoutError, std_requests.exceptions.Timeout):
            if attempt < max_retries:
                logger.warning("Timeout en %s. Reintentando en %.1fs...", url, delay)
                time.sleep(delay)
                delay *= 2
            else:
                raise SofascoreAPIError(f"Timeout persistente: {url}") from None

        except Exception as exc:
            if attempt < max_retries:
                logger.warning(
                    "Error en %s: %s. Reintentando en %.1fs...",
                    url, exc, delay,
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise SofascoreAPIError(f"Fallo persistente: {url}") from exc

    raise SofascoreAPIError(f"No se pudo obtener {url} tras {max_retries} intentos")


# ---------------------------------------------------------------------------
# Endpoints específicos de Sofascore
# ---------------------------------------------------------------------------
def get_seasons(tournament_id: int = config.UNIQUE_TOURNAMENT_ID) -> dict:
    """
    GET /unique-tournament/{tournament_id}/seasons
    Retorna temporadas disponibles del torneo.
    """
    url = f"{config.BASE_URL}/unique-tournament/{tournament_id}/seasons"
    return fetch_with_backoff(url)


def get_events_by_round(
    round_number: int,
    season_id: int = config.SEASON_ID,
    tournament_id: int = config.UNIQUE_TOURNAMENT_ID,
) -> dict:
    """
    GET /unique-tournament/{id}/season/{sid}/events/round/{round_number}

    Retorna dict con lista de partidos de una ronda específica.
    Incluye campo ``events`` y posiblemente ``hasNextPage``.
    """
    url = (
        f"{config.BASE_URL}/unique-tournament/{tournament_id}"
        f"/season/{season_id}/events/round/{round_number}"
    )
    return fetch_with_backoff(url)


def get_event_statistics(event_id: int) -> dict:
    """
    GET /event/{event_id}/statistics
    Retorna estadísticas del partido (posesión, tiros, xG, tarjetas, etc.).
    """
    url = f"{config.BASE_URL}/event/{event_id}/statistics"
    return fetch_with_backoff(url)


def get_event_incidents(event_id: int) -> dict:
    """
    GET /event/{event_id}/incidents
    Retorna incidentes: goles, tarjetas, sustituciones.
    """
    url = f"{config.BASE_URL}/event/{event_id}/incidents"
    return fetch_with_backoff(url)


def get_event_detail(event_id: int) -> dict:
    """
    GET /event/{event_id}
    Retorna detalle completo del partido (estadio, árbitro, alineaciones).
    """
    url = f"{config.BASE_URL}/event/{event_id}"
    return fetch_with_backoff(url)


# ---------------------------------------------------------------------------
# Persistencia de capa raw (bronze)
# ---------------------------------------------------------------------------
def save_json(data: dict, filename: str, directory: Optional[Path] = None) -> Path:
    """Guarda un dict como JSON en disco. Retorna la ruta del archivo."""
    target_dir = directory or config.RAW_DATA_PATH
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / filename
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Guardado %s", file_path)
    return file_path
