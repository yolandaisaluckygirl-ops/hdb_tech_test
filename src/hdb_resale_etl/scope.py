from __future__ import annotations

import logging

import pandas as pd

from hdb_resale_etl.quality import is_valid_month_format

logger = logging.getLogger(__name__)


def split_assignment_scope(df: pd.DataFrame, start_month: str, end_month: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split raw combined data into scoped master rows and non-failed out-of-scope rows."""
    strict_format = df["month"].apply(is_valid_month_format)
    parseable = pd.to_datetime(df["month"], format="%Y-%m", errors="coerce").notna()
    valid_month = strict_format & parseable
    in_scope = df["month"].between(start_month, end_month)

    out_of_scope = valid_month & ~in_scope
    keep_for_master = ~out_of_scope

    scoped = df[keep_for_master].copy()
    excluded = df[out_of_scope].copy()
    logger.info(
        "Assignment scope filter complete: master_rows=%s scope_excluded_rows=%s period=%s..%s",
        len(scoped),
        len(excluded),
        start_month,
        end_month,
    )
    return scoped.reset_index(drop=True), excluded.reset_index(drop=True)