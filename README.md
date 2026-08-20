# HDB Resale Flat Prices Technical Test

This repository contains a Python ETL pipeline and AWS solution architecture for the HDB Senior Data Engineer technical test.

Dataset source: https://data.gov.sg/collections/189/view

The pipeline processes HDB resale flat price records for the assignment period, `2012-01` to `2016-12`, and produces the required raw, cleaned, transformed, failed, and hashed outputs.

## Project Overview

The solution is designed as a reproducible batch data pipeline:

```text
data.gov.sg API / raw CSV files
        |
        v
Extract raw files and combine into master dataset
        |
        v
Profile + deterministic data quality validation
        |
        +--> failed dataset
        |
        v
Cleaned dataset
        |
        +--> DQC review result for rare values and price anomalies
        |
        v
Transform with Resale Identifier
        |
        v
Hash identifier while preserving uniqueness
        |
        v
Final assignment outputs
```

Main design considerations:

- Preserve raw data as-is for audit and replay.
- Keep deterministic failures separate from review-only DQC findings.
- Make transformations idempotent and testable.
- Keep source file and row number metadata for traceability.
- Use modular Python code rather than one large notebook script.
- Include architecture diagrams for operationalising the flow on AWS.

## Project Structure

```text
hdb_resale_tech_test/
  architecture/              AWS ingestion and exploitation diagrams
  data/
    raw/                     Raw CSV files from data.gov.sg
    cleaned/                 Records that pass deterministic validation
    transformed/             Cleaned records with Resale Identifier
    failed/                  Records removed by hard validation rules
    hashed/                  Transformed data with hashed identifier
    dqc_result/              Review queue for statistical DQC findings
    profile/                 Data profiling JSON
  docs/                      Data quality notes and future improvements
  notebooks/                 Jupyter execution walkthrough
  src/hdb_resale_etl/        ETL package
  tests/                     Unit tests
```

## Requirement-To-Code Map

| Assignment requirement | Implementation | Code location |
| --- | --- | --- |
| Extract data programmatically from data.gov.sg | Discover collection child datasets, filter by coverage period, use initiate/poll download API | `src/hdb_resale_etl/extract.py` |
| Combine datasets into one master dataset | Load all raw CSVs and concatenate into one DataFrame with source metadata | `load_raw_files()` in `extract.py` |
| Data profiling | Generate row counts, empty counts, unique counts, samples, and numeric stats | `src/hdb_resale_etl/profile.py` |
| Validate date, town, flat type, flat model, storey range | Apply deterministic validation and statistical DQC checks | `src/hdb_resale_etl/quality.py` |
| Recompute remaining lease | Recalculate 99-year lease balance as of run date | `recompute_remaining_lease()` in `quality.py` |
| Handle duplicate composite keys | Use all columns except resale price as the key; keep higher resale price | `split_duplicate_keys()` in `quality.py` |
| Identify anomalous resale prices | 3x IQR rule on `price_per_sqm` within `month + town + flat_type + remaining_lease_decade` groups | `build_price_anomaly_dqc()` in `quality.py` |
| Create Resale Identifier | Apply assignment formula using block, group average price, month, and town | `add_resale_identifier()` in `transform.py` |
| Hash identifier irreversibly | SHA-256 hash using identifier plus natural key to preserve uniqueness | `add_hashed_identifier()` in `transform.py` |
| Produce output groups | Write raw, cleaned, transformed, failed, hashed, DQC, and profile outputs | `src/hdb_resale_etl/pipeline.py` |
| Provide execution guide | Notebook walkthrough | `notebooks/HDB_Resale_ETL_Walkthrough.ipynb` |
| Provide AWS architecture | PNG diagrams and notes | `architecture/` |

## Data Quality Approach

### Hard Validation Rules

Records that fail these rules are written to `data/failed/failed_resale_flat_prices.csv`.

| Rule | Failure reason |
| --- | --- |
| Mandatory fields must not be null or empty | `missing_required_<column>` |
| Business fields must not contain replacement/control characters | `garbled_or_control_characters` |
| `month` must be strict `YYYY-MM` | `invalid_month` |
| `month` must be within `2012-01` to `2016-12` | `out_of_scope_month` |
| `storey_range` must follow `number TO number`, e.g. `01 TO 03` | `invalid_storey_range_format` |
| `lease_commence_date` must be between 1960 and the run year | `invalid_lease_commence_date` |
| `floor_area_sqm` must be greater than zero | `invalid_floor_area_sqm` |
| `resale_price` must be greater than or equal to zero | `invalid_resale_price` |
| Duplicate composite keys keep only the higher resale price | `duplicate_composite_key_lower_price` |

### DQC Review Rules

Some records pass hard validation but should still be reviewed. These are written to:

```text
data/dqc_result/dqc_result.csv
```

| DQC category | Method | Why it is review-only |
| --- | --- | --- |
| `rare value` | Frequency check across non-price fields; values appearing once are flagged | Rare does not always mean wrong |
| `anomaly resale price` | 3x IQR outlier rule on `price_per_sqm` within `month + town + flat_type + remaining_lease_decade` groups, with `dqc_anomaly_direction` as `high` or `low` | High or low price can still be genuine |

DQC records remain in the cleaned dataset unless a future manual review process rejects them. See `docs/data_quality_notes.md` for the proposed review decision loop.

## Identifier And Hashing

The assignment-defined `resale_identifier` can repeat because it uses only a small number of fields.

To preserve uniqueness, the pipeline hashes:

```text
resale_identifier + cleaned transaction natural key
```

using SHA-256. This produces a 64-character irreversible hash in `hashed_resale_identifier`.

## Architecture Deliverables

```text
architecture/data_ingestion_architecture.png
architecture/data_exploitation_architecture.png
architecture/architecture_notes.md
```

The architecture covers:

- Batch ingestion from public data.gov.sg into private AWS data platform components.
- Raw and curated storage on S3.
- Glue Data Catalog and Athena integration.
- Tableau on AWS using Athena driver.
- Security, scalability, and performance considerations.

## Future Improvements

Recommended enhancements for a production version:

- Create governed dimension tables such as `dim_town`, `dim_flat_type`, `dim_flat_model`, and `dim_storey_range` from profiled master data.
- Validate future loads against those dimension tables to detect unknown categories and source drift.
- Add a permanent transaction-level unique id to simplify deduplication, audit, review decisions, and downstream joins.
- Implement the DQC review decision loop described in `docs/data_quality_notes.md`.
- Store curated outputs as partitioned Parquet files for Athena performance.
- Add CI checks to run unit tests automatically on GitHub.
