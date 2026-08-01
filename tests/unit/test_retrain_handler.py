import json
from unittest import mock

import pytest

from tests.unit.conftest import import_with_stubbed_boto3

retrain_handler = import_with_stubbed_boto3("src.monitoring.retrain_handler")

EXECUTION_ARN = "arn:aws:sagemaker:us-east-1:123456789012:pipeline/test-pipeline/execution/abc"


def _event(status: str) -> dict:
    return {"detail": {"MonitoringScheduleName": "x", "MonitoringExecutionStatus": status}}


def test_violation_starts_the_pipeline():
    with (
        mock.patch.object(retrain_handler, "sm") as sm,
        mock.patch("builtins.print") as log,
    ):
        sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}
        result = retrain_handler.handler(_event("CompletedWithViolations"), None)

    assert result == {"retrain_started": EXECUTION_ARN}
    call = sm.start_pipeline_execution.call_args.kwargs
    assert call["PipelineName"] == "test-pipeline"
    assert call["PipelineExecutionDescription"]
    assert json.loads(log.call_args.args[0]) == {
        "event": "retrain_started",
        "pipeline": "test-pipeline",
        "execution_arn": EXECUTION_ARN,
    }


@pytest.mark.parametrize("status", ["Completed", "Failed", "Stopped", "InProgress", None])
def test_non_violation_statuses_do_not_retrain(status):
    """Only a violation may retrain: every other outcome is a no-op.

    Retraining on `Completed` would put the pipeline in a loop, and each run
    costs a training job.
    """
    with mock.patch.object(retrain_handler, "sm") as sm:
        result = retrain_handler.handler(_event(status), None)

    assert result == {"skipped": status}
    sm.start_pipeline_execution.assert_not_called()


def test_missing_status_is_skipped_not_an_error():
    """A malformed event must not raise -- EventBridge would retry it."""
    with mock.patch.object(retrain_handler, "sm") as sm:
        result = retrain_handler.handler({"detail": {}}, None)

    assert result == {"skipped": None}
    sm.start_pipeline_execution.assert_not_called()
