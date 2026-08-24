from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
STOREY_RANGE_PATTERN = re.compile(r"^\d{1,2}\s+TO\s+\d{1,2}$")
NUMERIC_PROFILE_COLUMNS = {"floor_area_sqm", "lease_commence_date", "resale_price"}
DUPLICATE_KEY_EXCLUDED_COLUMNS = {"resale_price", "source_file", "source_row_number"}
CATEGORY_PROFILE_COLUMNS = ["town", "flat_type", "flat_model", "storey_range"]


def build_profile(df: pd.DataFrame) -> dict:
    logger.info("Building profile for rows=%s columns=%s", len(df), len(df.columns))
    profile: dict[str, object] = {
        "row_count": int(len(df)),
        "columns": {},
        "duplicate_key_statistics": _duplicate_key_statistics(df),
        "category_domain_tables": _category_domain_tables(df),
    }
    for column in df.columns:
        series = df[column]
        missing_mask = _missing_mask(series)
        non_missing = series[~missing_mask]
        column_profile = {
            "non_empty_count": int((~missing_mask).sum()),
            "empty_count": int(missing_mask.sum()),
            "unique_count": int(non_missing.nunique(dropna=True)),
            "sample_values": [_json_safe_value(value) for value in non_missing.drop_duplicates().head(10).tolist()],
            "top_values": _top_values(series, missing_mask),
        }
        numeric = pd.to_numeric(series, errors="coerce")
        numeric_non_missing = numeric[~missing_mask]
        if column in NUMERIC_PROFILE_COLUMNS or numeric_non_missing.notna().any():
            quantiles = numeric_non_missing.dropna().quantile([0.25, 0.5, 0.75]).to_dict()
            column_profile["numeric"] = {
                "parse_failure_count": int((~missing_mask & numeric.isna()).sum()),
                "min": _json_safe_value(numeric_non_missing.min()),
                "max": _json_safe_value(numeric_non_missing.max()),
                "mean": _json_safe_value(numeric_non_missing.mean()),
                "p25": _json_safe_value(quantiles.get(0.25)),
                "median": _json_safe_value(quantiles.get(0.5)),
                "p75": _json_safe_value(quantiles.get(0.75)),
            }
        format_failures = _format_failure_count(column, series, missing_mask)
        if format_failures is not None:
            column_profile["format_failure_count"] = format_failures
        profile["columns"][column] = column_profile
    return profile


def write_profile(profile: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2, allow_nan=False), encoding="utf-8")
    logger.info("Wrote profile to %s", output_path)
    return output_path


def _missing_mask(series: pd.Series) -> pd.Series:
    string_values = series.astype("string")
    return series.isna() | string_values.str.strip().eq("")


def _top_values(series: pd.Series, missing_mask: pd.Series, limit: int = 10) -> list[dict[str, Any]]:
    total = int((~missing_mask).sum())
    if total == 0:
        return []
    counts = series[~missing_mask].astype("string").str.strip().value_counts(dropna=True).head(limit)
    return [
        {
            "value": _json_safe_value(value),
            "count": int(count),
            "frequency_pct": round(float(count / total * 100), 6),
        }
        for value, count in counts.items()
    ]


def _format_failure_count(column: str, series: pd.Series, missing_mask: pd.Series) -> int | None:
    values = series.astype("string").str.strip()
    if column == "month":
        strict = values.str.match(MONTH_PATTERN, na=False)
        parseable = pd.to_datetime(values, format="%Y-%m", errors="coerce").notna()
        return int((~missing_mask & ~(strict & parseable)).sum())
    if column == "storey_range":
        upper = values.str.upper()
        strict = upper.str.match(STOREY_RANGE_PATTERN, na=False)
        bounds = upper.str.extract(r"^(\d{1,2})\s+TO\s+(\d{1,2})$")
        lower = pd.to_numeric(bounds[0], errors="coerce")
        higher = pd.to_numeric(bounds[1], errors="coerce")
        reasonable = strict & lower.le(higher)
        return int((~missing_mask & ~reasonable).sum())
    if column in NUMERIC_PROFILE_COLUMNS:
        numeric = pd.to_numeric(series, errors="coerce")
        return int((~missing_mask & numeric.isna()).sum())
    return None


def _duplicate_key_statistics(df: pd.DataFrame) -> dict[str, Any]:
    key_columns = [column for column in df.columns if column not in DUPLICATE_KEY_EXCLUDED_COLUMNS]
    if not key_columns or df.empty:
        return {"key_columns": key_columns, "duplicate_group_count": 0, "duplicate_row_count": 0}
    duplicate_mask = df.duplicated(subset=key_columns, keep=False)
    duplicate_groups = int(df.loc[duplicate_mask, key_columns].drop_duplicates().shape[0])
    return {
        "key_columns": key_columns,
        "duplicate_group_count": duplicate_groups,
        "duplicate_row_count": int(duplicate_mask.sum()),
    }


def _category_domain_tables(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    domains: dict[str, list[dict[str, Any]]] = {}
    for column in [c for c in CATEGORY_PROFILE_COLUMNS if c in df.columns]:
        values = df[column]
        missing = _missing_mask(values)
        total = int((~missing).sum())
        if total == 0:
            domains[column] = []
            continue
        working = df.loc[~missing, [column]].copy()
        working["_domain_value"] = values[~missing].astype("string").str.strip().str.upper()
        if "month" in df.columns:
            working["month"] = df.loc[~missing, "month"].astype("string")
        counts = working["_domain_value"].value_counts(dropna=True)
        rows = []
        for value, count in counts.items():
            value_rows = working[working["_domain_value"] == value]
            rows.append(
                {
                    "value": _json_safe_value(value),
                    "record_count": int(count),
                    "frequency_pct": round(float(count / total * 100), 6),
                    "first_month": _json_safe_value(value_rows["month"].min()) if "month" in value_rows else None,
                    "last_month": _json_safe_value(value_rows["month"].max()) if "month" in value_rows else None,
                }
            )
        domains[column] = rows
    return domains


def _json_safe_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value
