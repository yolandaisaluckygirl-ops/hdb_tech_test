from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

STABLE_BUSINESS_KEY_COLUMNS = [
    "month",
    "town",
    "flat_type",
    "block",
    "street_name",
    "storey_range",
    "floor_area_sqm",
    "flat_model",
    "lease_commence_date",
]

_HASH_EXCLUDED_COLUMNS = {
    "resale_price",
    "remaining_lease",
    "remaining_lease_decade",
    "price_per_sqm",
    "resale_identifier",
    "hashed_resale_identifier",
    "source_file",
    "source_row_number",
    "failure_reason",
}


def _block_digits(block: str) -> str:
    """Use the first three numeric block digits; non-numeric blocks become 000."""
    digits = "".join(re.findall(r"\d", str(block)))
    return digits[:3].zfill(3)


def add_resale_identifier(cleaned: pd.DataFrame) -> pd.DataFrame:
    """Create the assignment-defined plain resale identifier."""
    logger.info("Adding resale identifiers for rows=%s", len(cleaned))
    result = cleaned.copy()
    result["_avg_price"] = result.groupby(["month", "town", "flat_type"])["resale_price"].transform("mean")
    result["_avg_price_digits"] = result["_avg_price"].round().astype(int).astype(str).str.zfill(2).str[:2]
    result["resale_identifier"] = (
        "S"
        + result["block"].apply(_block_digits)
        + result["_avg_price_digits"]
        + result["month"].str[-2:]
        + result["town"].str[:1]
    )
    return result.drop(columns=["_avg_price", "_avg_price_digits"])


def add_hashed_identifier(cleaned: pd.DataFrame) -> pd.DataFrame:
    """Create a stable irreversible identifier from the plain identifier and source business key."""
    logger.info("Adding hashed resale identifiers for rows=%s", len(cleaned))
    _ensure_stable_key_columns(cleaned)
    with_plain_identifier = add_resale_identifier(cleaned)

    result = cleaned.drop(columns=["resale_identifier"], errors="ignore").copy()
    result["hashed_resale_identifier"] = with_plain_identifier.apply(_hash_row, axis=1)
    logger.debug("Hashed identifier sample: %s", result["hashed_resale_identifier"].head(3).tolist())
    return result


def _ensure_stable_key_columns(df: pd.DataFrame) -> None:
    missing = [column for column in STABLE_BUSINESS_KEY_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing stable business key columns for hashing: {missing}")


def _hash_row(row: pd.Series) -> str:
    payload = {
        "resale_identifier": _canonical_value(row["resale_identifier"]),
        "stable_business_key": [
            {"field": column, "value": _canonical_value(row[column])}
            for column in STABLE_BUSINESS_KEY_COLUMNS
        ],
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _canonical_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()