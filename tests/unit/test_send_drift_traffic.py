"""Test the drift-traffic helper and its isolated feature shift."""

import sys
from unittest import mock

import pytest

from scripts import send_drift_traffic
from src.common import drift
from src.common.features import FEATURE_COLUMNS, encode_features
from src.common.schema import CustomerRecord
from tests.unit.conftest import varied_records

FIXTURE = [{"record": record, "label": 0} for record in varied_records(500, seed=21)]


def test_the_shift_touches_only_the_columns_it_names():
    window = send_drift_traffic.build_window(FIXTURE, 200)
    background = {record["record"]["gender"] for record in FIXTURE}

    for record in window:
        assert set(record) == set(FEATURE_COLUMNS)
        assert 120 <= record["tenure"] <= 200
        assert 300 <= record["MonthlyCharges"] <= 500
        assert record["TotalCharges"] == pytest.approx(
            round(record["tenure"] * record["MonthlyCharges"], 2)
        )
        # Require each shifted record to pass the API schema.
        CustomerRecord.model_validate(record)
        assert len(encode_features(record)) == len(FEATURE_COLUMNS)

    # Preserve untouched columns from the background population.
    assert {record["gender"] for record in window} <= background


def test_the_generated_window_drifts_on_severity_not_on_breadth():
    """The three shifted columns carry the signal, and they are under the
    drifted-column fraction. Only the severity rule can catch this."""
    baseline = drift.build_baseline(varied_records(600, seed=22))
    result = drift.compare(baseline, send_drift_traffic.build_window(FIXTURE, 200))

    assert result["drifted_columns"] == sorted(send_drift_traffic.SHIFTED_COLUMNS)
    assert result["drifted_fraction"] < drift.DRIFTED_COLUMN_FRACTION
    assert result["max_column_psi"] >= drift.SEVERE_COLUMN_PSI
    assert result["drifted"] is True


def test_the_unshifted_background_does_not_drift():
    """The control. If the background alone drifts, the demo proves nothing."""
    baseline = drift.build_baseline(varied_records(600, seed=22))
    result = drift.compare(baseline, [record["record"] for record in FIXTURE[:200]])

    assert result["drifted"] is False
    assert result["drifted_columns"] == []


def test_the_window_stays_diverse_enough_to_be_scored():
    """Keep the generated window above the distinct-record threshold."""
    window = send_drift_traffic.build_window(FIXTURE, 200)
    assert drift.distinct_record_count(window) >= 25


def test_build_window_is_deterministic():
    assert send_drift_traffic.build_window(FIXTURE, 20) == send_drift_traffic.build_window(
        FIXTURE, 20
    )


def test_build_window_does_not_mutate_the_fixture():
    before = [dict(record["record"]) for record in FIXTURE]
    send_drift_traffic.build_window(FIXTURE, 50)
    assert [record["record"] for record in FIXTURE] == before


def _run_main(argv, post, fixture=FIXTURE):
    with (
        mock.patch.object(sys, "argv", argv),
        mock.patch.object(send_drift_traffic, "post_prediction", post),
        mock.patch.object(send_drift_traffic, "load_fixture", return_value=fixture),
        mock.patch.object(send_drift_traffic, "resolve_fixture_s3_uri", return_value="s3://b/f"),
        # Stub the signing session created by `main`.
        mock.patch.object(send_drift_traffic.boto3, "Session"),
        mock.patch("builtins.print"),
    ):
        send_drift_traffic.main()


def test_main_sends_the_requested_number_of_records():
    post = mock.Mock(return_value={"churn_probability": 0.9, "churn": True})
    _run_main(
        [
            "send_drift_traffic.py",
            "--api-url",
            "https://x.test",
            "--pipeline-execution-arn",
            "arn:aws:sagemaker:us-east-1:123456789012:pipeline/p/execution/e",
            "-n",
            "5",
        ],
        post,
    )

    assert post.call_count == 5
    for record in [call.args[1] for call in post.call_args_list]:
        CustomerRecord.model_validate(record)


def test_main_requires_an_api_url():
    with pytest.raises(SystemExit):
        _run_main(
            ["send_drift_traffic.py", "--fixture-s3-uri", "s3://b/f"],
            mock.Mock(),
        )


def test_main_rejects_a_fixture_that_no_longer_matches_the_schema():
    """Reject an invalid fixture before the first request."""
    broken = [{"record": {**FIXTURE[0]["record"], "Contract": "Fortnightly"}}]
    with pytest.raises(Exception, match="Contract"):
        _run_main(
            [
                "send_drift_traffic.py",
                "--api-url",
                "https://x.test",
                "--fixture-s3-uri",
                "s3://b/f",
            ],
            mock.Mock(),
            fixture=broken,
        )
