from pathlib import Path
import sys
import unittest

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hdb_resale_etl.scope import split_assignment_scope


class ScopeTests(unittest.TestCase):
    def test_scope_filter_excludes_valid_out_of_period_rows_only(self) -> None:
        raw = pd.DataFrame(
            [
                {"month": "2011-12", "source_row_number": 2},
                {"month": "2012-01", "source_row_number": 3},
                {"month": "2016-12", "source_row_number": 4},
                {"month": "2017-01", "source_row_number": 5},
                {"month": "2012-1", "source_row_number": 6},
            ]
        )

        master, excluded = split_assignment_scope(raw, "2012-01", "2016-12")

        self.assertEqual(master["source_row_number"].tolist(), [3, 4, 6])
        self.assertEqual(excluded["source_row_number"].tolist(), [2, 5])


if __name__ == "__main__":
    unittest.main()