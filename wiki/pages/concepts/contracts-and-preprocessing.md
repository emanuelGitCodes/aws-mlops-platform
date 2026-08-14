---
type: concept
title: Validation versus preprocessing contracts
created: "2026-07-10"
updated: "2026-08-14"
sources: ["../../../src/common/schema.py", "../../../src/pipeline/preprocess.py", "../../../src/serving/proxy_handler.py", "../../../src/ingestion/validate_handler.py", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md"]
summary: "Validation checks whether a record is acceptable; preprocessing deterministically converts an accepted record into the model's numeric feature vector."
---
# Validation versus preprocessing contracts

## Confirmed

`src/common/schema.py` defines the accepted customer-record shape, the value
constraints, the optional label behavior, and the canonical `FEATURE_COLUMNS`
order. The ingestion validation and the inference proxy both use it.

`src/pipeline/preprocess.py` does a separate transformation. `encode_features`
maps each categorical value to a deterministic number. It writes one float per
feature, in the canonical order. `encode_labeled_row` writes the label first,
for the XGBoost training files.

The serving proxy validates the JSON request first. It then extracts only
`FEATURE_COLUMNS`, encodes the values, and sends one CSV line to SageMaker. The
proxy holds no model inference logic.

The deployed pipeline showed one packaging rule: the Processing container MUST
receive `preprocess.py` and the shared package that holds `src.common.schema`.
The first live execution failed with `ModuleNotFoundError: No module named
'src'` before it transformed any data. A correct schema contract in the
repository does not put that contract at the SageMaker Processing runtime
boundary. The repository fixed the packaging defect; see the
[closed drift loop](closed-drift-loop.md) for the execution that then
succeeded.

## Synthesis

Read the two stages in this order:

```text
schema validation -> accepted raw record -> deterministic encoding -> model payload
```

Validation answers one question: is this record allowed? Preprocessing answers a
different one: how does the model read it? The two stages MUST stay separate.
The separation keeps the schema reusable, and it keeps a data contract distinct
from a model transform.

## Tensions or open questions

- The source code holds the ordinal maps as fixed values. This is easy to
  reproduce. It also means that a new category needs a code change and a model
  compatibility change, because the platform does not learn the map from data.
- The pipeline MUST package the shared schema. It MUST NOT copy the schema into
  `preprocess.py`, because two copies let validation and preprocessing separate
  without a signal.
