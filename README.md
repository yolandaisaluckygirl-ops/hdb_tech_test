# HDB Technical Test for Senior Data Engineer

This is a fresh project for the HDB resale flat prices technical test.

Source dataset: https://data.gov.sg/collections/189/view

The pipeline processes resale flat price records for `2012-01` to `2016-12`, produces the required output groups, and includes AWS architecture diagrams for ingestion and exploitation.

## Project Structure

```text
hdb_resale_tech_test/
  architecture/              PNG diagrams and architecture notes
  data/
    raw/                     Raw CSV files as downloaded
    cleaned/                 Records that pass data quality checks
    transformed/             Cleaned records with Resale Identifier
    failed/                  Removed records with failure reasons
    hashed/                  Cleaned data with hashed identifier
    dqc_result/              Review output for rare values and price anomalies
    profile/                 Data profiling JSON
  notebooks/                 Jupyter walkthrough
  src/hdb_resale_etl/        ETL source code
  tests/                     Automated tests
```

## Setup

```bash
cd hdb_resale_tech_test
python -m pip install -r requirements.txt
```

## Run Tests

```bash
python -m unittest discover -s tests -q
```

## Run Pipeline

To process CSV files already placed in `data/raw/`:

```bash
python run_pipeline.py
```

To download the collection from data.gov.sg first:

```bash
python run_pipeline.py --download
```

The pipeline discovers child datasets from collection `189` programmatically. Unauthenticated data.gov.sg API calls are rate-limited, so a retry or production API key may be required for repeated downloads.

## Required Outputs

The pipeline writes:

```text
data/raw/*.csv
data/cleaned/cleaned_resale_flat_prices.csv
data/transformed/transformed_resale_flat_prices.csv
data/failed/failed_resale_flat_prices.csv
data/hashed/hashed_resale_flat_prices.csv
data/dqc_result/dqc_result.csv
data/profile/master_profile.json
```

## Key Rules Implemented

- Combines all raw files into one master dataset.
- Profiles every column with row counts, empty counts, unique counts, sample values, and numeric stats where applicable.
- Validates `month`, `town`, `flat_type`, `flat_model`, and `storey_range` from the observed statistical properties of the master dataset.
- Fails records with null or empty values in mandatory source fields.
- Fails records containing replacement characters or non-printable control characters that indicate possible encoding corruption.
- Fails records where `month` is not strict `YYYY-MM` format or is outside `2012-01` to `2016-12`.
- Fails records where `storey_range` is not in `number TO number` format, for example `01 TO 03`, or where the lower storey is greater than the upper storey.
- Fails records where `lease_commence_date` is outside a reasonable interval from 1960 to the run year.
- Recomputes remaining lease as of the run date using a 99-year lease, rounded down to years and months.
- Treats all columns except `resale_price` as the duplicate composite key; when duplicate keys exist, keeps the higher resale price and sends lower prices to failed output.
- Flags potential resale price anomalies using a 3x IQR rule within each `month + town + flat_type` group where there are at least 8 records, and writes them to `data/dqc_result/dqc_result.csv` for review.
- Runs frequency checks on all non-price fields in the cleaned dataset. Values that appear only once are flagged as `rare value` in `data/dqc_result/dqc_result.csv` for review instead of being automatically failed.
- Builds `resale_identifier` according to the assignment formula.
- Hashes the identifier with SHA-256, an irreversible one-way hashing algorithm with a 256-bit digest represented as 64 hex characters.
- The assignment formula can produce duplicate plain `resale_identifier` values. To preserve uniqueness, `hashed_resale_identifier` hashes the plain identifier together with the cleaned transaction natural key.

## Additional Data Validation Mechanism

As an additional production-ready validation pattern, the categorical fields can be governed through profiling-derived dimension tables:

```text
dim_town
dim_flat_type
dim_flat_model
dim_storey_range
```

These dimension tables would be derived from the combined in-scope master dataset after canonical normalization. Each table can store the full accepted value list together with profiling statistics such as `record_count`, `first_month`, and `last_month`.

Example:

```text
dim_town(town, record_count, first_month, last_month)
```

During validation, incoming records can be checked against these reference dimensions. Any record with a `town`, `flat_type`, `flat_model`, or `storey_range` outside the accepted dimension values would be routed to the failed dataset with a reason such as `unknown_town` or `unknown_flat_model`.

This approach demonstrates a mechanism for catching spelling changes, unexpected new categories, source-system drift, and other anomalous categorical values even if the current dataset does not contain such issues. In production, these generated dimension lists should be reviewed and promoted to governed reference data before being used for future loads.

For a stronger production workflow, DQC review decisions can be captured in a separate decision file and applied in a later stage to produce a final approved dataset. See `docs/data_quality_notes.md` for the recommended review decision loop.

## Architecture Deliverables

```text
architecture/data_ingestion_architecture.png
architecture/data_exploitation_architecture.png
architecture/architecture_notes.md
```

The diagrams cover AWS batch ingestion from public data.gov.sg into private HDB data platform components, and Tableau-on-AWS integration with Athena while keeping AWS traffic private where possible.
