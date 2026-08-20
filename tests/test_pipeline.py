from datetime import date
import tempfile
from pathlib import Path
import sys
import unittest

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hdb_resale_etl.config import PipelineConfig
from hdb_resale_etl.pipeline import run_pipeline


class PipelineTests(unittest.TestCase):
    def test_pipeline_writes_all_mandatory_output_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            raw_dir = tmp_path / "data" / "raw"
            raw_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "month": "2012-01",
                        "town": "Ang Mo Kio",
                        "flat_type": "2 Room",
                        "block": "19",
                        "street_name": "Ang Mo Kio Ave 3",
                        "storey_range": "01 to 03",
                        "floor_area_sqm": "45",
                        "flat_model": "Improved",
                        "lease_commence_date": "1980",
                        "resale_price": "300000",
                    },
                    {
                        "month": "2011-12",
                        "town": "Ang Mo Kio",
                        "flat_type": "2 Room",
                        "block": "20",
                        "street_name": "Ang Mo Kio Ave 3",
                        "storey_range": "01 to 03",
                        "floor_area_sqm": "45",
                        "flat_model": "Improved",
                        "lease_commence_date": "1980",
                        "resale_price": "280000",
                    }
                ]
            ).to_csv(raw_dir / "sample.csv", index=False)

            result = run_pipeline(PipelineConfig(project_root=tmp_path, as_of_date=date(2026, 8, 18)))

            self.assertEqual(result.raw_rows, 2)
            self.assertEqual(result.master_rows, 1)
            self.assertEqual(result.scope_excluded_rows, 1)
            self.assertEqual(result.cleaned_rows, 1)
            self.assertEqual(result.transformed_rows, 1)
            self.assertEqual(result.hashed_rows, 1)
            self.assertGreater(result.dqc_result_rows, 0)
            self.assertTrue(result.output_paths["cleaned"].exists())
            self.assertTrue(result.output_paths["transformed"].exists())
            self.assertTrue(result.output_paths["failed"].exists())
            self.assertTrue(result.output_paths["hashed"].exists())
            hashed_columns = pd.read_csv(result.output_paths["hashed"], nrows=0).columns
            self.assertIn("hashed_resale_identifier", hashed_columns)
            self.assertNotIn("resale_identifier", hashed_columns)
            self.assertTrue(result.output_paths["dqc_result"].exists())
            self.assertTrue(result.output_paths["profile"].exists())


if __name__ == "__main__":
    unittest.main()
