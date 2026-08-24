from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse

import pandas as pd


COLLECTION_METADATA_URL = "https://api-production.data.gov.sg/v2/public/api/collections/{collection_id}/metadata"
COLLECTION_WITH_DATASETS_URL = "https://api-production.data.gov.sg/v2/public/api/collections/{collection_id}/metadata?withDatasetMetadata=true"
INITIATE_DOWNLOAD_URL = "https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/initiate-download"
POLL_DOWNLOAD_URL = "https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"
logger = logging.getLogger(__name__)
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
CSV_CHUNK_SIZE = 100_000


def fetch_json(url: str, retries: int = 5) -> dict:
    """Fetch JSON with simple retry handling for public API rate limits."""
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "hdb-resale-etl/1.0"})
    for attempt in range(retries + 1):
        try:
            logger.debug("Fetching JSON: %s", url)
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code != 429 or attempt == retries:
                logger.exception("Failed to fetch JSON from %s", url)
                raise
            retry_after = error.headers.get("Retry-After")
            wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 15 * (attempt + 1)
            logger.warning("Rate limited by API. Retrying in %s seconds. URL=%s", wait_seconds, url)
            time.sleep(wait_seconds)
    raise RuntimeError(f"Unable to fetch JSON from {url}")


def discover_dataset_ids(collection_id: str) -> list[str]:
    payload = fetch_json(COLLECTION_METADATA_URL.format(collection_id=collection_id))
    dataset_ids = payload["data"]["collectionMetadata"]["childDatasets"]
    logger.info("Discovered %s child datasets for collection %s", len(dataset_ids), collection_id)
    return dataset_ids


def discover_dataset_ids_for_period(collection_id: str, start_month: str, end_month: str) -> list[str]:
    """Select only child datasets whose coverage overlaps the assignment period."""
    logger.info("Discovering datasets for collection=%s period=%s..%s", collection_id, start_month, end_month)
    payload = fetch_json(COLLECTION_WITH_DATASETS_URL.format(collection_id=collection_id))
    dataset_metadata = payload["data"].get("datasetMetadata") or []
    if not dataset_metadata:
        return discover_dataset_ids(collection_id)

    start = pd.Period(start_month, freq="M")
    end = pd.Period(end_month, freq="M")
    selected = []
    for dataset in dataset_metadata:
        coverage_start = _period_from_timestamp(dataset["coverageStart"])
        coverage_end = _period_from_timestamp(dataset["coverageEnd"])
        if coverage_start <= end and coverage_end >= start:
            selected.append(dataset["datasetId"])
            logger.debug("Selected dataset %s covering %s..%s", dataset["datasetId"], coverage_start, coverage_end)
    logger.info("Selected %s datasets for requested period", len(selected))
    return selected


def _period_from_timestamp(value: str) -> pd.Period:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return pd.Period(parsed.strftime("%Y-%m"), freq="M")


def _download_url(payload: dict) -> str | None:
    data = payload.get("data") or {}
    return data.get("url") or data.get("downloadUrl") or data.get("downloadURL")


def get_download_url(dataset_id: str, attempts: int = 10, wait_seconds: float = 2.0) -> str:
    """Use data.gov.sg initiate/poll flow to obtain the real CSV download URL."""
    logger.info("Initiating download for dataset %s", dataset_id)
    fetch_json(INITIATE_DOWNLOAD_URL.format(dataset_id=dataset_id))
    for attempt in range(1, attempts + 1):
        payload = fetch_json(POLL_DOWNLOAD_URL.format(dataset_id=dataset_id))
        url = _download_url(payload)
        if url:
            logger.info("Download URL ready for dataset %s after %s poll attempt(s)", dataset_id, attempt)
            return url
        logger.debug("Download URL not ready for dataset %s. Poll attempt=%s", dataset_id, attempt)
        time.sleep(wait_seconds)
    raise TimeoutError(f"Download URL was not ready for dataset {dataset_id}")


def download_dataset(dataset_id: str, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = get_download_url(dataset_id)
    suffix = Path(urlparse(url).path).suffix or ".csv"
    output_path = raw_dir / f"{dataset_id}{suffix}"
    tmp_path = output_path.with_suffix(output_path.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "hdb-resale-etl/1.0"})
    bytes_written = 0
    with urllib.request.urlopen(request, timeout=300) as response, tmp_path.open("wb") as handle:
        expected_length = response.headers.get("Content-Length")
        while True:
            chunk = response.read(DOWNLOAD_CHUNK_SIZE)
            if not chunk:
                break
            handle.write(chunk)
            bytes_written += len(chunk)
    if expected_length and bytes_written != int(expected_length):
        tmp_path.unlink(missing_ok=True)
        raise IOError(f"Downloaded {bytes_written} bytes for {dataset_id}; expected {expected_length} bytes")
    os.replace(tmp_path, output_path)
    logger.info("Downloaded dataset %s to %s bytes=%s", dataset_id, output_path, bytes_written)
    return output_path


def download_collection(collection_id: str, raw_dir: Path, start_month: str, end_month: str) -> list[Path]:
    dataset_ids = discover_dataset_ids_for_period(collection_id, start_month, end_month)
    paths = [download_dataset(dataset_id, raw_dir) for dataset_id in dataset_ids]
    logger.info("Downloaded %s dataset file(s) into %s", len(paths), raw_dir)
    return paths


def load_raw_files(raw_dir: Path, chunksize: int = CSV_CHUNK_SIZE) -> pd.DataFrame:
    """Load all raw CSV files and retain source metadata for audit/debugging."""
    frames = []
    for csv_path in sorted(raw_dir.glob("*.csv")):
        logger.info("Loading raw CSV: %s", csv_path)
        next_source_row = 2
        for frame in pd.read_csv(csv_path, dtype=str, keep_default_na=False, chunksize=chunksize):
            frame["source_file"] = csv_path.name
            frame["source_row_number"] = range(next_source_row, next_source_row + len(frame))
            next_source_row += len(frame)
            logger.debug("Loaded chunk rows=%s from %s with columns=%s", len(frame), csv_path.name, list(frame.columns))
            frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"No raw CSV files found in {raw_dir}")
    raw_combined = pd.concat(frames, ignore_index=True, sort=False)
    logger.info("Combined raw source files rows=%s columns=%s", len(raw_combined), len(raw_combined.columns))
    return raw_combined
