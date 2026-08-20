from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    project_root: Path
    collection_id: str = "189"
    start_month: str = "2012-01"
    end_month: str = "2016-12"
    lease_years: int = 99
    as_of_date: date = date.today()
    raw_dir_name: str = "raw"
    cleaned_dir_name: str = "cleaned"
    transformed_dir_name: str = "transformed"
    failed_dir_name: str = "failed"
    hashed_dir_name: str = "hashed"
    dqc_result_dir_name: str = "dqc_result"
    profile_dir_name: str = "profile"

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / self.raw_dir_name

    @property
    def cleaned_dir(self) -> Path:
        return self.data_dir / self.cleaned_dir_name

    @property
    def transformed_dir(self) -> Path:
        return self.data_dir / self.transformed_dir_name

    @property
    def failed_dir(self) -> Path:
        return self.data_dir / self.failed_dir_name

    @property
    def hashed_dir(self) -> Path:
        return self.data_dir / self.hashed_dir_name

    @property
    def dqc_result_dir(self) -> Path:
        return self.data_dir / self.dqc_result_dir_name

    @property
    def profile_dir(self) -> Path:
        return self.data_dir / self.profile_dir_name
