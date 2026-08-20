from __future__ import annotations

import json
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


def fetch_json(url: str, retries: int = 5) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "hdb-resale-etl/1.0"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code != 429 or attempt == retries:
                raise
            retry_after = error.headers.get("Retry-After")
            wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 15 * (attempt + 1)
            time.sleep(wait_seconds)
    raise RuntimeError(f"Unable to fetch JSON from {url}")


def discover_dataset_ids(collection_id: str) -> list[str]:
    payload = fetch_json(COLLECTION_METADATA_URL.format(collection_id=collection_id))
    return payload["data"]["collectionMetadata"]["childDatasets"]


def discover_dataset_ids_for_period(collection_id: str, start_month: str, end_month: str) -> list[str]:
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
    return selected


def _period_from_timestamp(value: str) -> pd.Period:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return pd.Period(parsed.strftime("%Y-%m"), freq="M")


def _download_url(payload: dict) -> str | None:
    data = payload.get("data") or {}
    return data.get("url") or data.get("downloadUrl") or data.get("downloadURL")


def get_download_url(dataset_id: str, attempts: int = 10, wait_seconds: float = 2.0) -> str:
    fetch_json(INITIATE_DOWNLOAD_URL.format(dataset_id=dataset_id))
    for _ in range(attempts):
        payload = fetch_json(POLL_DOWNLOAD_URL.format(dataset_id=dataset_id))
        url = _download_url(payload)
        if url:
            return url
        time.sleep(wait_seconds)
    raise TimeoutError(f"Download URL was not ready for dataset {dataset_id}")


def download_dataset(dataset_id: str, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = get_download_url(dataset_id)
    suffix = Path(urlparse(url).path).suffix or ".csv"
    output_path = raw_dir / f"{dataset_id}{suffix}"
    request = urllib.request.Request(url, headers={"User-Agent": "hdb-resale-etl/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response, output_path.open("wb") as handle:
        handle.write(response.read())
    return output_path


def download_collection(collection_id: str, raw_dir: Path, start_month: str, end_month: str) -> list[Path]:
    dataset_ids = discover_dataset_ids_for_period(collection_id, start_month, end_month)
    return [download_dataset(dataset_id, raw_dir) for dataset_id in dataset_ids]


def load_raw_files(raw_dir: Path) -> pd.DataFrame:
    frames = []
    for csv_path in sorted(raw_dir.glob("*.csv")):
        frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        frame["source_file"] = csv_path.name
        frame["source_row_number"] = range(2, len(frame) + 2)
        frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"No raw CSV files found in {raw_dir}")
    return pd.concat(frames, ignore_index=True, sort=False)
