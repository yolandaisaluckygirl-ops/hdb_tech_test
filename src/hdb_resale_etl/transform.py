from __future__ import annotations

import hashlib
import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)


def _block_digits(block: str) -> str:
    digits = "".join(re.findall(r"\d", str(block)))
    return digits[-3:].zfill(3)


def add_resale_identifier(cleaned: pd.DataFrame) -> pd.DataFrame:
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


def add_hashed_identifier(transformed: pd.DataFrame) -> pd.DataFrame:
    logger.info("Adding hashed resale identifiers for rows=%s", len(transformed))
    result = transformed.copy()
    key_columns = [
        column
        for column in result.columns
        if column not in {"source_file", "source_row_number", "hashed_resale_identifier"}
    ]
    hash_input = result[key_columns].astype(str).agg("|".join, axis=1)
    result["hashed_resale_identifier"] = hash_input.apply(lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest())
    logger.debug("Hashed identifier sample: %s", result["hashed_resale_identifier"].head(3).tolist())
    return result
