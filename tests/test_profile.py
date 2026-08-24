from pathlib import Path
import json
import sys
import tempfile
import unittest

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hdb_resale_etl.profile import build_profile, write_profile


class ProfileTests(unittest.TestCase):
    def test_profile_counts_real_missing_values_and_writes_strict_json(self) -> None:
        df = pd.DataFrame(
            {
                "month": ["2012-01", "bad-month", "2012-03"],
                "remaining_lease": [pd.NA, "", "52 years 4 months"],
                "resale_price": ["300000", "bad-price", "320000"],
                "town": ["ANG MO KIO", "ANG MO KIO", "RARE TOWN"],
                "flat_type": ["2 ROOM", "2 ROOM", "3 ROOM"],
                "flat_model": ["IMPROVED", "IMPROVED", "MODEL A"],
                "storey_range": ["01 TO 03", "03-05", "04 TO 06"],
            }
        )

        profile = build_profile(df)

        self.assertEqual(profile["columns"]["remaining_lease"]["empty_count"], 2)
        self.assertEqual(profile["columns"]["month"]["format_failure_count"], 1)
        self.assertEqual(profile["columns"]["storey_range"]["format_failure_count"], 1)
        self.assertEqual(profile["columns"]["resale_price"]["numeric"]["parse_failure_count"], 1)
        self.assertEqual(profile["columns"]["remaining_lease"]["sample_values"], ["52 years 4 months"])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            write_profile(profile, path)
            json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
