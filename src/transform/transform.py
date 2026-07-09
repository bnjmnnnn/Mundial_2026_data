"""
Transformación de datos crudos (bronze) a tablas planas (silver).

Tablas generadas:
  - matches         : información base de cada partido
  - team_stats      : estadísticas por equipo / partido
  - events_incidents: todos los incidentes (goles, tarjetas, cambios, etc.)
  - match_goals     : subconjunto de incidentes tipo 'goal'
  - match_cards     : subconjunto de incidentes tipo 'card'
  - match_subs      : subconjunto de incidentes tipo 'substitution'
  - player_stats    : estadísticas individuales por jugador / partido

Exporta todo a CSV y Parquet en data/silver/.

Uso:
    python -m src.transform.transform
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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
# Rutas
# ---------------------------------------------------------------------------
RAW_DIR = config.RAW_DATA_PATH
SILVER_DIR = config.SILVER_DATA_PATH


def load_json(path: Path) -> Optional[dict]:
    """Carga un archivo JSON de forma segura."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("No se pudo cargar %s: %s", path, exc)
        return None


# =============================================================================
# 1. MATCHES
# =============================================================================
def build_matches_table(event_ids: List[int]) -> pd.DataFrame:
    """
    Construye la tabla de partidos a partir de los archivos
    event_{id}.json y detail_{id}.json.
    """
    rows: List[dict] = []

    for eid in event_ids:
        event = load_json(RAW_DIR / "events" / f"event_{eid}.json")
        detail = load_json(RAW_DIR / "details" / f"detail_{eid}.json")

        if event is None:
            continue

        # Datos básicos del evento
        home = event.get("homeTeam", {})
        away = event.get("awayTeam", {})
        hscore = event.get("homeScore", {})
        ascore = event.get("awayScore", {})
        status = event.get("status", {})
        round_info = event.get("roundInfo", {})
        tournament = event.get("tournament", {})
        season = event.get("season", {})
        time_info = event.get("time", {})

        row = {
            "match_id": eid,
            "season_id": season.get("id"),
            "season_name": season.get("name"),
            "round": round_info.get("round"),
            "group_name": tournament.get("groupName"),
            "group_sign": tournament.get("groupSign"),
            "status_code": status.get("code"),
            "status_description": status.get("description"),
            "winner_code": event.get("winnerCode"),

            # Home
            "home_team_id": home.get("id"),
            "home_team_name": home.get("name"),
            "home_team_code": home.get("nameCode"),
            "home_score": hscore.get("current"),
            "home_score_p1": hscore.get("period1"),
            "home_score_p2": hscore.get("period2"),

            # Away
            "away_team_id": away.get("id"),
            "away_team_name": away.get("name"),
            "away_team_code": away.get("nameCode"),
            "away_score": ascore.get("current"),
            "away_score_p1": ascore.get("period1"),
            "away_score_p2": ascore.get("period2"),

            # Timing
            "start_timestamp": event.get("startTimestamp"),
            "start_datetime": (
                datetime.utcfromtimestamp(event.get("startTimestamp", 0))
                .isoformat() if event.get("startTimestamp") else None
            ),
            "injury_time_1": time_info.get("injuryTime1"),
            "injury_time_2": time_info.get("injuryTime2"),

            # Flags
            "has_xg": event.get("hasXg"),
            "has_player_stats": event.get("hasEventPlayerStatistics"),
            "has_heatmaps": event.get("hasEventPlayerHeatMap"),
        }

        # Enriquecer con datos del detail si existe
        if detail and "event" in detail:
            d = detail["event"]
            row["attendance"] = d.get("attendance")

            venue = d.get("venue", {})
            row["venue_name"] = venue.get("name")
            row["venue_city"] = venue.get("city", {}).get("name")
            row["venue_country"] = venue.get("country", {}).get("name")
            row["venue_capacity"] = venue.get("capacity")

            referee = d.get("referee", {})
            row["referee_name"] = referee.get("name")
            row["referee_country"] = referee.get("country", {}).get("name")

            # Managers (si existen)
            ht = d.get("homeTeam", {})
            at = d.get("awayTeam", {})
            row["home_manager"] = ht.get("manager", {}).get("name")
            row["away_manager"] = at.get("manager", {}).get("name")

        rows.append(row)

    df = pd.DataFrame(rows)
    logger.info("Tabla matches: %d filas, %d columnas", len(df), len(df.columns))
    return df


