---
type: architecture
title: Data and ingestion path
created: "2026-07-10"
updated: "2026-07-10"
sources: ["../../../infra/stacks/data_stack.py", "../../../infra/stacks/ingestion_stack.py", "../../../src/ingestion/validate_handler.py", "../../../src/common/schema.py"]
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

The validation Lambda consumes one SQS message at a time, reads the referenced raw object, validates rows with the shared `CustomerRecord` schema, writes valid records to curated storage, and quarantines invalid rows. The same schema is used at the [serving boundary](../concepts/contracts-and-preprocessing.md), keeping training and inference validation aligned.

## Synthesis

The queue is a reliability boundary rather than just a transport: it absorbs bursts, retries transient failures, and preserves permanently failing messages in a 14-day DLQ for investigation. The curated bucket is the hand-off from event-driven ingestion to the [SageMaker training pipeline](../concepts/closed-drift-loop.md).

## Tensions or open questions

- The current event rule filters on the raw bucket name and the validation handler owns CSV-specific behavior. If more source formats arrive, the event contract and handler routing will need an explicit versioning strategy.
