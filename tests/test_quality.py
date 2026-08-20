from datetime import date
from pathlib import Path
import sys
import unittest

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hdb_resale_etl.quality import (
    build_price_anomaly_dqc,
    build_rare_value_dqc,
    clean_dataset,
    has_garbled_characters,
    is_reasonable_storey_range,
    is_valid_month_format,
    recompute_remaining_lease,
)
from hdb_resale_etl.transform import add_hashed_identifier, add_resale_identifier


class QualityTests(unittest.TestCase):
    def test_recompute_remaining_lease_rounds_down_to_years_and_months(self) -> None:
        self.assertEqual(recompute_remaining_lease(1980, date(2026, 8, 18)), "52 years 4 months")

    def test_clean_dataset_keeps_higher_duplicate_price_and_fails_lower_price(self) -> None:
        master = pd.DataFrame(
            [
                _row(resale_price="300000", source_row_number=2),
                _row(resale_price="320000", source_row_number=3),
                _row(month="2017-01", resale_price="400000", source_row_number=4),
            ]
        )

        cleaned, failed, dqc_result = clean_dataset(master, "2012-01", "2016-12", date(2026, 8, 18))

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned.iloc[0]["resale_price"], 320000)
        self.assertEqual(len(failed), 2)
        self.assertEqual(set(failed["failure_reason"]), {"duplicate_composite_key_lower_price", "out_of_scope_month"})
        self.assertIn("rare value", set(dqc_result["dqc_category"]))

    def test_storey_range_month_and_lease_validation_fail_deterministically(self) -> None:
        master = pd.DataFrame(
            [
                _row(storey_range="01 TO 03", source_row_number=2),
                _row(storey_range="03-05", source_row_number=3),
                _row(month="2012-1", source_row_number=4),
                _row(lease_commence_date="1959", source_row_number=5),
            ]
        )

        cleaned, failed, _dqc_result = clean_dataset(master, "2012-01", "2016-12", date(2026, 8, 18))

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(len(failed), 3)
        self.assertIn("invalid_storey_range_format", set(failed["failure_reason"]))
        self.assertIn("invalid_month", set(failed["failure_reason"]))
        self.assertIn("invalid_lease_commence_date", set(failed["failure_reason"]))

    def test_storey_range_and_month_helpers(self) -> None:
        self.assertTrue(is_reasonable_storey_range("01 TO 03"))
        self.assertTrue(is_reasonable_storey_range("1 TO 3"))
        self.assertFalse(is_reasonable_storey_range("03 TO 01"))
        self.assertFalse(is_reasonable_storey_range("03-05"))
        self.assertTrue(is_valid_month_format("2012-01"))
        self.assertFalse(is_valid_month_format("2012-1"))

    def test_null_and_garbled_character_checks_fail_deterministically(self) -> None:
        master = pd.DataFrame(
            [
                _row(source_row_number=2),
                _row(town="", source_row_number=3),
                _row(street_name="ANG MO KIO AVE \ufffd", source_row_number=4),
            ]
        )

        cleaned, failed, _dqc_result = clean_dataset(master, "2012-01", "2016-12", date(2026, 8, 18))

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(len(failed), 2)
        failure_text = ";".join(failed["failure_reason"].tolist())
        self.assertIn("missing_required_town", failure_text)
        self.assertIn("garbled_or_control_characters", failure_text)
        self.assertTrue(has_garbled_characters("BAD\ufffdTEXT"))
        self.assertTrue(has_garbled_characters("BAD\x01TEXT"))
        self.assertFalse(has_garbled_characters("ANG MO KIO"))

    def test_rare_value_dqc_flags_low_frequency_values_for_review(self) -> None:
        df = pd.DataFrame(
            [
                _row(town="ANG MO KIO", source_row_number=2),
                _row(town="ANG MO KIO", source_row_number=3),
                _row(town="RARE TOWN", source_row_number=4),
            ]
        )

        dqc_result = build_rare_value_dqc(df, rare_count_threshold=1)

        rare_town = dqc_result[(dqc_result["dqc_field"] == "town") & (dqc_result["dqc_value"] == "RARE TOWN")]
        self.assertEqual(len(rare_town), 1)
        self.assertEqual(rare_town.iloc[0]["dqc_category"], "rare value")

    def test_price_anomaly_dqc_flags_price_per_sqm_outlier_for_review(self) -> None:
        rows = [
            _row(resale_price=str(price), remaining_lease="46 years 4 months", source_row_number=i)
            for i, price in enumerate([300000] * 8 + [9999999], start=2)
        ]
        df = pd.DataFrame(rows)

        dqc_result = build_price_anomaly_dqc(df)

        self.assertEqual(len(dqc_result), 1)
        self.assertEqual(dqc_result.iloc[0]["dqc_category"], "anomaly resale price")
        self.assertEqual(dqc_result.iloc[0]["dqc_field"], "price_per_sqm")
        self.assertEqual(dqc_result.iloc[0]["remaining_lease_decade"], "40-49 years")
        self.assertIn("remaining_lease_decade", dqc_result.iloc[0]["dqc_rule"])

    def test_resale_identifier_and_hash_are_created(self) -> None:
        cleaned = pd.DataFrame([_row(block="19A", resale_price=230000), _row(block="7", resale_price=230000)])

        transformed = add_resale_identifier(cleaned)
        hashed = add_hashed_identifier(transformed)

        self.assertEqual(transformed.iloc[0]["resale_identifier"], "S0192301A")
        self.assertEqual(transformed.iloc[1]["resale_identifier"], "S0072301A")
        self.assertEqual(len(hashed.iloc[0]["hashed_resale_identifier"]), 64)
        self.assertNotEqual(hashed.iloc[0]["hashed_resale_identifier"], transformed.iloc[0]["resale_identifier"])
        self.assertEqual(hashed["hashed_resale_identifier"].nunique(), 2)


def _row(**overrides):
    row = {
        "month": "2012-01",
        "town": "ANG MO KIO",
        "flat_type": "2 ROOM",
        "block": "19",
        "street_name": "ANG MO KIO AVE 3",
        "storey_range": "01 TO 03",
        "floor_area_sqm": "45",
        "flat_model": "IMPROVED",
        "lease_commence_date": "1980",
        "remaining_lease": "",
        "resale_price": "300000",
        "source_file": "sample.csv",
        "source_row_number": 2,
    }
    row.update(overrides)
    return row


if __name__ == "__main__":
    unittest.main()