# =============================================================================
# 2. TEAM STATS
# =============================================================================
def build_team_stats_table(event_ids: List[int]) -> pd.DataFrame:
    """
    Extrae estadísticas por equipo para cada partido.
    Cada fila = un equipo en un partido.
    """
    rows: List[dict] = []

    for eid in event_ids:
        stats = load_json(RAW_DIR / "stats" / f"stats_{eid}.json")
        event = load_json(RAW_DIR / "events" / f"event_{eid}.json")

        if stats is None or event is None:
            continue

        home_name = event.get("homeTeam", {}).get("name", "Home")
        away_name = event.get("awayTeam", {}).get("name", "Away")

        # Sofascore organiza stats por periodo (ALL, 1ST, 2ND)
        # Tomamos solo period = "ALL"
        all_periods = stats.get("statistics", [])
        all_stats = [p for p in all_periods if p.get("period") == "ALL"]

        if not all_stats:
            continue

        # Construir dict de métricas por equipo
        home_metrics: Dict[str, Any] = {"match_id": eid, "team": home_name, "is_home": True}
        away_metrics: Dict[str, Any] = {"match_id": eid, "team": away_name, "is_home": False}

        for group in all_stats[0].get("groups", []):
            for item in group.get("statisticsItems", []):
                key = item.get("key")
                if key:
                    home_metrics[key] = item.get("homeValue")
                    away_metrics[key] = item.get("awayValue")

        rows.append(home_metrics)
        rows.append(away_metrics)

    df = pd.DataFrame(rows)
    logger.info("Tabla team_stats: %d filas, %d columnas", len(df), len(df.columns))
    return df


# =============================================================================
# 3. EVENTS INCIDENTS (tabla maestra)
# =============================================================================
def build_incidents_table(event_ids: List[int]) -> pd.DataFrame:
    """
    Tabla plana con todos los incidentes de todos los partidos.
    """
    rows: List[dict] = []

    for eid in event_ids:
        data = load_json(RAW_DIR / "incidents" / f"incidents_{eid}.json")
        if data is None:
            continue

        for inc in data.get("incidents", []):
            row = {
                "match_id": eid,
                "incident_type": inc.get("incidentType"),
                "incident_class": inc.get("incidentClass"),
                "time": inc.get("time"),
                "added_time": inc.get("addedTime"),
                "is_home": inc.get("isHome"),
                "reversed_period_time": inc.get("reversedPeriodTime"),
            }

            # Jugador asociado (tarjetas, goles)
            player = inc.get("player")
            if player:
                row["player_id"] = player.get("id")
                row["player_name"] = player.get("name")
                row["player_short_name"] = player.get("shortName")
                row["player_position"] = player.get("position")
                row["player_jersey"] = player.get("jerseyNumber")

            # Gol: scorer
            if inc.get("incidentType") == "goal":
                row["home_score"] = inc.get("homeScore")
                row["away_score"] = inc.get("awayScore")
                row["goal_type"] = inc.get("goalType")
                row["body_part"] = inc.get("bodyPart")

                # Asistencia
                assist = inc.get("assist1")
                if assist:
                    row["assist_player_id"] = assist.get("id")
                    row["assist_player_name"] = assist.get("name")

            # Tarjeta
            if inc.get("incidentType") == "card":
                row["card_reason"] = inc.get("reason")
                row["card_rescinded"] = inc.get("rescinded")

            # Sustitución
            if inc.get("incidentType") == "substitution":
                pin = inc.get("playerIn")
                pout = inc.get("playerOut")
                if pin:
                    row["sub_in_id"] = pin.get("id")
                    row["sub_in_name"] = pin.get("name")
                if pout:
                    row["sub_out_id"] = pout.get("id")
                    row["sub_out_name"] = pout.get("name")
                row["sub_injury"] = inc.get("injury")

            rows.append(row)

    df = pd.DataFrame(rows)
    logger.info("Tabla events_incidents: %d filas, %d columnas", len(df), len(df.columns))
    return df


# =============================================================================
# 4. SUB-TABLAS DERIVADAS
# =============================================================================
def build_goals_table(incidents_df: pd.DataFrame) -> pd.DataFrame:
    """Filtra solo goles de la tabla de incidentes."""
    if incidents_df.empty:
        return incidents_df.copy()
    goals = incidents_df[incidents_df["incident_type"] == "goal"].copy()
    logger.info("Tabla match_goals: %d filas", len(goals))
    return goals


def build_cards_table(incidents_df: pd.DataFrame) -> pd.DataFrame:
    """Filtra solo tarjetas."""
    if incidents_df.empty:
        return incidents_df.copy()
    cards = incidents_df[incidents_df["incident_type"] == "card"].copy()
    logger.info("Tabla match_cards: %d filas", len(cards))
    return cards


