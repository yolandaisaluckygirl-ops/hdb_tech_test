from datetime import date
from pathlib import Path
import sys
import unittest

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hdb_resale_etl.quality import clean_dataset
from hdb_resale_etl.transform import add_hashed_identifier, add_resale_identifier


class TransformTests(unittest.TestCase):
    def test_resale_identifier_uses_first_three_block_digits(self) -> None:
        cases = {
            "19": "019",
            "19A": "019",
            "7": "007",
            "123": "123",
            "1234A": "123",
            "A1234B": "123",
        }
        rows = [_row(block=block, source_row_number=i) for i, block in enumerate(cases, start=2)]

        transformed = add_resale_identifier(pd.DataFrame(rows))

        for block, expected_digits in cases.items():
            actual = transformed.loc[transformed["block"] == block, "resale_identifier"].iloc[0]
            self.assertEqual(actual[1:4], expected_digits)

    def test_resale_identifier_no_numeric_block_uses_zero_fallback(self) -> None:
        transformed = add_resale_identifier(pd.DataFrame([_row(block="ABC")]))

        self.assertEqual(transformed.iloc[0]["resale_identifier"][1:4], "000")

    def test_hash_is_stable_across_run_dates_even_when_remaining_lease_changes(self) -> None:
        master = pd.DataFrame([_row()])
        cleaned_2026, _, _ = clean_dataset(master, date(2026, 8, 20))
        cleaned_2027, _, _ = clean_dataset(master, date(2027, 8, 20))

        hashed_2026 = add_hashed_identifier(cleaned_2026)
        hashed_2027 = add_hashed_identifier(cleaned_2027)

        self.assertNotEqual(cleaned_2026.iloc[0]["remaining_lease"], cleaned_2027.iloc[0]["remaining_lease"])
        self.assertEqual(hashed_2026.iloc[0]["hashed_resale_identifier"], hashed_2027.iloc[0]["hashed_resale_identifier"])

    def test_plain_identifier_collision_still_produces_distinct_hashes(self) -> None:
        cleaned = pd.DataFrame(
            [
                _row(block="19", street_name="ANG MO KIO AVE 3", source_row_number=2),
                _row(block="19", street_name="ANG MO KIO AVE 4", source_row_number=3),
            ]
        )

        transformed = add_resale_identifier(cleaned)
        hashed = add_hashed_identifier(cleaned)

        self.assertEqual(transformed["resale_identifier"].nunique(), 1)
        self.assertEqual(hashed["hashed_resale_identifier"].nunique(), 2)

    def test_hash_is_deterministic_and_sha256_hex(self) -> None:
        cleaned = pd.DataFrame([_row()])

        first = add_hashed_identifier(cleaned).iloc[0]["hashed_resale_identifier"]
        second = add_hashed_identifier(cleaned).iloc[0]["hashed_resale_identifier"]

        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_hashed_output_does_not_contain_plain_resale_identifier(self) -> None:
        hashed = add_hashed_identifier(pd.DataFrame([_row()]))

        self.assertIn("hashed_resale_identifier", hashed.columns)
        self.assertNotIn("resale_identifier", hashed.columns)


def _row(**overrides):
    row = {
        "month": "2012-01",
        "town": "ANG MO KIO",
        "flat_type": "2 ROOM",
        "block": "19",
        "street_name": "ANG MO KIO AVE 3",
        "storey_range": "01 TO 03",
        "floor_area_sqm": 45.0,
        "flat_model": "IMPROVED",
        "lease_commence_date": 1980,
        "remaining_lease": "52 years 4 months",
        "resale_price": 300000.0,
        "source_file": "sample.csv",
        "source_row_number": 2,
    }
    row.update(overrides)
    return row


if __name__ == "__main__":
    unittest.main()