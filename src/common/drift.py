"""Population Stability Index over the raw feature contract.

This module is the one definition of the drift statistic. The preprocessing
step imports it to build the training baseline. The drift Lambda imports it to
score a capture window against that baseline. A second copy would let the two
sides bin the same value differently and report drift that is not there.

Drift is measured on raw values, not on the encoded vector from
``features.encode_features``. Raw values name the column and the category that
moved, which an ordinal code cannot.

The module uses the standard library only. The drift Lambda ships it in the
same bundle as the handlers, and the SageMaker processing image installs
nothing extra for it.
"""

# The preprocessing step imports this module inside the SageMaker managed
# image. That image runs an older Python than 3.12. Deferred annotations keep
# modern syntax here from becoming a runtime error.
from __future__ import annotations

import bisect
import math
from typing import Any

from src.common.features import FEATURE_COLUMNS, NUMERIC

# Quantile bins per numeric column. Ten is enough to show a shift in a column
# with a few thousand distinct values, and coarse enough that an hourly window
# of a few hundred records still fills most bins.
NUMERIC_BINS = 10

# A bucket that holds no records would make the ratio below zero or infinite.
# Substituting this floor keeps one empty bucket from dominating the sum.
EPSILON = 1e-6

# Above this, a column's distribution has moved enough to act on. The
# convention this follows reads 0.1 to 0.2 as a moderate shift and anything
# above 0.2 as a large one.
COLUMN_PSI_THRESHOLD = 0.2

# The share of columns that must breach `COLUMN_PSI_THRESHOLD` before the
# window counts as drift. One column moving is a data-quality question. Six of
# nineteen is a different population.
DRIFTED_COLUMN_FRACTION = 0.3

# The platform's own violation event, shared by the Lambda that emits it and
# the Lambda that consumes it. `infra/stacks/monitoring_stack.py` repeats these
# three as literals, because importing a handler during synth would run its
# module-level environment lookups. tests/unit/test_monitoring_stack.py asserts
# the stack and this module agree.
EVENT_SOURCE = "mlops.monitoring"
EVENT_DETAIL_TYPE = "Drift Evaluation Result"
DRIFT_STATUS = "DriftDetected"


def numeric_value(raw: Any) -> float:
    """Read one numeric feature value.

    Blank strings become ``0.0``. The curated Telco data spells an unbilled
    account's ``TotalCharges`` as a blank, and ``features.encode_features``
    reads it the same way.
    """
    text = str(raw).strip()
    if not text:
        return 0.0
    return float(text)


def numeric_edges(values: list[float], bins: int = NUMERIC_BINS) -> list[float]:
    """Return the interior quantile edges that split ``values`` into ``bins``.

    Repeated edges collapse. A column where one value holds most of the rows
    yields fewer buckets than ``bins``, which is correct: the bins it would
    have had are empty.
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

    A categorical value is its own bucket, so an unseen category appears as a
    new key rather than being folded into a neighbour.

    Numeric bins are left-open: a value equal to an edge falls below it. That
    matters for a low-cardinality column. `SeniorCitizen` holds 0 and 1, so its
    only edge is `0.0`; binning right-open would put both values in the same
    bucket and make that column's drift undetectable.
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
    """Count the distinct feature vectors in a window.

    A window of repeated identical records is a point mass. Every column's PSI
    against the training distribution then explodes, and `compare` reports that
    every column moved. The count of records cannot detect this, so the caller
    needs the count of distinct ones.
    """
    return len({tuple(str(row.get(column)) for column in FEATURE_COLUMNS) for row in rows})


def build_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the reference distribution the drift job compares windows against.

    The edges are stored beside the counts. The drift job must bin a live
    window on the training data's edges, never on the window's own.
    """
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
    """Return the PSI between two bucket-count distributions.

    The result is 0.0 when the two distributions are identical, and grows
    without bound as they separate.
    """
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
    return {
        "record_count": len(rows),
        "column_psi": column_psi,
        "drifted_columns": drifted,
        "drifted_fraction": round(len(drifted) / len(FEATURE_COLUMNS), 6),
        "drifted": len(drifted) / len(FEATURE_COLUMNS) >= DRIFTED_COLUMN_FRACTION,
    }
