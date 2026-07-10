---
type: concept
title: Validation versus preprocessing contracts
created: "2026-07-10"
updated: "2026-07-10"
sources: ["../../../src/common/schema.py", "../../../src/pipeline/preprocess.py", "../../../src/serving/proxy_handler.py", "../../../src/ingestion/validate_handler.py"]
summary: "Validation checks whether a record is acceptable; preprocessing deterministically converts an accepted record into the model's numeric feature vector."
---
# Validation versus preprocessing contracts

## Confirmed

`src/common/schema.py` defines the accepted customer-record shape, value constraints, optional label behavior, and the canonical `FEATURE_COLUMNS` order. Both ingestion validation and the inference proxy use it.

`src/pipeline/preprocess.py` performs a separate transformation. `encode_features` maps categorical values to deterministic numbers and emits one float per feature in the canonical order. `encode_labeled_row` adds the label first for XGBoost training files.

The serving proxy validates the JSON request first, extracts only `FEATURE_COLUMNS`, encodes the values, and sends a CSV line to SageMaker. It does not contain model inference logic.

## Synthesis

The safe mental model is:

```text
schema validation -> accepted raw record -> deterministic encoding -> model payload
```

Validation answers “is this record allowed?”; preprocessing answers “how does the model consume it?” Keeping the two stages separate makes the schema reusable without confusing a data contract with a learned model transform.

## Tensions or open questions

- The ordinal maps are fixed in source code, which is easy to reproduce but means a new category requires a code and model compatibility change rather than being learned from data.
