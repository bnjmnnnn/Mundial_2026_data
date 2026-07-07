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


def fetch_all_rounds() -> List[Dict[str, Any]]:
    """
    Itera rondas desde 1 hasta que no haya eventos o se alcance MAX_ROUNDS.
    Retorna lista plana de todos los eventos finalizados.
    """
    all_events = []

    for round_num in range(1, MAX_ROUNDS + 1):
        logger.info("=== RONDA %d ===", round_num)

        try:
            data = client.get_events_by_round(
                round_number=round_num,
                season_id=SEASON_ID,
                tournament_id=TOURNAMENT_ID,
            )
        except client.SofascoreAPIError as exc:
            logger.error("Error al obtener ronda %d: %s", round_num, exc)
            break

        events = data.get("events", [])
        if not events:
            logger.info("Ronda %d sin eventos. Fin del torneo.", round_num)
            break

        # Filtrar solo finalizados
        finished = [
            ev for ev in events
            if ev.get("status", {}).get("code") == 100
        ]

        logger.info(
            "Ronda %d: %d eventos (%d finalizados)",
            round_num, len(events), len(finished),
        )

        all_events.extend(finished)

        # Guardar JSON de la ronda completa (backup)
        client.save_json(
            data,
            f"round_{round_num}_events.json",
            directory=RAW_DIR / "rounds",
        )

    logger.info("TOTAL partidos finalizados: %d", len(all_events))
    return all_events


def fetch_event_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dado un evento (dict), descarga estadísticas e incidentes.
    Guarda todo en disco y retorna resumen.
    """
    event_id = event["id"]
    home = event.get("homeTeam", {}).get("name", "?")
    away = event.get("awayTeam", {}).get("name", "?")

    logger.info("Descargando event %d: %s vs %s", event_id, home, away)

    result = {
        "event_id": event_id,
        "match": f"{home} vs {away}",
        "stats_ok": False,
        "incidents_ok": False,
        "detail_ok": False,
    }

    # 1. Guardar el evento base
    client.save_json(
        event,
        f"event_{event_id}.json",
        directory=RAW_DIR / "events",
    )

    # 2. Estadísticas
    try:
        stats = client.get_event_statistics(event_id)
        client.save_json(
            stats,
            f"stats_{event_id}.json",
            directory=RAW_DIR / "stats",
        )
        result["stats_ok"] = True
    except client.SofascoreAPIError as exc:
        logger.warning("Stats falló para %d: %s", event_id, exc)

    # 3. Incidentes
    try:
        incidents = client.get_event_incidents(event_id)
        client.save_json(
            incidents,
            f"incidents_{event_id}.json",
            directory=RAW_DIR / "incidents",
        )
        result["incidents_ok"] = True
    except client.SofascoreAPIError as exc:
        logger.warning("Incidents falló para %d: %s", event_id, exc)

    # 4. Detalle completo (opcional, por si tiene alineaciones)
    try:
        detail = client.get_event_detail(event_id)
        client.save_json(
            detail,
            f"detail_{event_id}.json",
            directory=RAW_DIR / "details",
        )
        result["detail_ok"] = True
    except client.SofascoreAPIError as exc:
        logger.warning("Detail falló para %d: %s", event_id, exc)

    return result


def main():
    """Pipeline completo de extracción."""
    logger.info("=" * 60)
    logger.info("INICIANDO EXTRACCIÓN - Mundial 2026")
    logger.info("Season ID: %d | Torneo ID: %d", SEASON_ID, TOURNAMENT_ID)
    logger.info("=" * 60)

    # Paso 1: Obtener todos los partidos por ronda
    events = fetch_all_rounds()

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
