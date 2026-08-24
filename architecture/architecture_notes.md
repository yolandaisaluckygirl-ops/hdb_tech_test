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
- Public internet traffic to data.gov.sg and AWS services without configured VPC endpoints uses controlled outbound egress: private Fargate task -> private route table -> NAT Gateway in a public subnet -> Internet Gateway.
- S3 traffic uses an S3 Gateway Endpoint associated with the private route table, avoiding NAT for S3 access while keeping S3 buckets outside the VPC.
- In a production private-subnet setup, additional interface endpoints can be added for ECR API, ECR DKR, CloudWatch Logs, Glue, KMS, and STS to reduce NAT dependency.
- Raw files are written to an immutable S3 raw zone.
- The Fargate task reads raw files, performs validation and transformation, and writes cleaned, transformed, failed, and hashed outputs to curated S3 prefixes.
- The Fargate task updates Glue Data Catalog tables and partitions through the Glue API for downstream Athena queries.
- CloudWatch and CloudTrail provide operational logs and audit records.
- EventBridge Scheduler retry and DLQ handle failures to invoke the ECS `RunTask` target.
- ECS task runtime failures are handled separately through ECS task state change events, for example a STOPPED non-zero-exit task triggering an EventBridge rule and SNS/SQS alert or failure handler.
- A production task-level retry design can route Scheduler -> Step Functions -> ECS Fargate so Step Functions can wait for completion and apply `Retry` and `Catch`.

## Data Exploitation

The exploitation design supports Tableau on AWS using the Athena driver.

- Tableau runs inside private AWS network segments.
- Tableau reaches Athena privately through an Athena Interface VPC Endpoint ENI; Athena itself remains an AWS managed service outside the VPC.
- Athena reads schema and partition metadata from AWS Glue Data Catalog.
- Athena scans actual curated data directly in Amazon S3; this access is performed by the Athena managed service, not by Tableau through the VPC S3 Gateway Endpoint.
- Athena writes query results to a controlled Amazon S3 result bucket or prefix. The Athena workgroup should enforce the result location, encryption, and lifecycle policy.
- Lake Formation and IAM govern table, column, and S3 permissions.
- Athena emits query metrics to CloudWatch.
- CloudTrail is treated as a cross-cutting audit capability for Athena, Glue, S3, EventBridge, ECS, and Lake Formation API activity.

## Security, Scalability, and Performance

- Encrypt S3 with KMS keys and block public access.
- Use IAM task roles instead of static credentials.
- Partition curated files by year and month.
- Prefer Parquet for production curated tables to reduce Athena scan cost.
- Alert on failed ingestion, schema drift, abnormal row-count changes, and high failed-record rates.

## Diagram Files

- `architecture/hdb_resale_architecture.png`

The diagram uses selected icons from the official AWS Architecture Icons package. The PNG file is the submitted diagram artifact, and the selected icon assets are stored under `architecture/aws-icons/`.
