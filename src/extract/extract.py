"""
Script de extracción masiva (Hito 2)

Descarga de Sofascore:
  - Partidos por ronda (fase de grupos, eliminatorias, final)
  - Estadísticas por partido
  - Incidentes (goles, tarjetas, sustituciones)

Guarda todo en data/raw/ como capa bronze (JSON crudo).

Uso:
    python src/extract/extract.py
"""

import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

# Asegurar que src/ esté en el path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extract import sofascore_client as client
from src.utils import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuración de extracción
# ---------------------------------------------------------------------------
MAX_ROUNDS = 20          # Safety break para no iterar infinitamente
SEASON_ID = config.SEASON_ID
TOURNAMENT_ID = config.UNIQUE_TOURNAMENT_ID
RAW_DIR = config.RAW_DATA_PATH


def _is_finished(ev: Dict[str, Any]) -> bool:
    """Determina si un evento está finalizado (incluye penales y tiempo extra)."""
    status = ev.get("status", {})
    return status.get("type") == "finished"


def _load_existing_json(path: Path) -> Dict[str, Any] | None:
    """Carga un JSON existente o retorna None si no existe."""
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def fetch_all_events() -> List[Dict[str, Any]]:
    """
    Itera páginas /events/last/{page} hasta que hasNextPage sea False.
    Retorna lista plana de todos los eventos finalizados (sin duplicados).
    """
    all_events: List[Dict[str, Any]] = []
    seen_ids = set()
    page = 0
    max_pages = 50

    while page < max_pages:
        logger.info("=== PÁGINA %d ===", page)

        try:
            data = client.get_events_last_page(
                page=page,
                season_id=SEASON_ID,
                tournament_id=TOURNAMENT_ID,
            )
        except client.SofascoreAPIError as exc:
            logger.error("Error al obtener página %d: %s", page, exc)
            break

        events = data.get("events", [])
        if not events:
            logger.info("Página %d sin eventos. Fin del torneo.", page)
            break

        for ev in events:
            if _is_finished(ev) and ev["id"] not in seen_ids:
                seen_ids.add(ev["id"])
                all_events.append(ev)

        logger.info(
            "Página %d: %d eventos (%d nuevos finalizados)",
            page, len(events), len([e for e in events if _is_finished(e)]),
        )

        client.save_json(
            data,
            f"page_{page}_events.json",
            directory=RAW_DIR / "pages",
        )

        if not data.get("hasNextPage", False):
            logger.info("Última página alcanzada (hasNextPage=False).")
            break

        page += 1

    logger.info("TOTAL partidos finalizados únicos: %d", len(all_events))
    return all_events


def fetch_event_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dado un evento (dict), descarga/actualiza estadísticas e incidentes.
    Si el archivo ya existe en disco, lo reutiliza (evita requests redundantes).
    """
    event_id = event["id"]
    home = event.get("homeTeam", {}).get("name", "?")
    away = event.get("awayTeam", {}).get("name", "?")

    logger.info("Procesando event %d: %s vs %s", event_id, home, away)

    result = {
        "event_id": event_id,
        "match": f"{home} vs {away}",
        "stats_ok": False,
        "incidents_ok": False,
        "detail_ok": False,
    }

    client.save_json(
        event,
        f"event_{event_id}.json",
        directory=RAW_DIR / "events",
    )

    # Stats
    stats_path = RAW_DIR / "stats" / f"stats_{event_id}.json"
    if _load_existing_json(stats_path) is not None:
        logger.info("  Stats ya existen en disco, reutilizando.")
        result["stats_ok"] = True
    else:
        try:
            stats = client.get_event_statistics(event_id)
            client.save_json(stats, f"stats_{event_id}.json", directory=RAW_DIR / "stats")
            result["stats_ok"] = True
        except client.SofascoreAPIError as exc:
            logger.warning("  Stats falló para %d: %s", event_id, exc)

    # Incidents
    incidents_path = RAW_DIR / "incidents" / f"incidents_{event_id}.json"
    if _load_existing_json(incidents_path) is not None:
        logger.info("  Incidents ya existen en disco, reutilizando.")
        result["incidents_ok"] = True
    else:
        try:
            incidents = client.get_event_incidents(event_id)
            client.save_json(incidents, f"incidents_{event_id}.json", directory=RAW_DIR / "incidents")
            result["incidents_ok"] = True
        except client.SofascoreAPIError as exc:
            logger.warning("  Incidents falló para %d: %s", event_id, exc)

    # Detail
    detail_path = RAW_DIR / "details" / f"detail_{event_id}.json"
    if _load_existing_json(detail_path) is not None:
        logger.info("  Detail ya existe en disco, reutilizando.")
        result["detail_ok"] = True
    else:
        try:
            detail = client.get_event_detail(event_id)
            client.save_json(detail, f"detail_{event_id}.json", directory=RAW_DIR / "details")
            result["detail_ok"] = True
        except client.SofascoreAPIError as exc:
            logger.warning("  Detail falló para %d: %s", event_id, exc)

    return result


def main():
    """Pipeline completo de extracción."""
    logger.info("=" * 60)
    logger.info("INICIANDO EXTRACCIÓN - Mundial 2026")
    logger.info("Season ID: %d | Torneo ID: %d", SEASON_ID, TOURNAMENT_ID)
    logger.info("=" * 60)

    # Paso 1: Obtener todos los partidos por página
    events = fetch_all_events()

    if not events:
        logger.error("No se encontraron partidos. Abortando.")
        sys.exit(1)

    # Paso 2: Para cada partido, descargar stats e incidents
    summary = []
    for i, event in enumerate(events, 1):
        logger.info("[%d/%d] Procesando partido...", i, len(events))
        result = fetch_event_data(event)
        summary.append(result)

    # Paso 3: Reporte final
    stats_success = sum(1 for r in summary if r["stats_ok"])
    incidents_success = sum(1 for r in summary if r["incidents_ok"])
    detail_success = sum(1 for r in summary if r["detail_ok"])

    logger.info("=" * 60)
    logger.info("EXTRACCIÓN COMPLETADA")
    logger.info("Partidos procesados: %d", len(summary))
    logger.info("Stats descargadas: %d/%d", stats_success, len(summary))
    logger.info("Incidents descargados: %d/%d", incidents_success, len(summary))
    logger.info("Detalles descargados: %d/%d", detail_success, len(summary))
    logger.info("=" * 60)

    # Guardar resumen
    client.save_json(
        {"total_events": len(summary), "results": summary},
        "extraction_summary.json",
        directory=RAW_DIR,
    )

    return summary


if __name__ == "__main__":
    main()
