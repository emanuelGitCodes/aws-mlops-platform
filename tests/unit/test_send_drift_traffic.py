"""Unit tests for the drift-traffic demo helper.

This module asserts that the hardcoded demo record stays a valid
`CustomerRecord` and that the traffic it sends is actually distribution-shifted.
A schema change breaks both without any error. The script runs by hand during
a demo, so nothing else reports it.
"""

import sys
from unittest import mock

import pytest

from scripts import send_drift_traffic
from src.common.features import FEATURE_COLUMNS, encode_features
from src.common.schema import CustomerRecord


def test_demo_record_matches_the_shared_schema():
    """The record is written out by hand; the schema is the source of truth."""
    CustomerRecord.model_validate(send_drift_traffic.BASE)
    assert set(send_drift_traffic.BASE) == set(FEATURE_COLUMNS)
    # It must also survive encoding, a stricter check than validation.
    assert len(encode_features(send_drift_traffic.BASE)) == len(FEATURE_COLUMNS)


def _run_main(argv, post):
    with (
        mock.patch.object(sys, "argv", argv),
        mock.patch.object(send_drift_traffic, "post_prediction", post),
        mock.patch("builtins.print"),
    ):
        send_drift_traffic.main()


def test_main_sends_the_requested_number_of_shifted_records():
    post = mock.Mock(return_value={"churn_probability": 0.9, "churn": True})
    argv = ["send_drift_traffic.py", "--url", "https://x.test", "--api-key", "k", "-n", "5"]
    _run_main(argv, post)

    assert post.call_count == 5
    sent = [call.args[2] for call in post.call_args_list]
    for record in sent:
        # This is shifted well outside the training distribution, which is
        # the point. Model Monitor has to see drift.
        assert 120 <= record["tenure"] <= 200
        assert 300 <= record["MonthlyCharges"] <= 500
        assert record["TotalCharges"] == pytest.approx(
            round(record["tenure"] * record["MonthlyCharges"], 2)
        )
        # It must stay a valid record. Otherwise the API returns a 422 and
        # the demo produces no traffic.
        CustomerRecord.model_validate(record)


def test_main_is_deterministic():
    """Seeded RNG: two runs must send byte-identical traffic."""
    first, second = mock.Mock(), mock.Mock()
    argv = ["send_drift_traffic.py", "--url", "https://x.test", "--api-key", "k", "-n", "3"]
    _run_main(argv, first)
    _run_main(argv, second)

    assert [call.args[2] for call in first.call_args_list] == [
        call.args[2] for call in second.call_args_list
    ]


def test_main_does_not_mutate_the_shared_base_record():
    """Each request copies BASE; mutating it would shift every later record."""
    before = dict(send_drift_traffic.BASE)
    _run_main(
        ["send_drift_traffic.py", "--url", "https://x.test", "--api-key", "k", "-n", "3"],
        mock.Mock(),
    )
    assert send_drift_traffic.BASE == before


def test_main_exits_when_the_demo_record_drifts_from_the_feature_columns():
    """The guard that replaced a bare `assert`, which -O would have stripped."""
    drifted = {**send_drift_traffic.BASE, "UnknownColumn": "x"}
    with mock.patch.object(send_drift_traffic, "BASE", drifted):
        with pytest.raises(SystemExit, match="UnknownColumn"):
            _run_main(
                ["send_drift_traffic.py", "--url", "https://x.test", "--api-key", "k"],
                mock.Mock(),
            )
