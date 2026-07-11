---
type: concept
title: Validation versus preprocessing contracts
created: "2026-07-10"
updated: "2026-07-11"
sources: ["../../../src/common/schema.py", "../../../src/pipeline/preprocess.py", "../../../src/serving/proxy_handler.py", "../../../src/ingestion/validate_handler.py", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md"]
summary: "Validation checks whether a record is acceptable; preprocessing deterministically converts an accepted record into the model's numeric feature vector."
---
# Validation versus preprocessing contracts

## Confirmed

`src/common/schema.py` defines the accepted customer-record shape, value constraints, optional label behavior, and the canonical `FEATURE_COLUMNS` order. Both ingestion validation and the inference proxy use it.

`src/pipeline/preprocess.py` performs a separate transformation. `encode_features` maps categorical values to deterministic numbers and emits one float per feature in the canonical order. `encode_labeled_row` adds the label first for XGBoost training files.

The serving proxy validates the JSON request first, extracts only `FEATURE_COLUMNS`, encodes the values, and sends a CSV line to SageMaker. It does not contain model inference logic.

The deployed pipeline exposed an operational packaging requirement: the Processing container must receive both `preprocess.py` and the shared package containing `src.common.schema`. The current execution failed with `ModuleNotFoundError: No module named 'src'` before it could transform data. The schema contract is correct locally; it is not yet present at the SageMaker Processing runtime boundary.

## Synthesis

The safe mental model is:

```text
schema validation -> accepted raw record -> deterministic encoding -> model payload
```

Validation answers “is this record allowed?”; preprocessing answers “how does the model consume it?” Keeping the two stages separate makes the schema reusable without confusing a data contract with a learned model transform.

## Tensions or open questions

- The ordinal maps are fixed in source code, which is easy to reproduce but means a new category requires a code and model compatibility change rather than being learned from data.
- The next pipeline fix should package the shared schema rather than duplicate it in `preprocess.py`, so validation and preprocessing cannot silently drift apart.
