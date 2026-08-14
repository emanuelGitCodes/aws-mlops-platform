---
type: architecture
title: Data and ingestion path
created: "2026-07-10"
updated: "2026-08-14"
sources: ["../../../infra/stacks/data_stack.py", "../../../infra/stacks/ingestion_stack.py", "../../../src/ingestion/validate_handler.py", "../../../src/common/schema.py", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md"]
summary: "Raw S3 events flow through EventBridge and SQS to schema validation, then valid rows land in curated S3 storage."
---
# Data and ingestion path

## Confirmed

`DataStack` owns three retained, versioned, private, KMS-encrypted S3 buckets: raw input, curated data, and artifacts. The raw bucket enables EventBridge notifications.

`IngestionStack` wires the event path:

```text
S3 Object Created -> EventBridge rule -> SQS queue -> validation Lambda -> curated S3
                                              \-> DLQ after three failed deliveries
```

The validation Lambda reads one SQS message at a time. It reads the raw object
that the message names, then validates each row with the shared `CustomerRecord`
schema. It writes the valid records to curated storage and quarantines the
invalid rows. The [serving boundary](../concepts/contracts-and-preprocessing.md)
uses the same schema, so training validation and inference validation agree.

The July 10 verification uploaded `telco.csv` to the raw bucket. The curated
object then appeared at `telco/telco.csv`. CloudWatch logged
`{"key":"telco.csv","valid":7043,"rejected":0}`, so the ingestion path accepted
all 7,043 rows. This is evidence for the training-data path only. An API
`sample.json` request tests the separate inference path.

## Synthesis

The queue is a reliability boundary, not only a transport. It absorbs a burst,
it retries a temporary failure, and it keeps a permanently failing message in a
14-day DLQ for investigation. The curated bucket is the hand-off from
event-driven ingestion to the
[SageMaker training pipeline](../concepts/closed-drift-loop.md).

## Tensions or open questions

- The event rule filters on the raw bucket name, and the validation handler
  holds the CSV-specific behavior. A second source format therefore needs an
  explicit version strategy for the event contract and for the handler routing.
- The pipeline reads curated data through a Processing job. A successful
  ingestion does not prove that SageMaker preprocessing or training started.
