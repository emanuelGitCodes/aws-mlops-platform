"""Calculate Population Stability Index over the raw feature contract.

The preprocessing step builds the training baseline with this module. The drift
Lambda scores capture windows with the same functions. Raw values preserve the
column names and categories in drift results. This module uses only the
standard library.
"""

# The SageMaker managed image uses an older Python version.
# Deferred annotations preserve compatibility with that image.
from __future__ import annotations

import bisect
import math
from typing import Any

from src.common.features import FEATURE_COLUMNS, NUMERIC

# Use ten quantile bins for each numeric column.
NUMERIC_BINS = 10

# Replace empty bucket shares with this positive floor.
EPSILON = 1e-6

# A column reaches drift at this PSI value.
COLUMN_PSI_THRESHOLD = 0.2

# This fraction of columns must reach `COLUMN_PSI_THRESHOLD`.
DRIFTED_COLUMN_FRACTION = 0.3

# One column at this PSI value declares drift.
# This rule detects targeted shifts below `DRIFTED_COLUMN_FRACTION`.
SEVERE_COLUMN_PSI = 1.0

# The drift Lambda emits this platform event. The retrain Lambda consumes it.
# `infra/stacks/monitoring_stack.py` repeats these literals.
# Importing a handler evaluates its environment lookups during synthesis.
EVENT_SOURCE = "mlops.monitoring"
EVENT_DETAIL_TYPE = "Drift Evaluation Result"
DRIFT_STATUS = "DriftDetected"


def numeric_value(raw: Any) -> float:
    """Return one numeric feature value. Convert a blank string to `0.0`."""
    text = str(raw).strip()
    if not text:
        return 0.0
    return float(text)


def numeric_edges(values: list[float], bins: int = NUMERIC_BINS) -> list[float]:
    """Return the interior quantile edges that split ``values`` into ``bins``.

    Repeated edges collapse. A dominant value can produce fewer than `bins`
    buckets.
    """
    ordered = sorted(values)
    if not ordered:
        return []
    edges = set()
    for step in range(1, bins):
        index = min(len(ordered) * step // bins, len(ordered) - 1)
        edges.add(float(ordered[index]))
    return sorted(edges)


def bucket_of(column: str, raw: Any, edges: list[float]) -> str:
    """Return the bucket key one raw value falls in.

    Each categorical value uses its own bucket. An unseen category creates a
    new key. Numeric bins are left-open. A value equal to an edge uses the
    lower bucket.
    """
    if column not in NUMERIC:
        return str(raw)
    return str(bisect.bisect_left(edges, numeric_value(raw)))


def bucket_counts(
    rows: list[dict[str, Any]], edges: dict[str, list[float]]
) -> dict[str, dict[str, int]]:
    """Count how many rows fall in each bucket, per feature column."""
    counts: dict[str, dict[str, int]] = {column: {} for column in FEATURE_COLUMNS}
    for row in rows:
        for column in FEATURE_COLUMNS:
            if column not in row:
                continue
            key = bucket_of(column, row[column], edges.get(column, []))
            counts[column][key] = counts[column].get(key, 0) + 1
    return counts


def distinct_record_count(rows: list[dict[str, Any]]) -> int:
    """Count the distinct feature vectors in a capture window."""
    return len({tuple(str(row.get(column)) for column in FEATURE_COLUMNS) for row in rows})


def build_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the reference distribution and numeric edges for drift scoring."""
    edges = {
        column: numeric_edges([numeric_value(row[column]) for row in rows if column in row])
        for column in FEATURE_COLUMNS
        if column in NUMERIC
    }
    return {
        "record_count": len(rows),
        "edges": edges,
        "counts": bucket_counts(rows, edges),
    }


def population_stability_index(reference: dict[str, int], current: dict[str, int]) -> float:
    """Return the PSI between two bucket-count distributions."""
    reference_total = sum(reference.values())
    current_total = sum(current.values())
    if not reference_total or not current_total:
        return 0.0
    index = 0.0
    for key in set(reference) | set(current):
        reference_share = max(reference.get(key, 0) / reference_total, EPSILON)
        current_share = max(current.get(key, 0) / current_total, EPSILON)
        index += (current_share - reference_share) * math.log(current_share / reference_share)
    return index


def compare(baseline: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score one window of captured records against the baseline.

    The caller decides whether the result is actionable. This function reports
    the measurement and does not apply the sample-size rule.
    """
    counts = bucket_counts(rows, baseline.get("edges", {}))
    reference = baseline.get("counts", {})
    column_psi = {
        column: round(population_stability_index(reference.get(column, {}), counts[column]), 6)
        for column in FEATURE_COLUMNS
    }
    drifted = sorted(
        column for column, value in column_psi.items() if value >= COLUMN_PSI_THRESHOLD
    )
    fraction = len(drifted) / len(FEATURE_COLUMNS)
    worst = max(column_psi.values()) if column_psi else 0.0
    return {
        "record_count": len(rows),
        "column_psi": column_psi,
        "drifted_columns": drifted,
        "drifted_fraction": round(fraction, 6),
        "max_column_psi": round(worst, 6),
        # Declare drift from a broad shift or one severe column shift.
        "drifted": fraction >= DRIFTED_COLUMN_FRACTION or worst >= SEVERE_COLUMN_PSI,
    }
