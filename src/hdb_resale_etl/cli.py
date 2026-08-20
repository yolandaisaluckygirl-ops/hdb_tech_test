from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from hdb_resale_etl.config import PipelineConfig
from hdb_resale_etl.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the HDB resale flat prices ETL pipeline.")
    parser.add_argument("--project-root", default=Path.cwd(), type=Path)
    parser.add_argument("--download", action="store_true", help="Download raw files from data.gov.sg first.")
    parser.add_argument("--collection-id", default="189")
    parser.add_argument("--start-month", default="2012-01")
    parser.add_argument("--end-month", default="2016-12")
    parser.add_argument("--as-of-date", default=date.today().isoformat(), help="YYYY-MM-DD date for remaining lease calculation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = PipelineConfig(
        project_root=args.project_root,
        collection_id=args.collection_id,
        start_month=args.start_month,
        end_month=args.end_month,
        as_of_date=date.fromisoformat(args.as_of_date),
    )
    result = run_pipeline(config, download=args.download)
    print(f"Raw rows: {result.raw_rows}")
    print(f"Cleaned rows: {result.cleaned_rows}")
    print(f"Transformed rows: {result.transformed_rows}")
    print(f"Failed rows: {result.failed_rows}")
    print(f"Hashed rows: {result.hashed_rows}")
    print(f"DQC result rows: {result.dqc_result_rows}")
    for name, path in result.output_paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
