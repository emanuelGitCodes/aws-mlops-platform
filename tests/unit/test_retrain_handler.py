import datetime
import json
from unittest import mock

import pytest

from tests.unit.conftest import import_with_stubbed_boto3

retrain_handler = import_with_stubbed_boto3("src.monitoring.retrain_handler")

EXECUTION_ARN = "arn:aws:sagemaker:us-east-1:123456789012:pipeline/test-pipeline/execution/abc"


def _event(status: str) -> dict:
    """One drift event as `src.monitoring.drift_handler` emits it."""
    return {"detail": {"drifted_columns": ["tenure"], "status": status}}


def test_violation_starts_the_pipeline():
    with (
        mock.patch.object(retrain_handler, "sm") as sm,
        mock.patch("builtins.print") as log,
    ):
        sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}
        sm.list_pipeline_executions.return_value = {"PipelineExecutionSummaries": []}
        result = retrain_handler.handler(_event(retrain_handler.VIOLATION_STATUS), None)

    assert result == {"retrain_started": EXECUTION_ARN}
    call = sm.start_pipeline_execution.call_args.kwargs
    assert call["PipelineName"] == "test-pipeline"
    assert call["PipelineExecutionDescription"]
    assert json.loads(log.call_args.args[0]) == {
        "event": "retrain_started",
        "pipeline": "test-pipeline",
        "execution_arn": EXECUTION_ARN,
    }


@pytest.mark.parametrize("status", ["CompletedWithViolations", "Evaluated", None])
def test_non_violation_statuses_do_not_retrain(status):
    """Skip every event status except the platform violation status."""
    with mock.patch.object(retrain_handler, "sm") as sm:
        result = retrain_handler.handler(_event(status), None)

    assert result == {"skipped": status}
    sm.start_pipeline_execution.assert_not_called()


def test_missing_status_is_skipped_not_an_error():
    """Skip an event with no status."""
    with mock.patch.object(retrain_handler, "sm") as sm:
        result = retrain_handler.handler({"detail": {}}, None)

    assert result == {"skipped": None}
    sm.start_pipeline_execution.assert_not_called()


def _summary(status="Succeeded", hours_ago=99.0, arn=EXECUTION_ARN):
    return {
        "PipelineExecutionSummaries": [
            {
                "PipelineExecutionArn": arn,
                "PipelineExecutionStatus": status,
                "StartTime": datetime.datetime.now(datetime.UTC)
                - datetime.timedelta(hours=hours_ago),
            }
        ]
    }


def _violation(sm):
    with mock.patch.object(retrain_handler, "sm", sm), mock.patch("builtins.print"):
        return retrain_handler.handler(_event(retrain_handler.VIOLATION_STATUS), None)


def test_a_run_already_in_flight_suppresses_a_second_one():
    """Two runs against one pipeline duplicate the cost and race each other."""
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = _summary(status="Executing", hours_ago=0.1)

    assert _violation(sm) == {"suppressed": EXECUTION_ARN}
    sm.start_pipeline_execution.assert_not_called()


def test_a_recent_run_suppresses_the_next_violation():
    """Suppress another violation during the retraining cooldown."""
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = _summary(
        status="Succeeded", hours_ago=retrain_handler.RETRAIN_COOLDOWN_HOURS - 1
    )

    assert _violation(sm) == {"suppressed": EXECUTION_ARN}
    sm.start_pipeline_execution.assert_not_called()


def test_a_violation_after_the_cooldown_retrains():
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = _summary(
        status="Succeeded", hours_ago=retrain_handler.RETRAIN_COOLDOWN_HOURS + 1
    )
    sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}

    assert _violation(sm) == {"retrain_started": EXECUTION_ARN}
    sm.start_pipeline_execution.assert_called_once()


def test_the_first_ever_violation_retrains():
    """Start retraining when no earlier execution exists."""
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = {"PipelineExecutionSummaries": []}
    sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}

    assert _violation(sm) == {"retrain_started": EXECUTION_ARN}
    sm.start_pipeline_execution.assert_called_once()


def test_suppression_is_logged_with_its_reason():
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = _summary(status="Executing", hours_ago=0.1)
    with mock.patch.object(retrain_handler, "sm", sm), mock.patch("builtins.print") as log:
        retrain_handler.handler(_event(retrain_handler.VIOLATION_STATUS), None)

    logged = json.loads(log.call_args.args[0])
    assert logged["event"] == "retrain_suppressed"
    assert logged["reason"] == "in_flight"


def test_a_non_violation_never_reaches_the_cooldown_lookup():
    """Skip the cooldown lookup for a non-violation event."""
    sm = mock.Mock()
    with mock.patch.object(retrain_handler, "sm", sm):
        retrain_handler.handler(_event("Evaluated"), None)
    sm.list_pipeline_executions.assert_not_called()
