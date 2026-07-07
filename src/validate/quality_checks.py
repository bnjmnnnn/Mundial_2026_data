"""
Validación de calidad de datos (Data Quality Checks).

Uso:
    python -m src.validate.quality_checks

Genera:
    - data/quality_report.json — Resultado machine-readable
    - data/quality_report.md  — Resumen human-readable

Validaciones:
    1. Existencia de archivos silver/gold
    2. Columnas obligatorias sin nulos
    3. Rangos razonables (posesión 0-100, goles >= 0, etc.)
    4. Cardinalidad esperada (filas por tabla)
    5. Consistencia entre tablas (match_id presente en todas)
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

SILVER_DIR = config.SILVER_DATA_PATH
GOLD_DIR = config.GOLD_DATA_PATH
OUTPUT_DIR = Path("data")

# ---------------------------------------------------------------------------
# Configuración de validaciones
# ---------------------------------------------------------------------------
REQUIRED_FILES = {
    "silver": ["matches.csv", "team_stats.csv", "events_incidents.csv"],
    "gold": ["team_features.csv", "match_ml_dataset.csv", "team_tournament_agg.csv"],
}

REQUIRED_COLS = {
    "matches": ["match_id", "home_team_name", "away_team_name", "home_score", "away_score"],
    "team_stats": ["match_id", "team", "is_home", "ballPossession"],
    "team_features": ["match_id", "team", "goals_scored", "goals_conceded", "result"],
    "match_ml_dataset": ["match_id", "home_team_name", "away_team_name", "result_1x2"],
}

RANGE_CHECKS = {
    "matches": {
        "home_score": (0, 20),
        "away_score": (0, 20),
        "round": (1, 20),
    },
    "team_stats": {
        "ballPossession": (0, 100),
        "expectedGoals": (0, 10),
    },
    "team_features": {
        "goals_scored": (0, 20),
        "goals_conceded": (0, 20),
        "possession_pct": (0, 100),
    },
}

CARDINALITY = {
    "matches": {"min": 1, "max": 200},
    "team_stats": {"min": 2, "max": 400},
    "events_incidents": {"min": 1, "max": 5000},
    "team_features": {"min": 2, "max": 400},
    "match_ml_dataset": {"min": 1, "max": 200},
    "team_tournament_agg": {"min": 1, "max": 60},
}


# =============================================================================
# HELPERS
# =============================================================================
def load_csv(name: str, directory: Path) -> pd.DataFrame:
    """Carga un CSV de forma segura."""
    path = directory / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def check_file_exists(name: str, directory: Path) -> Tuple[bool, str]:
    """Verifica que un archivo CSV exista."""
    path = directory / f"{name}.csv"
    if path.exists():
        return True, f"✅ {name}.csv encontrado"
    return False, f"❌ {name}.csv NO encontrado en {directory}"


def check_required_cols(df: pd.DataFrame, name: str) -> List[dict]:
    """Verifica columnas obligatorias sin nulos."""
    results = []
    cols = REQUIRED_COLS.get(name, [])
    for col in cols:
        if col not in df.columns:
            results.append({"column": col, "status": "MISSING", "nulls": None})
            continue
        null_count = df[col].isna().sum()
        null_pct = null_count / len(df) * 100 if len(df) > 0 else 0
        status = "PASS" if null_count == 0 else "WARN" if null_pct < 5 else "FAIL"
        results.append({
            "column": col,
            "status": status,
            "nulls": int(null_count),
            "null_pct": round(null_pct, 2),
        })
    return results


def check_ranges(df: pd.DataFrame, name: str) -> List[dict]:
    """Valida rangos de columnas numéricas."""
    results = []
    checks = RANGE_CHECKS.get(name, {})
    for col, (min_val, max_val) in checks.items():
        if col not in df.columns:
            continue
        # Solo valores no nulos
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) == 0:
            continue
        out_of_range = ((series < min_val) | (series > max_val)).sum()
        status = "PASS" if out_of_range == 0 else "FAIL"
        results.append({
            "column": col,
            "status": status,
            "min": float(series.min()) if len(series) > 0 else None,
            "max": float(series.max()) if len(series) > 0 else None,
            "expected_range": [min_val, max_val],
            "out_of_range": int(out_of_range),
        })
    return results


def check_cardinality(df: pd.DataFrame, name: str) -> dict:
    """Verifica que el número de filas esté dentro de lo esperado."""
    n = len(df)
    expected = CARDINALITY.get(name, {"min": 0, "max": 999999})
    status = "PASS" if expected["min"] <= n <= expected["max"] else "FAIL"
    return {
        "table": name,
        "rows": n,
        "expected": expected,
        "status": status,
    }


def check_consistency(matches: pd.DataFrame, team_stats: pd.DataFrame) -> List[dict]:
    """Verifica que todos los match_id de matches existan en team_stats."""
    results = []
    if matches.empty or team_stats.empty:
        return results

    match_ids_matches = set(matches["match_id"].dropna().astype(int))
    match_ids_stats = set(team_stats["match_id"].dropna().astype(int))

    missing = match_ids_matches - match_ids_stats
    status = "PASS" if len(missing) == 0 else "FAIL"
    results.append({
        "check": "match_id en team_stats",
        "status": status,
        "missing_ids": sorted(list(missing))[:10],  # max 10
        "total_missing": len(missing),
    })

    # Verificar que cada match tiene exactamente 2 filas en team_stats
    counts = team_stats.groupby("match_id").size()
    wrong = counts[counts != 2]
    status2 = "PASS" if len(wrong) == 0 else "FAIL"
    results.append({
        "check": "2 filas por match en team_stats",
        "status": status2,
        "wrong_matches": sorted(list(wrong.index))[:10],
        "total_wrong": len(wrong),
    })

    return results


# =============================================================================
# MAIN
# =============================================================================
def main():
    logger.info("=" * 60)
    logger.info("VALIDACIÓN DE CALIDAD DE DATOS")
    logger.info("=" * 60)

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "overall_status": "PASS",
        "checks": [],
    }

    all_pass = True

    # 1. Existencia de archivos
    logger.info("\n[1] Verificando existencia de archivos...")
    for layer, files in REQUIRED_FILES.items():
        dir_path = SILVER_DIR if layer == "silver" else GOLD_DIR
        for fname in files:
            name = fname.replace(".csv", "")
            ok, msg = check_file_exists(name, dir_path)
            report["checks"].append({"category": "file_exists", "table": name, "status": "PASS" if ok else "FAIL", "message": msg})
            if not ok:
                all_pass = False
                logger.error(msg)
            else:
                logger.info(msg)

    # 2. Cardinalidad + columnas + rangos
    logger.info("\n[2] Validando contenido de tablas...")
    tables_to_check = [
        ("matches", SILVER_DIR),
        ("team_stats", SILVER_DIR),
        ("events_incidents", SILVER_DIR),
        ("team_features", GOLD_DIR),
        ("match_ml_dataset", GOLD_DIR),
        ("team_tournament_agg", GOLD_DIR),
    ]

    loaded = {}
    for name, dir_path in tables_to_check:
        df = load_csv(name, dir_path)
        loaded[name] = df

        # Cardinalidad
        card = check_cardinality(df, name)
        report["checks"].append({"category": "cardinality", **card})
        if card["status"] != "PASS":
            all_pass = False
            logger.error("❌ %s: %d filas (esperado %s)", name, card["rows"], card["expected"])
        else:
            logger.info("✅ %s: %d filas", name, card["rows"])

        if df.empty:
            continue

        # Columnas obligatorias
        col_results = check_required_cols(df, name)
        for r in col_results:
            report["checks"].append({"category": "required_cols", "table": name, **r})
            if r["status"] == "FAIL":
                all_pass = False
                logger.error("❌ %s.%s: %d nulos", name, r["column"], r.get("nulls", 0))
            elif r["status"] == "WARN":
                logger.warning("⚠️ %s.%s: %.1f%% nulos", name, r["column"], r.get("null_pct", 0))

        # Rangos
        range_results = check_ranges(df, name)
        for r in range_results:
            report["checks"].append({"category": "range", "table": name, **r})
            if r["status"] == "FAIL":
                all_pass = False
                logger.error("❌ %s.%s: %d fuera de rango %s", name, r["column"], r["out_of_range"], r["expected_range"])

    # 3. Consistencia entre tablas
    logger.info("\n[3] Verificando consistencia entre tablas...")
    consistency = check_consistency(loaded.get("matches", pd.DataFrame()), loaded.get("team_stats", pd.DataFrame()))
    for c in consistency:
        report["checks"].append({"category": "consistency", **c})
        if c["status"] != "PASS":
            all_pass = False
            logger.error("❌ %s: %s", c["check"], c)
        else:
            logger.info("✅ %s", c["check"])

    # 4. Resultado global
    report["overall_status"] = "PASS" if all_pass else "FAIL"
    logger.info("\n" + "=" * 60)
    if all_pass:
        logger.info("✅ VALIDACIÓN COMPLETADA — Todos los checks pasaron")
    else:
        logger.error("❌ VALIDACIÓN FALLÓ — Revisar checks marcados")
    logger.info("=" * 60)

    # Guardar reportes
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUTPUT_DIR / "quality_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Reporte JSON: %s", json_path)

    md_path = OUTPUT_DIR / "quality_report.md"
    generate_markdown_report(report, md_path)
    logger.info("Reporte MD: %s", md_path)

    return 0 if all_pass else 1


def generate_markdown_report(report: dict, path: Path):
    """Genera un resumen en Markdown del reporte."""
    lines = [
        "# Data Quality Report — Mundial 2026 Pipeline",
        "",
        f"**Timestamp:** {report['timestamp']}",
        f"**Overall Status:** {report['overall_status']}",
        "",
        "## Resumen por Categoría",
        "",
    ]

    # Agrupar checks por categoría
    by_category = {}
    for check in report["checks"]:
        cat = check["category"]
        by_category.setdefault(cat, []).append(check)

    for cat, checks in by_category.items():
        lines.append(f"### {cat.replace('_', ' ').title()}")
        lines.append("")
        fail_count = sum(1 for c in checks if c.get("status") == "FAIL")
        pass_count = sum(1 for c in checks if c.get("status") == "PASS")
        lines.append(f"- ✅ PASS: {pass_count} | ❌ FAIL: {fail_count}")
        lines.append("")

        for c in checks:
            status = c.get("status", "?")
            emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
            table = c.get("table", c.get("check", ""))
            msg = c.get("message", "")
            lines.append(f"- {emoji} **{table}** — {msg}" if msg else f"- {emoji} **{table}** — {status}")
        lines.append("")

    lines.append("---")
    lines.append("*Generado automáticamente por el pipeline de datos.*")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
