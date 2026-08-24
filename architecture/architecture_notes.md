# Architecture Notes

## Assumptions

- HDB's compute layer runs in private AWS VPC subnets; AWS managed services such as S3, Athena, Glue, CloudWatch, CloudTrail, and Secrets Manager are consumed through public service APIs or VPC endpoints and are not placed inside subnets.
- The source is the public data.gov.sg endpoint.
- Raw and curated target stores are Amazon S3.
- Tableau is hosted on AWS and connects to Amazon Athena through the Athena driver.
- Production data should be encrypted, audited, and accessed through least-privilege roles.

## Data Ingestion

The ingestion design supports scheduled batch pulls from data.gov.sg, including files larger than 100 MB.

- EventBridge Scheduler triggers ECS/Fargate `RunTask` monthly or on demand.
- ECS Fargate runs the Python pipeline in a private subnet using a task ENI.
- The runtime reaches data.gov.sg through controlled outbound egress: private Fargate task -> private route table -> NAT Gateway in a public subnet -> Internet Gateway -> data.gov.sg.
- S3 traffic uses an S3 Gateway Endpoint where applicable, avoiding NAT for S3 access.
- Secrets Manager access uses an Interface Endpoint ENI in the private subnet.
- Raw files are written to an immutable S3 raw zone.
- Cleaned, transformed, failed, and hashed outputs are written to curated S3 prefixes.
- Glue Data Catalog stores schemas and partitions for downstream Athena queries.
- CloudWatch and CloudTrail provide operational logs and audit records.
- Failed task attempts are retried through scheduler/task retry policy and routed to a DLQ or failure-handling target for operations follow-up.

## Data Exploitation

The exploitation design supports Tableau on AWS using the Athena driver.

- Tableau runs inside private AWS network segments.
- Tableau reaches Athena privately through an Athena Interface VPC Endpoint ENI; Athena itself remains an AWS managed service outside the VPC.
- Athena queries curated S3 data through Glue Catalog metadata.
- S3 access uses a Gateway Endpoint where applicable so S3 traffic does not require NAT.
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
- `architecture/data_ingestion_architecture.svg`
- `architecture/data_exploitation_architecture.svg`

The diagrams use selected icons from the official AWS Architecture Icons package. The SVG files are retained as maintainable diagram sources, and the selected icon assets are stored under `architecture/aws-icons/`.
