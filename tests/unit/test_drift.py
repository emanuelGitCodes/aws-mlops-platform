"""The drift statistic: binning, PSI, and the baseline contract."""

import json

import pytest

from src.common import drift
from src.common.features import FEATURE_COLUMNS, NUMERIC
from tests.unit.conftest import VALID


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
    # SeniorCitizen holds 0 and 1, so its only edge is 0.0. Right-open binning
    # would put both values in bucket 1 and hide every shift in this column.
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


def test_compare_reports_no_drift_against_the_same_population():
    population = spread(200, "tenure", [1, 12, 24, 48, 60])
    result = drift.compare(drift.build_baseline(population), population)
    assert result["drifted"] is False
    assert result["drifted_columns"] == []
    assert result["record_count"] == 200


def test_compare_detects_a_shifted_population():
    # The shift `scripts/send_drift_traffic.py` sends: extreme tenure and
    # charges, on a month-to-month fiber contract.
    baseline = drift.build_baseline(spread(200, "tenure", [1, 6, 12, 24, 36]))
    shifted = spread(200, "tenure", [150, 160, 170, 180, 190])
    for row in shifted:
        row["MonthlyCharges"] = 400.0
        row["TotalCharges"] = 60000.0
        row["Contract"] = "Two year"
        row["InternetService"] = "DSL"
        row["PaymentMethod"] = "Mailed check"
        row["gender"] = "Male"
    result = drift.compare(baseline, shifted)
    assert result["drifted"] is True
    assert "tenure" in result["drifted_columns"]
    assert result["drifted_fraction"] >= drift.DRIFTED_COLUMN_FRACTION


def test_one_moved_column_is_not_enough_to_call_drift():
    # A single column is a data-quality question, not a changed population.
    baseline = drift.build_baseline(spread(200, "tenure", [1, 6, 12, 24, 36]))
    result = drift.compare(baseline, rows(200, tenure=200))
    assert result["drifted_columns"] == ["tenure"]
    assert result["drifted"] is False


def test_compare_scores_a_window_on_the_baseline_edges():
    # A window binned on its own edges would report zero drift for any
    # distribution, because it would always be compared with itself.
    baseline = drift.build_baseline(spread(200, "MonthlyCharges", [20.0, 30.0, 40.0]))
    result = drift.compare(baseline, rows(200, MonthlyCharges=500.0))
    assert result["column_psi"]["MonthlyCharges"] > drift.COLUMN_PSI_THRESHOLD


def test_compare_survives_an_empty_window():
    result = drift.compare(drift.build_baseline(rows(10)), [])
    assert result["record_count"] == 0
    assert result["drifted"] is False
