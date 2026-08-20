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

STATISTICAL_COLUMNS = ["month", "town", "flat_type", "flat_model", "storey_range"]
MIN_LEASE_COMMENCE_YEAR = 1960
STOREY_RANGE_PATTERN = re.compile(r"^\d{1,2}\s+TO\s+\d{1,2}$")
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
GARBLED_CHARACTER_PATTERN = re.compile(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
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
    result = df.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = result[column].fillna("").astype(str).str.strip()
    for column in ["town", "flat_type", "flat_model", "storey_range", "street_name", "block"]:
        if column in result.columns:
            result[column] = result[column].str.replace(r"\s+", " ", regex=True).str.upper()
    return result


def recompute_remaining_lease(lease_commence_year: int, as_of_date: date, lease_years: int = 99) -> str:
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


def split_duplicate_keys(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    key_columns = [
        column
        for column in df.columns
        if column not in {"resale_price", "failure_reason", "source_file", "source_row_number"}
    ]
    ranked = df.copy()
    ranked["_resale_price_numeric"] = pd.to_numeric(ranked["resale_price"], errors="coerce")
    ranked["_rank"] = ranked.groupby(key_columns, dropna=False)["_resale_price_numeric"].rank(method="first", ascending=False)
    keep = ranked[ranked["_rank"] == 1].drop(columns=["_rank", "_resale_price_numeric"])
    failed = ranked[ranked["_rank"] > 1].drop(columns=["_rank", "_resale_price_numeric"])
    if not failed.empty:
        failed = failed.assign(failure_reason="duplicate_composite_key_lower_price")
    logger.info("Duplicate key check complete: kept=%s duplicate_failures=%s", len(keep), len(failed))
    return keep.reset_index(drop=True), failed.reset_index(drop=True)


def flag_price_anomalies(df: pd.DataFrame) -> pd.Series:
    prices = pd.to_numeric(df["resale_price"], errors="coerce")
    group_columns = ["month", "town", "flat_type"]
    anomaly = pd.Series(False, index=df.index)
    for _, index in df.groupby(group_columns, dropna=False).groups.items():
        group_prices = prices.loc[index]
        if len(group_prices) < 8:
            continue
        q1 = group_prices.quantile(0.25)
        q3 = group_prices.quantile(0.75)
        iqr = q3 - q1
        lower = max(0, q1 - 3 * iqr)
        upper = q3 + 3 * iqr
        anomaly.loc[index] = (group_prices < lower) | (group_prices > upper)
    return anomaly


def clean_dataset(master_df: pd.DataFrame, start_month: str, end_month: str, as_of_date: date) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    logger.info("Starting quality checks for rows=%s", len(master_df))
    df = normalize_string_columns(master_df)
    failed_frames = []
    working = df.copy()
    working["failure_reason"] = ""
    failure_reasons = pd.Series([[] for _ in range(len(working))], index=working.index, dtype=object)

    missing_column_list = [column for column in REQUIRED_COLUMNS if column not in working.columns]
    if missing_column_list:
        raise ValueError(f"Missing mandatory source columns: {missing_column_list}")

    valid_mask = pd.Series(True, index=working.index)
    required_value_mask = pd.Series(True, index=working.index)
    for column in REQUIRED_COLUMNS:
        valid_required_value = working[column].astype(str).str.strip().ne("")
        _append_reason(failure_reasons, ~valid_required_value, f"missing_required_{column}")
        required_value_mask &= valid_required_value
    valid_mask &= required_value_mask

    text_columns = [column for column in working.columns if column not in GARBLED_CHECK_EXCLUDED_COLUMNS]
    garbled_mask = pd.Series(False, index=working.index)
    for column in text_columns:
        garbled_mask |= working[column].apply(has_garbled_characters)
    _append_reason(failure_reasons, garbled_mask, "garbled_or_control_characters")
    valid_mask &= ~garbled_mask

    valid_month_format = working["month"].apply(is_valid_month_format)
    date_values = pd.to_datetime(working["month"], format="%Y-%m", errors="coerce")
    valid_month = valid_month_format & date_values.notna()
    in_scope_month = working["month"].between(start_month, end_month)
    _append_reason(failure_reasons, ~valid_month, "invalid_month")
    _append_reason(failure_reasons, valid_month & ~in_scope_month, "out_of_scope_month")
    valid_mask &= valid_month & in_scope_month

    for column in STATISTICAL_COLUMNS:
        allowed_values = set(working.loc[working[column].ne(""), column].unique())
        valid_category = working[column].isin(allowed_values) & working[column].ne("")
        _append_reason(failure_reasons, ~valid_category, f"invalid_{column}")
        valid_mask &= valid_category

    valid_storey_range_format = working["storey_range"].apply(is_reasonable_storey_range)
    _append_reason(failure_reasons, ~valid_storey_range_format, "invalid_storey_range_format")
    valid_mask &= valid_storey_range_format

    numeric_area = pd.to_numeric(working["floor_area_sqm"], errors="coerce")
    numeric_price = pd.to_numeric(working["resale_price"], errors="coerce")
    lease_year = pd.to_numeric(working["lease_commence_date"], errors="coerce")
    valid_area = numeric_area.gt(0)
    valid_price = numeric_price.ge(0)
    valid_lease_year = lease_year.between(MIN_LEASE_COMMENCE_YEAR, as_of_date.year)
    _append_reason(failure_reasons, ~valid_area, "invalid_floor_area_sqm")
    _append_reason(failure_reasons, ~valid_price, "invalid_resale_price")
    _append_reason(failure_reasons, ~valid_lease_year, "invalid_lease_commence_date")
    valid_mask &= valid_area & valid_price & valid_lease_year

    invalid = working[~valid_mask].copy()
    if not invalid.empty:
        invalid["failure_reason"] = failure_reasons.loc[invalid.index].apply(lambda reasons: ";".join(reasons))
        failed_frames.append(invalid)
    logger.info("Deterministic validation complete: valid=%s invalid=%s", int(valid_mask.sum()), int((~valid_mask).sum()))

    cleaned = working[valid_mask].copy()
    cleaned["floor_area_sqm"] = numeric_area.loc[cleaned.index].round(2)
    cleaned["resale_price"] = numeric_price.loc[cleaned.index].round(2)
    cleaned["lease_commence_date"] = lease_year.loc[cleaned.index].astype(int)
    cleaned["remaining_lease"] = cleaned["lease_commence_date"].apply(lambda year: recompute_remaining_lease(year, as_of_date))

    cleaned, duplicate_failures = split_duplicate_keys(cleaned.drop(columns=["failure_reason"]))
    if not duplicate_failures.empty:
        failed_frames.append(duplicate_failures)

    dqc_result = pd.concat(
        [
            build_rare_value_dqc(cleaned),
            build_price_anomaly_dqc(cleaned),
        ],
        ignore_index=True,
        sort=False,
    )
    if dqc_result.empty:
        dqc_result = pd.DataFrame(columns=DQC_RESULT_COLUMNS)
    else:
        dqc_result = dqc_result.reindex(columns=DQC_RESULT_COLUMNS)
    if not dqc_result.empty:
        logger.info("DQC result categories: %s", dqc_result["dqc_category"].value_counts().to_dict())

    failed = pd.concat(failed_frames, ignore_index=True, sort=False) if failed_frames else pd.DataFrame(columns=list(working.columns))
    if not failed.empty:
        logger.info("Failed record reasons: %s", failed["failure_reason"].value_counts().to_dict())
    return cleaned.reset_index(drop=True), failed.reset_index(drop=True), dqc_result.reset_index(drop=True)


def _append_reason(reasons: pd.Series, mask: pd.Series, reason: str) -> None:
    for index in reasons[mask.fillna(True)].index:
        reasons.at[index].append(reason)


def build_rare_value_dqc(df: pd.DataFrame, rare_count_threshold: int = 1) -> pd.DataFrame:
    dqc_frames = []
    frequency_columns = [
        column
        for column in df.columns
        if column not in DQC_FREQUENCY_EXCLUDED_COLUMNS
    ]
    total_rows = len(df)
    if total_rows == 0:
        return pd.DataFrame(columns=DQC_RESULT_COLUMNS)

    for column in frequency_columns:
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


def build_price_anomaly_dqc(df: pd.DataFrame) -> pd.DataFrame:
    anomaly_mask = flag_price_anomalies(df)
    anomalies = df[anomaly_mask].copy()
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
