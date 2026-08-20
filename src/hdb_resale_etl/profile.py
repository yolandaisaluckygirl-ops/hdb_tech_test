from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def build_profile(df: pd.DataFrame) -> dict:
    logger.info("Building profile for rows=%s columns=%s", len(df), len(df.columns))
    profile: dict[str, object] = {"row_count": int(len(df)), "columns": {}}
    for column in df.columns:
        series = df[column]
        column_profile = {
            "non_empty_count": int(series.astype(str).str.strip().ne("").sum()),
            "empty_count": int(series.astype(str).str.strip().eq("").sum()),
            "unique_count": int(series.nunique(dropna=False)),
            "sample_values": series.astype(str).drop_duplicates().head(10).tolist(),
        }
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any():
            column_profile["numeric"] = {
                "min": float(numeric.min()),
                "max": float(numeric.max()),
                "mean": float(numeric.mean()),
            }
        profile["columns"][column] = column_profile
    return profile


def write_profile(profile: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    logger.info("Wrote profile to %s", output_path)
    return output_path
