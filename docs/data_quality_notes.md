# Data Quality Notes

## Implemented Validation

The pipeline first filters the combined raw rows to the assignment period, `2012-01` through `2016-12`. Valid rows outside this period are scope-excluded before profiling and data quality checks; they are not failed records. The pipeline then implements rule-based validation for the required assignment fields:

- `month` must be strict `YYYY-MM` format and parseable. The assignment date range is handled by the upstream scope filter, not by failed-record validation.
- Mandatory source fields must not be null or empty.
- Business fields must not contain replacement characters or non-printable control characters that indicate possible encoding corruption.
- `town`, `flat_type`, `flat_model`, and `storey_range` must be non-empty after canonical normalization.
- `floor_area_sqm` must be greater than zero.
- `resale_price` must be greater than or equal to zero.
- `storey_range` must follow `number TO number` format, for example `01 TO 03`, and the lower storey must be less than or equal to the upper storey.
- `lease_commence_date` must be a plausible year between 1960 and the run year.
- Duplicate composite keys keep the higher `resale_price`; lower-price duplicates go to the failed dataset.
- Potential resale price anomalies are flagged with a conservative 3x IQR rule on `price_per_sqm` within `month + town + flat_type + remaining_lease_decade` and written to the DQC result dataset for review. The `dqc_anomaly_direction` field indicates whether the record is below the lower bound (`low`) or above the upper bound (`high`).
- Low-frequency values are identified across non-price fields. Values that appear only once in the cleaned dataset are written to the DQC result dataset as `rare value` for review.

## DQC Result Dataset

The DQC result output is a review dataset, not a hard-fail dataset:

```text
data/dqc_result/dqc_result.csv
```

It contains records that pass deterministic validation but deserve additional review based on statistical checks.

Current DQC categories:

| Category | Meaning | Action |
| --- | --- | --- |
| `rare value` | A non-price field value appears only once in the cleaned dataset | Review as a potential typo, source drift, or genuinely rare value |
| `anomaly resale price` | `price_per_sqm` is outside a 3x IQR threshold within `month + town + flat_type + remaining_lease_decade`; `dqc_anomaly_direction` marks `high` or `low` | Review as a potential pricing anomaly |

Rare values are not automatically sent to failed output because low frequency does not always mean invalid data.

## Recommended Review Decision Loop

A stronger production implementation would add a review decision loop for records in the DQC result dataset.

Current behavior:

```text
cleaned_resale_flat_prices.csv
    contains deterministic-pass records, including records flagged for DQC review

dqc_result.csv
    contains a review queue copied from cleaned records
```

Recommended future behavior:

```text
raw
  -> deterministic validation
  -> cleaned
  -> dqc_result review queue
  -> manual review decisions
  -> final approved dataset
```

The review decision input can be maintained as:

```text
data/dqc_result/dqc_review_decisions.csv
```

Recommended schema:

```text
source_file,source_row_number,dqc_category,dqc_field,review_status,review_comment,reviewed_by,reviewed_at
```

Example:

```csv
source_file,source_row_number,dqc_category,dqc_field,review_status,review_comment,reviewed_by,reviewed_at
d_xxx.csv,123,rare value,town,approved,false alarm - valid rare value,data_steward,2026-08-20
d_xxx.csv,456,anomaly resale price,price_per_sqm,rejected,confirmed source price-per-sqm error,data_steward,2026-08-20
```

The next pipeline stage can apply these decisions:

```text
final_approved = cleaned - DQC records with review_status = rejected
```

Recommended outputs:

```text
data/final/final_approved_resale_flat_prices.csv
data/failed/review_rejected_resale_flat_prices.csv
```

This avoids manual edits to generated CSV files and keeps the pipeline reproducible. It also creates an audit trail for why reviewed records were approved or rejected.

## Proposed Dimension Table Validation

As an additional validation mechanism, the categorical fields can be validated against dimension reference tables derived from the statistical profile of the in-scope master dataset.

Recommended dimension tables:

```text
dim_town
dim_flat_type
dim_flat_model
dim_storey_range
```

Each dimension table can contain:

```text
value, record_count, first_month, last_month
```

The tables would be generated from the combined raw source files after filtering to the assignment period, `2012-01` to `2016-12`, and applying canonical string normalization.

Validation pattern:

```text
raw.town         not in dim_town         -> failed / unknown_town
raw.flat_type    not in dim_flat_type    -> failed / unknown_flat_type
raw.flat_model   not in dim_flat_model   -> failed / unknown_flat_model
raw.storey_range not in dim_storey_range -> failed / unknown_storey_range
```

This gives the pipeline an explicit mechanism to identify source-system drift, unexpected new categories, typos, and anomalous categorical values. The current dataset may not contain these issues, but the design demonstrates how the pipeline can detect them in future loads.

In production, these profiling-derived dimension tables should be reviewed by data owners and promoted to governed reference data before being used as hard validation rules.

## Stable Hashing Note

The hashed identifier is built from the assignment-defined resale identifier plus an explicit stable source business key. The key is serialized as ordered JSON with field names so the hash is deterministic and independent of DataFrame column order.

The business key excludes `remaining_lease` because this pipeline recomputes it as of the run date. It also excludes `resale_price`, DQC helper fields, lineage metadata, and execution-time values. This keeps the hash stable across reruns with different `as_of_date` values while still preserving uniqueness when the plain resale identifier collides.