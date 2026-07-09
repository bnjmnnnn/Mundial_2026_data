"""
Capa Gold: Datasets de jugadores limpios y listos para análisis por posición.

Tablas generadas:
  - player_match_stats      : Cada fila = jugador en un partido (4,914 filas)
                                Con nulos tratados, ratios calculadas y posiciones normalizadas
  - player_tournament_agg   : Stats agregadas por jugador en todo el torneo (~500 jugadores)
  - position_comparison     : Percentiles y métricas comparativas por posición (G/D/M/F)

Uso:
    python -m src.transform.player_gold
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


# =============================================================================
# 1. CARGA Y LIMPIEZA
# =============================================================================
def load_and_clean_player_stats() -> pd.DataFrame:
    """
    Carga player_stats.csv y aplica limpieza completa:
      - Tratamiento inteligente de nulos por posición
      - Feature engineering (ratios)
      - Flags por posición
    """
    logger.info("Cargando player_stats.csv...")
    df = pd.read_csv(SILVER_DIR / "player_stats.csv")
    logger.info("Shape inicial: %d filas x %d columnas", len(df), len(df.columns))

    # --- Tratamiento de nulos por posición ---
    # Stats exclusivas de portero → 0 para jugadores de campo
    goalkeeper_cols = [
        "saves", "keeperSaveValue", "goalkeeperValueNormalized",
        "goodHighClaim", "savedShotsFromInsideTheBox",
        "punches", "totalKeeperSweeper", "accurateKeeperSweeper",
        "crossNotClaimed", "penaltySave",
    ]
    outfielder_cols = [
        "goals", "totalShots", "onTargetScoringAttempt",
        "shotOffTarget", "expectedGoals", "expectedGoalsOnTarget",
        "bigChanceMissed", "bigChanceCreated",
        "hitWoodwork", "totalOffside",
    ]

    is_gk = df["position"] == "G"
    # Porteros: stats de campo = 0
    df.loc[is_gk, outfielder_cols] = df.loc[is_gk, outfielder_cols].fillna(0)
    # No-porteros: stats de portero = 0
    df.loc[~is_gk, goalkeeper_cols] = df.loc[~is_gk, goalkeeper_cols].fillna(0)
    # Resto de stats raras (penales, eventos especiales) = 0 para todos
    rare_event_cols = [
        "penaltyWon", "penaltyFaced", "penaltyConceded",
        "errorLeadToAGoal", "clearanceOffLine",
        "penaltyShootoutSave", "penaltyShootoutGoal", "penaltyShootoutMiss",
        "lastManTackle", "ownGoals", "penaltyMiss",
        "errorLeadToAShot",
    ]
    df[rare_event_cols] = df[rare_event_cols].fillna(0)

    # --- Feature engineering: ratios clave ---
    df["pass_accuracy_pct"] = safe_pct(df, "accuratePass", "totalPass")
    df["long_ball_accuracy_pct"] = safe_pct(df, "accurateLongBalls", "totalLongBalls")
    df["opp_half_pass_accuracy_pct"] = safe_pct(df, "accurateOppositionHalfPasses", "totalOppositionHalfPasses")
    df["own_half_pass_accuracy_pct"] = safe_pct(df, "accurateOwnHalfPasses", "totalOwnHalfPasses")
    df["cross_accuracy_pct"] = safe_pct(df, "accurateCross", "totalCross")

    df["tackle_success_pct"] = safe_pct(df, "wonTackle", "totalTackle")
    df["aerial_success_pct"] = safe_pct(df, "aerialWon", df["aerialWon"] + df["aerialLost"])
    df["duel_success_pct"] = safe_pct(df, "duelWon", df["duelWon"] + df["duelLost"])
    df["contest_success_pct"] = safe_pct(df, "wonContest", "totalContest")

    df["shot_accuracy_pct"] = safe_pct(df, "onTargetScoringAttempt", "totalShots")
    df["big_chance_conversion_pct"] = safe_pct(df, "bigChanceCreated", df["bigChanceMissed"] + df["bigChanceCreated"])

    df["xg_efficiency"] = safe_ratio(df, "goals", "expectedGoals")
    df["xg_ontarget_efficiency"] = safe_ratio(df, "goals", "expectedGoalsOnTarget")

    # Normalizados por 90 minutos
    minutes = df["minutesPlayed"].replace(0, np.nan)
    df["xa_per_90"] = df["expectedAssists"] / minutes * 90
    df["key_passes_per_90"] = df["keyPass"] / minutes * 90
    df["defensive_actions_per_90"] = (df["totalTackle"] + df["interceptionWon"] + df["ballRecovery"]) / minutes * 90
    df["fouls_per_90"] = df["fouls"] / minutes * 90
    df["km_per_90"] = df["kilometersCovered"] / minutes * 90
    df["sprints_per_90"] = df["numberOfSprints"] / minutes * 90
    df["progression_per_carry"] = safe_ratio(df, "totalProgression", "ballCarriesCount")
    df["ball_carry_distance_per_carry"] = safe_ratio(df, "totalBallCarriesDistance", "ballCarriesCount")

    # Portero
    df["gk_save_pct"] = safe_pct(df, "saves", df["saves"] + df["goalsPrevented"])
    df["gk_saves_inside_box_pct"] = safe_pct(df, "savedShotsFromInsideTheBox", "saves")

    # --- Flags por posición ---
    df["is_goalkeeper"] = df["position"] == "G"
    df["is_defender"] = df["position"] == "D"
    df["is_midfielder"] = df["position"] == "M"
    df["is_forward"] = df["position"] == "F"

    # --- Ordenar columnas ---
    core_cols = [
        "match_id", "team_id", "team_side", "formation",
        "player_id", "player_name", "player_short_name", "player_slug",
        "shirt_number", "position", "is_substitute", "is_captain",
        "minutesPlayed", "rating", "rating_original", "rating_alternative",
    ]
    # Añadir resto de columnas ordenadas
    remaining = [c for c in df.columns if c not in core_cols]
    df = df[core_cols + sorted(remaining)]

    logger.info("Shape después de limpieza: %d filas x %d columnas", len(df), len(df.columns))
    return df


def safe_pct(df: pd.DataFrame, num_col: str, denom_col) -> pd.Series:
    """Calcula porcentaje seguro (evita div/0)."""
    if isinstance(denom_col, str):
        denom = df[denom_col]
    else:
        denom = denom_col
    denom = denom.replace(0, np.nan)
    return (df[num_col] / denom * 100).clip(0, 100)


def safe_ratio(df: pd.DataFrame, num_col: str, denom_col: str) -> pd.Series:
    """Calcula ratio seguro."""
    denom = df[denom_col].replace(0, np.nan)
    return df[num_col] / denom


# =============================================================================
# 2. PLAYER TOURNAMENT AGG
# =============================================================================
def build_player_tournament_agg(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega stats por jugador en todo el torneo.
    Métricas = promedios POR 90 MINUTOS (para comparar titulares y suplentes).
    """
    logger.info("Construyendo player_tournament_agg...")

    # Primero, calcular totales por jugador
    agg = df.groupby("player_id").agg({
        "player_name": "first",
        "player_short_name": "first",
        "position": "first",
        "shirt_number": "first",
        "match_id": "count",
        "minutesPlayed": "sum",
        "is_substitute": "sum",  # cuántas veces entró de suplente
    }).reset_index()

    agg = agg.rename(columns={
        "match_id": "matches_played",
        "minutesPlayed": "total_minutes",
        "is_substitute": "substitute_appearances",
    })
    agg["starts"] = agg["matches_played"] - agg["substitute_appearances"]
    agg["minutes_per_match"] = agg["total_minutes"] / agg["matches_played"]

    # Stats numéricas a promediar por 90 min
    per90_cols = [
        "goals", "expectedGoals", "expectedAssists", "totalShots",
        "onTargetScoringAttempt", "keyPass", "bigChanceCreated",
        "totalTackle", "interceptionWon", "ballRecovery", "totalClearance",
        "fouls", "wasFouled", "duelWon", "aerialWon",
        "saves", "goalsPrevented", "keeperSaveValue",
        "passes_attempted", "passes_completed",
    ]
    # Solo columnas que existan
    per90_cols = [c for c in per90_cols if c in df.columns]

    for col in per90_cols:
        total = df.groupby("player_id")[col].sum().reset_index()
        total.columns = ["player_id", f"total_{col}"]
        agg = agg.merge(total, on="player_id", how="left")
        agg[f"{col}_per_90"] = agg[f"total_{col}"] / agg["total_minutes"] * 90
        agg = agg.drop(columns=[f"total_{col}"])

    # Rating promedio ponderado por minutos
    rating_sum = df.groupby("player_id").apply(
        lambda g: (g["rating"] * g["minutesPlayed"]).sum() / g["minutesPlayed"].sum()
        if g["minutesPlayed"].sum() > 0 else np.nan
    ).reset_index(name="weighted_rating")
    agg = agg.merge(rating_sum, on="player_id", how="left")

    logger.info("player_tournament_agg: %d jugadores x %d columnas", len(agg), len(agg.columns))
    return agg


