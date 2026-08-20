# Architecture Notes

## Assumptions

- HDB's data platform runs in private AWS VPC subnets.
- The source is the public data.gov.sg endpoint.
- Raw and curated target stores are Amazon S3.
- Tableau is hosted on AWS and connects to Amazon Athena through the Athena driver.
- Production data should be encrypted, audited, and accessed through least-privilege roles.

## Data Ingestion

The ingestion design supports scheduled batch pulls from data.gov.sg, including files larger than 100 MB.

- EventBridge triggers the ETL workflow monthly or on demand.
- ECS Fargate or AWS Glue runs the Python pipeline in private subnets.
- The runtime reaches data.gov.sg through controlled outbound egress via NAT Gateway.
- Raw files are written to an immutable S3 raw zone.
- Cleaned, transformed, failed, and hashed outputs are written to curated S3 prefixes.
- Glue Data Catalog stores schemas and partitions for downstream Athena queries.
- CloudWatch and CloudTrail provide operational logs and audit records.

## Data Exploitation

The exploitation design supports Tableau on AWS using the Athena driver.

- Tableau runs inside private AWS network segments.
- Traffic to supported AWS services uses VPC endpoints or PrivateLink where available.
- Athena queries curated S3 data through Glue Catalog metadata.
- Lake Formation and IAM govern table, column, and S3 permissions.
- Query results and logs are stored in controlled S3 buckets.

## Security, Scalability, and Performance

- Encrypt S3 with KMS keys and block public access.
- Use IAM task roles instead of static credentials.
- Partition curated files by year and month.
- Prefer Parquet for production curated tables to reduce Athena scan cost.
- Alert on failed ingestion, schema drift, abnormal row-count changes, and high failed-record rates.

## Diagram Files

- `architecture/data_ingestion_architecture.png`
- `architecture/data_exploitation_architecture.png`
