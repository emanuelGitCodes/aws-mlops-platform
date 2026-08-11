"""The drift statistic: binning, PSI, and the baseline contract."""

import json

import pytest

from src.common import drift
from src.common.features import FEATURE_COLUMNS, NUMERIC
from tests.unit.conftest import VALID, varied_records


def rows(count, **overrides):
    """`count` copies of the canonical record, with columns overridden."""
    return [{**VALID, **overrides} for _ in range(count)]


def spread(count, column, values):
    """`count` records cycling `column` through `values`."""
    return [{**VALID, column: values[i % len(values)]} for i in range(count)]


def test_numeric_value_reads_a_blank_as_zero():
    # The curated Telco data spells an unbilled account's TotalCharges blank.
    assert drift.numeric_value("") == 0.0
    assert drift.numeric_value("  ") == 0.0
    assert drift.numeric_value("42.5") == 42.5
    assert drift.numeric_value(7) == 7.0


def test_numeric_edges_are_interior_and_sorted():
    edges = drift.numeric_edges([float(v) for v in range(100)], bins=10)
    assert edges == sorted(edges)
    assert len(edges) == 9
    assert min(edges) > 0.0


def test_numeric_edges_collapse_on_a_constant_column():
    # One value holding every row cannot produce ten distinct bins. Fewer
    # buckets is the correct answer, not an error.
    assert drift.numeric_edges([5.0] * 100) == [5.0]


def test_numeric_edges_of_nothing_is_empty():
    assert drift.numeric_edges([]) == []


def test_bucket_of_keeps_a_category_as_its_own_key():
    assert drift.bucket_of("Contract", "Two year", []) == "Two year"


def test_bucket_of_bins_a_numeric_value_on_the_supplied_edges():
    edges = [10.0, 20.0, 30.0]
    assert drift.bucket_of("tenure", 5, edges) == "0"
    assert drift.bucket_of("tenure", 25, edges) == "2"
    assert drift.bucket_of("tenure", 99, edges) == "3"


def test_a_low_cardinality_numeric_column_still_separates():
    # `SeniorCitizen` values are zero and one. Its only edge is zero.
    # Left-open binning keeps the values in separate buckets.
    baseline = drift.build_baseline(spread(200, "SeniorCitizen", [0, 0, 0, 1]))
    result = drift.compare(baseline, rows(200, SeniorCitizen=1))
    assert result["column_psi"]["SeniorCitizen"] > drift.COLUMN_PSI_THRESHOLD


def test_bucket_counts_ignores_a_column_the_row_omits():
    counts = drift.bucket_counts([{"Contract": "One year"}], {})
    assert counts["Contract"] == {"One year": 1}
    # Every feature column is present as a key, even with no observations.
    assert set(counts) == set(FEATURE_COLUMNS)
    assert counts["gender"] == {}


def test_build_baseline_stores_edges_for_every_numeric_column():
    baseline = drift.build_baseline(spread(50, "tenure", [1, 12, 24, 48, 60]))
    assert baseline["record_count"] == 50
    assert set(baseline["edges"]) == NUMERIC
    assert set(baseline["counts"]) == set(FEATURE_COLUMNS)


def test_the_baseline_is_json_serializable():
    # It travels to S3 as JSON and back into the Lambda.
    baseline = drift.build_baseline(rows(10))
    assert json.loads(json.dumps(baseline)) == baseline


def test_psi_of_an_identical_distribution_is_zero():
    assert drift.population_stability_index({"a": 10, "b": 30}, {"a": 10, "b": 30}) == 0.0


def test_psi_ignores_scale_and_reads_proportion():
    # Twice the records, same shape. PSI must not move.
    index = drift.population_stability_index({"a": 10, "b": 30}, {"a": 20, "b": 60})
    assert index == pytest.approx(0.0)


def test_psi_grows_as_the_distributions_separate():
    reference = {"a": 90, "b": 10}
    near = drift.population_stability_index(reference, {"a": 80, "b": 20})
    far = drift.population_stability_index(reference, {"a": 10, "b": 90})
    assert 0 < near < far


def test_psi_of_an_empty_side_is_zero():
    # No observations is not evidence of drift.
    assert drift.population_stability_index({}, {"a": 5}) == 0.0
    assert drift.population_stability_index({"a": 5}, {}) == 0.0


def test_an_unseen_category_registers_as_drift():
    # The epsilon floor is what stops this dividing by zero.
    index = drift.population_stability_index({"No": 100}, {"Yes": 100})
    assert index > drift.COLUMN_PSI_THRESHOLD


def test_compare_reports_no_drift_between_two_draws_of_one_population():
    # Compare two independent draws from the same distribution.
    baseline = drift.build_baseline(varied_records(600, seed=1))
    result = drift.compare(baseline, varied_records(200, seed=2))
    assert result["drifted"] is False
    assert result["drifted_columns"] == []
    assert result["record_count"] == 200