# =============================================================================
# 3. POSITION COMPARISON
# =============================================================================
def build_position_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dataset comparativo por posición.
    Para cada posición (G, D, M, F) calcula percentiles de métricas clave.
    """
    logger.info("Construyendo position_comparison...")

    # Métricas relevantes por posición
    all_metrics = [
        "rating", "pass_accuracy_pct", "tackle_success_pct",
        "aerial_success_pct", "duel_success_pct", "shot_accuracy_pct",
        "xg_efficiency", "xa_per_90", "key_passes_per_90",
        "defensive_actions_per_90", "fouls_per_90", "km_per_90",
        "sprints_per_90", "progression_per_carry",
    ]
    # Filtrar solo las que existan
    metrics = [c for c in all_metrics if c in df.columns]

    rows = []
    for pos in ["G", "D", "M", "F"]:
        pos_df = df[df["position"] == pos]
        if pos_df.empty:
            continue

        row = {"position": pos, "count": len(pos_df)}
        for m in metrics:
            vals = pos_df[m].dropna()
            if len(vals) == 0:
                continue
            row[f"{m}_mean"] = vals.mean()
            row[f"{m}_median"] = vals.median()
            row[f"{m}_p25"] = vals.quantile(0.25)
            row[f"{m}_p75"] = vals.quantile(0.75)
            row[f"{m}_p90"] = vals.quantile(0.90)
            row[f"{m}_std"] = vals.std()

        rows.append(row)

    result = pd.DataFrame(rows)
    logger.info("position_comparison: %d posiciones x %d columnas", len(result), len(result.columns))
    return result


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
    logger.info("INICIANDO CAPA GOLD — Player Stats")
    logger.info("=" * 60)

    # 1. Carga y limpieza
    player_df = load_and_clean_player_stats()
    save_gold(player_df, "player_match_stats")

    # 2. Agregado por jugador
    player_agg = build_player_tournament_agg(player_df)
    save_gold(player_agg, "player_tournament_agg")

    # 3. Comparativo por posición
    position_comp = build_position_comparison(player_df)
    save_gold(position_comp, "position_comparison")

    logger.info("=" * 60)
    logger.info("CAPA GOLD DE JUGADORES COMPLETADA")
    logger.info("Archivos en: %s", GOLD_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
