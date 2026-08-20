from __future__ import annotations

from datetime import date
import logging
from math import floor
import re

import pandas as pd


REQUIRED_COLUMNS = [
    "month",
    "town",
    "flat_type",
    "block",
    "street_name",
    "storey_range",
    "floor_area_sqm",
    "flat_model",
    "lease_commence_date",
    "resale_price",
]

CATEGORY_COLUMNS = ["town", "flat_type", "flat_model", "storey_range"]
NORMALIZED_TEXT_COLUMNS = ["town", "flat_type", "flat_model", "storey_range", "street_name", "block"]
MIN_LEASE_COMMENCE_YEAR = 1960
STOREY_RANGE_PATTERN = re.compile(r"^\d{1,2}\s+TO\s+\d{1,2}$")
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
GARBLED_CHARACTER_PATTERN = re.compile(r"[�\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
DQC_FREQUENCY_EXCLUDED_COLUMNS = {"resale_price", "source_file", "source_row_number", "failure_reason"}
GARBLED_CHECK_EXCLUDED_COLUMNS = {"source_file", "source_row_number", "failure_reason"}
DQC_RESULT_COLUMNS = [
    "dqc_category",
    "dqc_field",
    "dqc_value",
    "dqc_rule",
    "record_count",
    "frequency_pct",
    "source_file",
    "source_row_number",
    "month",
    "town",
    "flat_type",
    "flat_model",
    "storey_range",
    "resale_price",
]
logger = logging.getLogger(__name__)


def normalize_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim strings and canonicalize HDB categorical text before validation."""
    result = df.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = result[column].fillna("").astype(str).str.strip()
    for column in NORMALIZED_TEXT_COLUMNS:
        if column in result.columns:
            result[column] = result[column].str.replace(r"\s+", " ", regex=True).str.upper()
    return result


def recompute_remaining_lease(lease_commence_year: int, as_of_date: date, lease_years: int = 99) -> str:
    """Recompute HDB 99-year lease balance, rounded down to years and months."""
    expiry_year = lease_commence_year + lease_years
    months_left = (expiry_year - as_of_date.year) * 12 - as_of_date.month
    months_left = max(months_left, 0)
    years = floor(months_left / 12)
    months = months_left % 12
    return f"{years} years {months} months"


def is_valid_month_format(value: str) -> bool:
    return bool(MONTH_PATTERN.match(str(value)))


def is_reasonable_storey_range(value: str) -> bool:
    value = str(value).strip().upper()
    if not STOREY_RANGE_PATTERN.match(value):
        return False
    lower, upper = [int(part) for part in value.split(" TO ")]
    return lower <= upper


def has_garbled_characters(value: str) -> bool:
    return bool(GARBLED_CHARACTER_PATTERN.search(str(value)))


def clean_dataset(master_df: pd.DataFrame, start_month: str, end_month: str, as_of_date: date) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply deterministic validation, duplicate handling, and DQC review checks."""
    logger.info("Starting quality checks for rows=%s", len(master_df))
    working = normalize_string_columns(master_df)
    _ensure_required_columns(working)

    failure_reasons = _empty_reason_series(working)
    valid_mask = _build_valid_mask(working, start_month, end_month, as_of_date, failure_reasons)

    invalid = _failed_records(working, valid_mask, failure_reasons)
    cleaned = _prepare_cleaned_records(working, valid_mask, as_of_date)
    cleaned, duplicate_failures = split_duplicate_keys(cleaned)

    failed = _combine_failed_records([invalid, duplicate_failures])
    dqc_result = build_dqc_result(cleaned)

    logger.info("Quality stage complete: cleaned=%s failed=%s dqc=%s", len(cleaned), len(failed), len(dqc_result))
    return cleaned.reset_index(drop=True), failed.reset_index(drop=True), dqc_result.reset_index(drop=True)


def _ensure_required_columns(df: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing mandatory source columns: {missing}")


def _empty_reason_series(df: pd.DataFrame) -> pd.Series:
    return pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)


def _build_valid_mask(df: pd.DataFrame, start_month: str, end_month: str, as_of_date: date, reasons: pd.Series) -> pd.Series:
    """Build one deterministic pass/fail mask while collecting row-level failure reasons."""
    valid_mask = pd.Series(True, index=df.index)
    valid_mask &= _check_required_values(df, reasons)
    valid_mask &= _check_garbled_characters(df, reasons)
    valid_mask &= _check_month(df, start_month, end_month, reasons)
    valid_mask &= _check_categories(df, reasons)
    valid_mask &= _check_storey_range(df, reasons)
    valid_mask &= _check_numeric_fields(df, as_of_date, reasons)
    logger.info("Deterministic validation complete: valid=%s invalid=%s", int(valid_mask.sum()), int((~valid_mask).sum()))
    return valid_mask


def _check_required_values(df: pd.DataFrame, reasons: pd.Series) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for column in REQUIRED_COLUMNS:
        column_mask = df[column].astype(str).str.strip().ne("")
        _append_reason(reasons, ~column_mask, f"missing_required_{column}")
        mask &= column_mask
    return mask


def _check_garbled_characters(df: pd.DataFrame, reasons: pd.Series) -> pd.Series:
    garbled = pd.Series(False, index=df.index)
    for column in [c for c in df.columns if c not in GARBLED_CHECK_EXCLUDED_COLUMNS]:
        garbled |= df[column].apply(has_garbled_characters)
    _append_reason(reasons, garbled, "garbled_or_control_characters")
    return ~garbled


def _check_month(df: pd.DataFrame, start_month: str, end_month: str, reasons: pd.Series) -> pd.Series:
    strict_format = df["month"].apply(is_valid_month_format)
    parseable = pd.to_datetime(df["month"], format="%Y-%m", errors="coerce").notna()
    valid_month = strict_format & parseable
    in_scope = df["month"].between(start_month, end_month)
    _append_reason(reasons, ~valid_month, "invalid_month")
    _append_reason(reasons, valid_month & ~in_scope, "out_of_scope_month")
    return valid_month & in_scope


def _check_categories(df: pd.DataFrame, reasons: pd.Series) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for column in CATEGORY_COLUMNS:
        # Current hard rule is non-empty canonical categories; rare/unusual values go to DQC review instead.
        column_mask = df[column].ne("")
        _append_reason(reasons, ~column_mask, f"invalid_{column}")
        mask &= column_mask
    return mask


def _check_storey_range(df: pd.DataFrame, reasons: pd.Series) -> pd.Series:
    mask = df["storey_range"].apply(is_reasonable_storey_range)
    _append_reason(reasons, ~mask, "invalid_storey_range_format")
    return mask


def _check_numeric_fields(df: pd.DataFrame, as_of_date: date, reasons: pd.Series) -> pd.Series:
    area = pd.to_numeric(df["floor_area_sqm"], errors="coerce")
    price = pd.to_numeric(df["resale_price"], errors="coerce")
    lease_year = pd.to_numeric(df["lease_commence_date"], errors="coerce")

    valid_area = area.gt(0)
    valid_price = price.ge(0)
    valid_lease_year = lease_year.between(MIN_LEASE_COMMENCE_YEAR, as_of_date.year)

    _append_reason(reasons, ~valid_area, "invalid_floor_area_sqm")
    _append_reason(reasons, ~valid_price, "invalid_resale_price")
    _append_reason(reasons, ~valid_lease_year, "invalid_lease_commence_date")
    return valid_area & valid_price & valid_lease_year


def _prepare_cleaned_records(df: pd.DataFrame, valid_mask: pd.Series, as_of_date: date) -> pd.DataFrame:
    cleaned = df[valid_mask].copy()
    cleaned["floor_area_sqm"] = pd.to_numeric(cleaned["floor_area_sqm"], errors="coerce").round(2)
    cleaned["resale_price"] = pd.to_numeric(cleaned["resale_price"], errors="coerce").round(2)
    cleaned["lease_commence_date"] = pd.to_numeric(cleaned["lease_commence_date"], errors="coerce").astype(int)
    cleaned["remaining_lease"] = cleaned["lease_commence_date"].apply(lambda year: recompute_remaining_lease(year, as_of_date))
    return cleaned.drop(columns=["failure_reason"], errors="ignore")


def _failed_records(df: pd.DataFrame, valid_mask: pd.Series, reasons: pd.Series) -> pd.DataFrame:
    failed = df[~valid_mask].copy()
    if not failed.empty:
        failed["failure_reason"] = reasons.loc[failed.index].apply(lambda row_reasons: ";".join(row_reasons))
    return failed


def split_duplicate_keys(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep the highest price for duplicate composite keys; fail lower-priced duplicates."""
    key_columns = [c for c in df.columns if c not in {"resale_price", "failure_reason", "source_file", "source_row_number"}]
    ranked = df.assign(_resale_price_numeric=pd.to_numeric(df["resale_price"], errors="coerce"))
    ranked["_rank"] = ranked.groupby(key_columns, dropna=False)["_resale_price_numeric"].rank(method="first", ascending=False)

    keep = ranked[ranked["_rank"] == 1].drop(columns=["_rank", "_resale_price_numeric"])
    failed = ranked[ranked["_rank"] > 1].drop(columns=["_rank", "_resale_price_numeric"])
    if not failed.empty:
        failed = failed.assign(failure_reason="duplicate_composite_key_lower_price")
    logger.info("Duplicate key check complete: kept=%s duplicate_failures=%s", len(keep), len(failed))
    return keep.reset_index(drop=True), failed.reset_index(drop=True)


def build_dqc_result(cleaned: pd.DataFrame) -> pd.DataFrame:
    dqc_result = pd.concat([build_rare_value_dqc(cleaned), build_price_anomaly_dqc(cleaned)], ignore_index=True, sort=False)
    if dqc_result.empty:
        return pd.DataFrame(columns=DQC_RESULT_COLUMNS)

    dqc_result = dqc_result.reindex(columns=DQC_RESULT_COLUMNS)
    logger.info("DQC result categories: %s", dqc_result["dqc_category"].value_counts().to_dict())
    return dqc_result


def build_rare_value_dqc(df: pd.DataFrame, rare_count_threshold: int = 1) -> pd.DataFrame:
    """Flag low-frequency values for review, but do not remove them from cleaned data."""
    total_rows = len(df)
    if total_rows == 0:
        return pd.DataFrame(columns=DQC_RESULT_COLUMNS)

    dqc_frames = []
    for column in [c for c in df.columns if c not in DQC_FREQUENCY_EXCLUDED_COLUMNS]:
        counts = df[column].astype(str).value_counts(dropna=False)
        rare_values = counts[counts <= rare_count_threshold]
        if rare_values.empty:
            continue

        rare_records = df[df[column].astype(str).isin(rare_values.index)].copy()
        rare_records["dqc_category"] = "rare value"
        rare_records["dqc_field"] = column
        rare_records["dqc_value"] = rare_records[column].astype(str)
        rare_records["record_count"] = rare_records["dqc_value"].map(rare_values).astype(int)
        rare_records["frequency_pct"] = (rare_records["record_count"] / total_rows * 100).round(6)
        rare_records["dqc_rule"] = f"{column} frequency count <= {rare_count_threshold}"
        dqc_frames.append(rare_records)

    result = pd.concat(dqc_frames, ignore_index=True, sort=False) if dqc_frames else pd.DataFrame(columns=DQC_RESULT_COLUMNS)
    logger.info("Rare value DQC complete: rows=%s threshold=%s", len(result), rare_count_threshold)
    return result


def flag_price_anomalies(df: pd.DataFrame) -> pd.Series:
    """Flag conservative 3x-IQR price outliers within month/town/flat_type groups."""
    prices = pd.to_numeric(df["resale_price"], errors="coerce")
    anomaly = pd.Series(False, index=df.index)
    for _, index in df.groupby(["month", "town", "flat_type"], dropna=False).groups.items():
        group_prices = prices.loc[index]
        if len(group_prices) < 8:
            continue
        q1 = group_prices.quantile(0.25)
        q3 = group_prices.quantile(0.75)
        iqr = q3 - q1
        anomaly.loc[index] = (group_prices < max(0, q1 - 3 * iqr)) | (group_prices > q3 + 3 * iqr)
    return anomaly


def build_price_anomaly_dqc(df: pd.DataFrame) -> pd.DataFrame:
    anomalies = df[flag_price_anomalies(df)].copy()
    if anomalies.empty:
        return pd.DataFrame(columns=DQC_RESULT_COLUMNS)

    anomalies["dqc_category"] = "anomaly resale price"
    anomalies["dqc_field"] = "resale_price"
    anomalies["dqc_value"] = anomalies["resale_price"].astype(str)
    anomalies["record_count"] = ""
    anomalies["frequency_pct"] = ""
    anomalies["dqc_rule"] = "3x IQR outlier within month + town + flat_type"
    logger.info("Price anomaly DQC complete: rows=%s", len(anomalies))
    return anomalies


def _combine_failed_records(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    failed = pd.concat(non_empty, ignore_index=True, sort=False)
    logger.info("Failed record reasons: %s", failed["failure_reason"].value_counts().to_dict())
    return failed


def _append_reason(reasons: pd.Series, mask: pd.Series, reason: str) -> None:
    for index in reasons[mask.fillna(True)].index:
        reasons.at[index].append(reason)