def test_compare_detects_a_shifted_population():
    # Match the tenure and charge shift from `scripts/send_drift_traffic.py`.
    baseline = drift.build_baseline(varied_records(600, seed=1))
    shifted = varied_records(
        200,
        seed=3,
        tenure=180,
        MonthlyCharges=400.0,
        TotalCharges=60000.0,
        Contract="Two year",
        InternetService="DSL",
        PaymentMethod="Mailed check",
    )
    result = drift.compare(baseline, shifted)
    assert result["drifted"] is True
    assert "tenure" in result["drifted_columns"]
    assert result["drifted_fraction"] >= drift.DRIFTED_COLUMN_FRACTION
    # Untouched columns must stay put, or the result is uniformity, not drift.
    assert "gender" not in result["drifted_columns"]


def test_one_column_moved_mildly_is_not_drift():
    """A single column that shifts a little is a data-quality question. The
    column clears `COLUMN_PSI_THRESHOLD` and stays under the severity bar."""
    baseline = drift.build_baseline(varied_records(600, seed=1))
    window = varied_records(400, seed=7)
    for index, record in enumerate(window):
        if index % 10 < 6:  # "Two year" goes from about a third to 60 percent
            record["Contract"] = "Two year"

    result = drift.compare(baseline, window)
    assert result["drifted_columns"] == ["Contract"]
    assert result["column_psi"]["Contract"] >= drift.COLUMN_PSI_THRESHOLD
    assert result["max_column_psi"] < drift.SEVERE_COLUMN_PSI
    assert result["drifted"] is False


def test_one_column_moved_severely_is_drift():
    """Detect one severe column shift below the fraction threshold."""
    baseline = drift.build_baseline(varied_records(600, seed=1))
    result = drift.compare(baseline, varied_records(400, seed=6, Contract="Two year"))

    assert result["drifted_columns"] == ["Contract"]
    assert result["drifted_fraction"] < drift.DRIFTED_COLUMN_FRACTION
    assert result["max_column_psi"] >= drift.SEVERE_COLUMN_PSI
    assert result["drifted"] is True


def test_compare_scores_a_window_on_the_baseline_edges():
    # Score the window with the baseline edges.
    baseline = drift.build_baseline(spread(200, "MonthlyCharges", [20.0, 30.0, 40.0]))
    result = drift.compare(baseline, rows(200, MonthlyCharges=500.0))
    assert result["column_psi"]["MonthlyCharges"] > drift.COLUMN_PSI_THRESHOLD


def test_compare_survives_an_empty_window():
    result = drift.compare(drift.build_baseline(rows(10)), [])
    assert result["record_count"] == 0
    assert result["drifted"] is False


def test_distinct_record_count_sees_through_repetition():
    assert drift.distinct_record_count(rows(100)) == 1
    assert drift.distinct_record_count(spread(100, "tenure", [1, 2, 3, 4])) == 4
    assert drift.distinct_record_count([]) == 0


def test_distinct_record_count_ignores_columns_outside_the_contract():
    # Two records that differ only in a non-feature column are one vector.
    assert drift.distinct_record_count([{**VALID, "Churn": "Yes"}, {**VALID, "Churn": "No"}]) == 1


def test_a_repeated_payload_reports_every_column_as_drifted():
    """Report all columns as drifted for a repeated-record window."""
    baseline = drift.build_baseline(varied_records(600, seed=1))
    result = drift.compare(baseline, rows(500))
    assert result["drifted"] is True
    assert len(result["drifted_columns"]) == len(FEATURE_COLUMNS)
    # The record count alone says this window is plentiful.
    assert result["record_count"] == 500
    assert drift.distinct_record_count(rows(500)) == 1


def test_a_targeted_severe_shift_drifts_below_the_column_fraction():
    """The fraction rule alone misses this. Three of nineteen columns is under
    the threshold, and those three carry most of the model's signal."""
    baseline = drift.build_baseline(varied_records(600, seed=1))
    shifted = varied_records(200, seed=4, tenure=180, MonthlyCharges=400.0, TotalCharges=72000.0)
    result = drift.compare(baseline, shifted)

    assert result["drifted_columns"] == ["MonthlyCharges", "TotalCharges", "tenure"]
    assert result["drifted_fraction"] < drift.DRIFTED_COLUMN_FRACTION
    assert result["max_column_psi"] >= drift.SEVERE_COLUMN_PSI
    assert result["drifted"] is True


def test_a_broad_mild_shift_drifts_on_the_fraction_rule():
    """The other way in. Many columns moved, none of them severely."""
    baseline = drift.build_baseline(varied_records(600, seed=1))
    result = drift.compare(baseline, varied_records(200, seed=5))
    # Two independent draws of one population do not drift at all.
    assert result["drifted"] is False
    assert result["max_column_psi"] < drift.SEVERE_COLUMN_PSI
