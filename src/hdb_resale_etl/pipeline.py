from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hdb_resale_etl.config import PipelineConfig
from hdb_resale_etl.extract import download_collection, load_raw_files
from hdb_resale_etl.profile import build_profile, write_profile
from hdb_resale_etl.quality import clean_dataset
from hdb_resale_etl.transform import add_hashed_identifier, add_resale_identifier


@dataclass(frozen=True)
class PipelineResult:
    raw_rows: int
    cleaned_rows: int
    transformed_rows: int
    failed_rows: int
    hashed_rows: int
    dqc_result_rows: int
    output_paths: dict[str, Path]


def _write_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def run_pipeline(config: PipelineConfig, *, download: bool = False) -> PipelineResult:
    if download:
        download_collection(config.collection_id, config.raw_dir, config.start_month, config.end_month)

    master = load_raw_files(config.raw_dir)
    profile = build_profile(master)
    cleaned, failed, dqc_result = clean_dataset(master, config.start_month, config.end_month, config.as_of_date)
    transformed = add_resale_identifier(cleaned)
    hashed = add_hashed_identifier(transformed)

    output_paths = {
        "profile": write_profile(profile, config.profile_dir / "master_profile.json"),
        "cleaned": _write_csv(cleaned, config.cleaned_dir / "cleaned_resale_flat_prices.csv"),
        "transformed": _write_csv(transformed, config.transformed_dir / "transformed_resale_flat_prices.csv"),
        "failed": _write_csv(failed, config.failed_dir / "failed_resale_flat_prices.csv"),
        "hashed": _write_csv(hashed, config.hashed_dir / "hashed_resale_flat_prices.csv"),
        "dqc_result": _write_csv(dqc_result, config.dqc_result_dir / "dqc_result.csv"),
    }

    return PipelineResult(
        raw_rows=len(master),
        cleaned_rows=len(cleaned),
        transformed_rows=len(transformed),
        failed_rows=len(failed),
        hashed_rows=len(hashed),
        dqc_result_rows=len(dqc_result),
        output_paths=output_paths,
    )
