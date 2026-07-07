"""
Capa Gold: Datasets optimizados para Machine Learning y análisis de apuestas.

Tablas generadas:
  - team_features        : Cada fila = un equipo en un partido (144 filas)
                           Features por partido + contexto + rolling stats + targets ML
  - match_ml_dataset     : Cada fila = un partido (72 filas)
                           Comparativa home vs away con diferencias. Ideal para predecir resultado.
  - team_tournament_agg  : Stats agregadas por equipo en todo el torneo (48 equipos)
                           Para dashboards y análisis comparativo.

Targets para apuestas:
  - result (W/D/L)
  - goals_scored, goals_conceded (regresión)
  - over_2_5 (True/False)
  - btts (both teams to score, True/False)

Uso:
    python -m src.transform.gold
"""

import logging
import sys
from pathlib import Path

import pandas as pd
import numpy as np

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

GOLD_DIR = config.GOLD_DATA_PATH
SILVER_DIR = config.SILVER_DATA_PATH


def load_silver() -> dict:
    """Carga las tablas silver necesarias."""
    return {
        "matches": pd.read_csv(SILVER_DIR / "matches.csv"),
        "team_stats": pd.read_csv(SILVER_DIR / "team_stats.csv"),
        "goals": pd.read_csv(SILVER_DIR / "match_goals.csv"),
        "cards": pd.read_csv(SILVER_DIR / "match_cards.csv"),
    }