def build_substitutions_table(incidents_df: pd.DataFrame) -> pd.DataFrame:
    """Filtra solo sustituciones."""
    if incidents_df.empty:
        return incidents_df.copy()
    subs = incidents_df[incidents_df["incident_type"] == "substitution"].copy()
    logger.info("Tabla match_subs: %d filas", len(subs))
    return subs


# =============================================================================
# 5. PLAYER STATS (lineups)
# =============================================================================
def build_player_stats_table(event_ids: List[int]) -> pd.DataFrame:
    """
    Extrae estadísticas individuales por jugador para cada partido.
    Cada fila = un jugador en un partido.
    """
    rows: List[dict] = []

    for eid in event_ids:
        lineups = load_json(RAW_DIR / "lineups" / f"lineups_{eid}.json")
        if lineups is None:
            continue

        for side in ["home", "away"]:
            team_data = lineups.get(side, {})
            team_id = team_data.get("teamId")
            formation = team_data.get("formation")
            players = team_data.get("players", [])

            for p in players:
                player_info = p.get("player", {})
                stats = p.get("statistics", {})

                row = {
                    "match_id": eid,
                    "team_id": team_id,
                    "team_side": side,
                    "formation": formation,
                    "player_id": player_info.get("id"),
                    "player_name": player_info.get("name"),
                    "player_short_name": player_info.get("shortName"),
                    "player_slug": player_info.get("slug"),
                    "shirt_number": p.get("shirtNumber") or p.get("jerseyNumber"),
                    "position": p.get("position"),
                    "is_substitute": p.get("substitute", False),
                    "is_captain": p.get("captain", False),
                }

                # Aplanar estadísticas numéricas
                for stat_key, stat_val in stats.items():
                    if stat_key in ("ratingVersions", "statisticsType"):
                        continue
                    if isinstance(stat_val, (int, float)):
                        row[stat_key] = stat_val
                    elif stat_key == "ratingVersions" and isinstance(stat_val, dict):
                        row["rating_original"] = stat_val.get("original")
                        row["rating_alternative"] = stat_val.get("alternative")

                rows.append(row)

    df = pd.DataFrame(rows)
    logger.info("Tabla player_stats: %d filas, %d columnas", len(df), len(df.columns))
    return df


# =============================================================================
# PERSISTENCIA SILVER
# =============================================================================
def save_silver(df: pd.DataFrame, name: str) -> None:
    """Guarda un DataFrame como CSV y Parquet en data/silver/."""
    if df.empty:
        logger.warning("DataFrame %s está vacío, omitiendo.", name)
        return

    SILVER_DIR.mkdir(parents=True, exist_ok=True)

    # CSV
    csv_path = SILVER_DIR / f"{name}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info("Guardado CSV: %s (%d filas)", csv_path, len(df))

    # Parquet
    parquet_path = SILVER_DIR / f"{name}.parquet"
    df.to_parquet(parquet_path, index=False)
    logger.info("Guardado Parquet: %s", parquet_path)


# =============================================================================
# MAIN
# =============================================================================
def main():
    logger.info("=" * 60)
    logger.info("INICIANDO TRANSFORMACIÓN - Capa Silver")
    logger.info("=" * 60)

    # Leer extraction_summary para obtener la lista de event_ids
    summary = load_json(RAW_DIR / "extraction_summary.json")
    if summary is None:
        logger.error("No se encontró extraction_summary.json. Abortando.")
        sys.exit(1)

    event_ids = [r["event_id"] for r in summary.get("results", [])]
    logger.info("Partidos a transformar: %d", len(event_ids))

    # 1. Matches
    matches_df = build_matches_table(event_ids)
    save_silver(matches_df, "matches")

    # 2. Team Stats
    team_stats_df = build_team_stats_table(event_ids)
    save_silver(team_stats_df, "team_stats")

    # 3. Incidents
    incidents_df = build_incidents_table(event_ids)
    save_silver(incidents_df, "events_incidents")

    # 4. Sub-tablas
    goals_df = build_goals_table(incidents_df)
    save_silver(goals_df, "match_goals")

    cards_df = build_cards_table(incidents_df)
    save_silver(cards_df, "match_cards")

    subs_df = build_substitutions_table(incidents_df)
    save_silver(subs_df, "match_substitutions")

    # 5. Player stats (lineups)
    player_stats_df = build_player_stats_table(event_ids)
    save_silver(player_stats_df, "player_stats")

    # Resumen
    logger.info("=" * 60)
    logger.info("TRANSFORMACIÓN COMPLETADA")
    logger.info("Archivos generados en: %s", SILVER_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