# =============================================================================
# 1. TEAM_FEATURES — Dataset ML por equipo/partido
# =============================================================================
def build_team_features(matches: pd.DataFrame, team_stats: pd.DataFrame) -> pd.DataFrame:
    """
    Construye dataset donde cada fila es un equipo en un partido.
    Incluye: stats del partido + contexto + targets para ML.
    """
    logger.info("Construyendo team_features...")

    # Unir matches con team_stats
    df = team_stats.merge(
        matches[[
            "match_id", "round", "group_name", "group_sign",
            "home_team_name", "away_team_name",
            "home_score", "away_score",
            "home_team_id", "away_team_id",
            "attendance", "venue_country",
            "start_timestamp", "start_datetime",
        ]],
        on="match_id",
        how="left",
    )

    # Contexto: determinar rival, goles propios/concedidos, resultado
    def get_context(row):
        is_home = row["is_home"]
        home_team = row["home_team_name"]
        away_team = row["away_team_name"]
        home_score = row["home_score"]
        away_score = row["away_score"]
        home_id = row["home_team_id"]
        away_id = row["away_team_id"]

        team = home_team if is_home else away_team
        rival = away_team if is_home else home_team
        team_id = home_id if is_home else away_id
        rival_id = away_id if is_home else home_id
        goals_scored = home_score if is_home else away_score
        goals_conceded = away_score if is_home else home_score

        if goals_scored > goals_conceded:
            result = "W"
        elif goals_scored < goals_conceded:
            result = "L"
        else:
            result = "D"

        return pd.Series({
            "team": team,
            "team_id": team_id,
            "rival": rival,
            "rival_id": rival_id,
            "goals_scored": goals_scored,
            "goals_conceded": goals_conceded,
            "result": result,
            "goal_difference": goals_scored - goals_conceded,
        })

    context = df.apply(get_context, axis=1)
    df = pd.concat([df, context], axis=1)

    # Targets de apuestas
    df["over_2_5"] = (df["home_score"] + df["away_score"]) > 2.5
    df["btts"] = (df["home_score"] > 0) & (df["away_score"] > 0)
    df["clean_sheet"] = df["goals_conceded"] == 0

    # Features derivadas
    df["is_group_stage"] = df["round"] <= 3
    df["is_knockout"] = df["round"] > 3

    # Eliminar columnas duplicadas (algunas del merge coinciden con las creadas por get_context)
    df = df.loc[:, ~df.columns.duplicated()]

    # Renombrar columnas de stats para claridad
    rename_map = {
        "ballPossession": "possession_pct",
        "expectedGoals": "xG",
        "totalShotsOnGoal": "total_shots",
        "shotsOnGoal": "shots_on_target",
        "bigChanceCreated": "big_chances",
        "bigChanceScored": "big_chances_scored",
        "cornerKicks": "corners",
        "fouls": "fouls_committed",
        "yellowCards": "yellow_cards",
        "redCards": "red_cards",
        "passes": "passes_attempted",
        "accuratePasses": "passes_completed",
        "totalTackle": "tackles",
        "interceptionWon": "interceptions",
        "ballRecovery": "recoveries",
        "totalClearance": "clearances",
        "goalkeeperSaves": "gk_saves",
        "duelWonPercent": "duels_won_pct",
        "goalsPrevented": "goals_prevented",
        "dribblesPercentage": "dribble_success_pct",
        "touchesInOppBox": "touches_opp_box",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Columnas finales ordenadas
    core_cols = [
        "match_id", "team", "team_id", "rival", "rival_id",
        "is_home", "round", "group_sign",
        "goals_scored", "goals_conceded", "goal_difference",
        "result", "over_2_5", "btts", "clean_sheet",
        "possession_pct", "xG", "total_shots", "shots_on_target",
        "big_chances", "big_chances_scored", "corners",
        "fouls_committed", "yellow_cards", "red_cards",
        "passes_attempted", "passes_completed",
        "tackles", "interceptions", "recoveries", "clearances",
        "gk_saves", "goals_prevented",
        "duels_won_pct", "dribble_success_pct", "touches_opp_box",
        "attendance", "venue_country",
        "start_timestamp", "start_datetime",
    ]
    # Mantener solo las que existen
    final_cols = [c for c in core_cols if c in df.columns]
    remaining = [c for c in df.columns if c not in final_cols]
    df = df[final_cols + remaining]

    logger.info("team_features: %d filas x %d columnas", len(df), len(df.columns))
    return df


# =============================================================================
# 2. MATCH_ML_DATASET — Dataset por partido (comparativa home vs away)
# =============================================================================
def build_match_ml_dataset(matches: pd.DataFrame, team_stats: pd.DataFrame) -> pd.DataFrame:
    """
    Cada fila = un partido. Features diferenciales home vs away.
    Ideal para predecir: 1X2, over/under, BTTS.
    """
    logger.info("Construyendo match_ml_dataset...")

    # Separar home y away stats
    home_stats = team_stats[team_stats["is_home"] == True].copy()
    away_stats = team_stats[team_stats["is_home"] == False].copy()

    # Seleccionar columnas numéricas relevantes
    numeric_cols = [
        "ballPossession", "expectedGoals", "totalShotsOnGoal", "shotsOnGoal",
        "bigChanceCreated", "bigChanceScored", "cornerKicks", "fouls",
        "yellowCards", "redCards", "passes", "accuratePasses",
        "totalTackle", "interceptionWon", "ballRecovery", "totalClearance",
        "goalkeeperSaves", "goalsPrevented", "duelWonPercent",
        "dribblesPercentage", "touchesInOppBox", "accurateCross",
        "accurateLongBalls", "wonTacklePercent",
    ]
    numeric_cols = [c for c in numeric_cols if c in team_stats.columns]

    # Renombrar con prefijo
    home_rename = {c: f"home_{c}" for c in numeric_cols}
    away_rename = {c: f"away_{c}" for c in numeric_cols}

    home_stats = home_stats.rename(columns=home_rename)
    away_stats = away_stats.rename(columns=away_rename)

    # Merge
    df = matches[[
        "match_id", "round", "group_sign",
        "home_team_name", "away_team_name",
        "home_score", "away_score",
        "attendance", "start_datetime",
    ]].copy()

    df = df.merge(
        home_stats[["match_id"] + list(home_rename.values())],
        on="match_id", how="left"
    )
    df = df.merge(
        away_stats[["match_id"] + list(away_rename.values())],
        on="match_id", how="left"
    )

    # Features diferenciales (home - away)
    for col in numeric_cols:
        h_col = f"home_{col}"
        a_col = f"away_{col}"
        if h_col in df.columns and a_col in df.columns:
            df[f"diff_{col}"] = df[h_col] - df[a_col]

    # Targets
    df["home_win"] = (df["home_score"] > df["away_score"]).astype(int)
    df["draw"] = (df["home_score"] == df["away_score"]).astype(int)
    df["away_win"] = (df["home_score"] < df["away_score"]).astype(int)
    df["result_1x2"] = df["home_win"].astype(str) + df["draw"].astype(str) + df["away_win"].astype(str)
    df["result_1x2"] = df["result_1x2"].map({"100": "H", "010": "D", "001": "A"})

    df["over_2_5"] = (df["home_score"] + df["away_score"]) > 2.5
    df["btts"] = (df["home_score"] > 0) & (df["away_score"] > 0)
    df["total_goals"] = df["home_score"] + df["away_score"]
    df["goal_difference"] = df["home_score"] - df["away_score"]

    logger.info("match_ml_dataset: %d filas x %d columnas", len(df), len(df.columns))
    return df


# =============================================================================
# 3. TEAM_TOURNAMENT_AGG — Stats agregadas por equipo
# =============================================================================
def build_team_tournament_agg(team_features: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega stats por equipo en todo el torneo.
    Para dashboards y análisis comparativo.
    """
    logger.info("Construyendo team_tournament_agg...")

    numeric_cols = [
        "goals_scored", "goals_conceded", "goal_difference",
        "possession_pct", "xG", "total_shots", "shots_on_target",
        "big_chances", "big_chances_scored", "corners",
        "fouls_committed", "yellow_cards", "red_cards",
        "passes_attempted", "passes_completed",
        "tackles", "interceptions", "recoveries", "clearances",
        "gk_saves", "goals_prevented",
        "duels_won_pct", "dribble_success_pct", "touches_opp_box",
        "attendance",
    ]
    numeric_cols = [c for c in numeric_cols if c in team_features.columns]

    agg = team_features.groupby("team").agg({
        "match_id": "count",
        "goals_scored": "sum",
        "goals_conceded": "sum",
        "goal_difference": "sum",
        "result": lambda x: (x == "W").sum(),  # wins
        "clean_sheet": "sum",
        "over_2_5": "sum",
        "btts": "sum",
        **{c: "mean" for c in numeric_cols},
    }).reset_index()

    agg = agg.rename(columns={
        "match_id": "matches_played",
        "result": "wins",
        "clean_sheet": "clean_sheets",
        "over_2_5": "over_2_5_count",
        "btts": "btts_count",
    })

    # Calcular puntos (3 por win, 1 por draw)
    draws = team_features.groupby("team").apply(
        lambda g: (g["result"] == "D").sum()
    ).reset_index(name="draws")
    losses = team_features.groupby("team").apply(
        lambda g: (g["result"] == "L").sum()
    ).reset_index(name="losses")

    agg = agg.merge(draws, on="team").merge(losses, on="team")
    agg["points"] = agg["wins"] * 3 + agg["draws"] * 1
    agg["win_pct"] = agg["wins"] / agg["matches_played"]
    agg["clean_sheet_pct"] = agg["clean_sheets"] / agg["matches_played"]
    agg["over_2_5_pct"] = agg["over_2_5_count"] / agg["matches_played"]
    agg["btts_pct"] = agg["btts_count"] / agg["matches_played"]

    logger.info("team_tournament_agg: %d equipos x %d columnas", len(agg), len(agg.columns))
    return agg


# =============================================================================
# PERSISTENCIA
# =============================================================================
def save_gold(df: pd.DataFrame, name: str) -> None:
    """Guarda DataFrame gold como CSV y Parquet."""
    if df.empty:
        logger.warning("DataFrame %s vacío, omitiendo.", name)
        return

    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = GOLD_DIR / f"{name}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info("Gold CSV: %s (%d filas)", csv_path, len(df))

    parquet_path = GOLD_DIR / f"{name}.parquet"
    df.to_parquet(parquet_path, index=False)
    logger.info("Gold Parquet: %s", parquet_path)


# =============================================================================
# MAIN
# =============================================================================
def main():
    logger.info("=" * 60)
    logger.info("INICIANDO CAPA GOLD — ML & Betting Dataset")
    logger.info("=" * 60)

    silver = load_silver()
    matches = silver["matches"]
    team_stats = silver["team_stats"]

    # 1. Team features (por equipo/partido)
    team_features = build_team_features(matches, team_stats)
    save_gold(team_features, "team_features")

    # 2. Match ML dataset (por partido, comparativa)
    match_ml = build_match_ml_dataset(matches, team_stats)
    save_gold(match_ml, "match_ml_dataset")

    # 3. Team tournament aggregate
    team_agg = build_team_tournament_agg(team_features)
    save_gold(team_agg, "team_tournament_agg")

    logger.info("=" * 60)
    logger.info("CAPA GOLD COMPLETADA")
    logger.info("Archivos en: %s", GOLD_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
