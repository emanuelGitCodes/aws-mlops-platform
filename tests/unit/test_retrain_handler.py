import datetime
import json
import os
from typing import Any
from unittest import mock

import pytest

from src.common import registry
from src.common.features import BASELINE_CHAMPION_AUC, NO_CHAMPION_ARN
from tests.unit.conftest import (
    TEST_MODEL_PACKAGE_ARN_PREFIX,
    TEST_MODEL_PACKAGE_GROUP,
    import_with_stubbed_boto3,
)

retrain_handler = import_with_stubbed_boto3("src.monitoring.retrain_handler")

EXECUTION_ARN = "arn:aws:sagemaker:us-east-1:123456789012:pipeline/test-pipeline/execution/abc"
CHAMPION_ARN = f"{TEST_MODEL_PACKAGE_ARN_PREFIX}/7"
NEXT_CHAMPION_ARN = f"{TEST_MODEL_PACKAGE_ARN_PREFIX}/8"


def _event(status: str, event_id: str | None = None) -> dict[str, Any]:
    """One drift event as `src.monitoring.drift_handler` emits it."""
    event: dict[str, Any] = {"detail": {"drifted_columns": ["tenure"], "status": status}}
    if event_id is not None:
        event["id"] = event_id
    return event


@pytest.mark.parametrize(
    ("champion", "expected_parameters"),
    [
        (
            (CHAMPION_ARN, 0.83),
            [
                {"Name": "ChampionAuc", "Value": "0.83"},
                {"Name": "ChampionModelPackageArn", "Value": CHAMPION_ARN},
            ],
        ),
        (
            (NEXT_CHAMPION_ARN, 0.91),
            [
                {"Name": "ChampionAuc", "Value": "0.91"},
                {"Name": "ChampionModelPackageArn", "Value": NEXT_CHAMPION_ARN},
            ],
        ),
    ],
)
def test_violation_starts_the_pipeline(champion, expected_parameters):
    with (
        mock.patch.object(retrain_handler, "sm") as sm,
        mock.patch.object(
            retrain_handler,
            "get_champion",
            return_value=champion,
        ) as get_champion,
        mock.patch("builtins.print") as log,
    ):
        sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}
        sm.list_pipeline_executions.return_value = {"PipelineExecutionSummaries": []}
        sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}
        result = retrain_handler.handler(_event(retrain_handler.VIOLATION_STATUS), None)

    assert result == {"retrain_started": EXECUTION_ARN}
    call = sm.start_pipeline_execution.call_args.kwargs
    assert call["PipelineName"] == "test-pipeline"
    assert call["PipelineExecutionDescription"]
    assert len(call["ClientRequestToken"]) <= 128
    assert call["PipelineParameters"] == expected_parameters
    get_champion.assert_called_once_with(
        TEST_MODEL_PACKAGE_GROUP,
        os.environ["AWS_REGION"],
    )
    assert json.loads(log.call_args.args[0])["event"] == "retrain_started"


def test_no_approved_package_sends_the_baseline():
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = {"PipelineExecutionSummaries": []}
    sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}
    sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}
    registry_client = mock.Mock()
    registry_client.list_model_packages.return_value = {"ModelPackageSummaryList": []}

    with (
        mock.patch.object(retrain_handler, "sm", sm),
        mock.patch.object(registry.boto3, "client", return_value=registry_client),
        mock.patch("builtins.print"),
    ):
        result = retrain_handler.handler(_event(retrain_handler.VIOLATION_STATUS), None)

    assert result == {"retrain_started": EXECUTION_ARN}
    call = sm.start_pipeline_execution.call_args.kwargs
    assert call["PipelineParameters"] == [
        {"Name": "ChampionAuc", "Value": str(BASELINE_CHAMPION_AUC)},
        {"Name": "ChampionModelPackageArn", "Value": NO_CHAMPION_ARN},
    ]
    registry_client.describe_model_package.assert_not_called()


@pytest.mark.parametrize("status", ["CompletedWithViolations", "Evaluated", None])
def test_non_violation_statuses_do_not_retrain(status):
    """Skip every event status except the platform violation status."""
    with (
        mock.patch.object(retrain_handler, "sm") as sm,
        mock.patch("builtins.print") as log,
    ):
        result = retrain_handler.handler(_event(status), None)

    assert result == {"skipped": status}
    logged = json.loads(log.call_args.args[0])
    assert logged["event"] == "retrain_skipped"
    assert logged["status"] == status
    sm.start_pipeline_execution.assert_not_called()


def test_missing_status_is_skipped_not_an_error():
    """Skip an event with no status."""
    with (
        mock.patch.object(retrain_handler, "sm") as sm,
        mock.patch("builtins.print") as log,
    ):
        result = retrain_handler.handler({"detail": {}}, None)

    assert result == {"skipped": None}
    assert json.loads(log.call_args.args[0])["event"] == "retrain_skipped"
    sm.start_pipeline_execution.assert_not_called()


def _summary(status="Succeeded", hours_ago=99.0, arn=EXECUTION_ARN):
    return {
        "PipelineExecutionSummaries": [
            {
                "PipelineExecutionArn": arn,
                "PipelineExecutionStatus": status,
                "PipelineExecutionDescription": retrain_handler.RETRAIN_DESCRIPTION,
                "StartTime": datetime.datetime.now(datetime.UTC)
                - datetime.timedelta(hours=hours_ago),
            }
        ]
    }


def _violation(sm: mock.Mock, event: dict[str, Any] | None = None) -> dict[str, Any]:
    if event is None:
        event = _event(retrain_handler.VIOLATION_STATUS)
    with (
        mock.patch.object(retrain_handler, "sm", sm),
        mock.patch.object(
            retrain_handler,
            "get_champion",
            return_value=(NO_CHAMPION_ARN, BASELINE_CHAMPION_AUC),
        ),
        mock.patch("builtins.print"),
    ):
        return retrain_handler.handler(event, None)


def test_a_run_already_in_flight_suppresses_a_second_one():
    """Two runs against one pipeline duplicate the cost and race each other."""
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = _summary(status="Executing", hours_ago=0.1)
    sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}

    assert _violation(sm) == {"suppressed": EXECUTION_ARN}
    sm.start_pipeline_execution.assert_not_called()


def test_a_recent_run_suppresses_the_next_violation():
    """Suppress another violation during the retraining cooldown."""
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = _summary(
        status="Succeeded", hours_ago=retrain_handler.RETRAIN_COOLDOWN_HOURS - 1
    )
    sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}

    assert _violation(sm) == {"suppressed": EXECUTION_ARN}
    sm.start_pipeline_execution.assert_not_called()


def test_a_violation_after_the_cooldown_retrains():
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = _summary(
        status="Succeeded", hours_ago=retrain_handler.RETRAIN_COOLDOWN_HOURS + 1
    )
    sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}
    sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}

    assert _violation(sm) == {"retrain_started": EXECUTION_ARN}
    sm.start_pipeline_execution.assert_called_once()


def test_the_first_ever_violation_retrains():
    """Start retraining when no earlier execution exists."""
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = {"PipelineExecutionSummaries": []}
    sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}
    sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}

    assert _violation(sm) == {"retrain_started": EXECUTION_ARN}
    sm.start_pipeline_execution.assert_called_once()


def test_suppression_is_logged_with_its_reason():
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = _summary(status="Executing", hours_ago=0.1)
    sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}
    with (
        mock.patch.object(retrain_handler, "sm", sm),
        mock.patch("builtins.print") as log,
    ):
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


def test_event_id_is_used_as_request_token():
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = {"PipelineExecutionSummaries": []}
    sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}
    sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}

    result = _violation(sm, _event(retrain_handler.VIOLATION_STATUS, "drift:event#id"))

    assert result == {"retrain_started": EXECUTION_ARN}
    call = sm.start_pipeline_execution.call_args.kwargs
    assert call["ClientRequestToken"] == "drift-event-id"


def test_missing_event_id_uses_deterministic_request_token():
    sm = mock.Mock()
    sm.list_pipeline_executions.return_value = {"PipelineExecutionSummaries": []}
    sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}
    sm.start_pipeline_execution.return_value = {"PipelineExecutionArn": EXECUTION_ARN}

    _violation(sm)
    _violation(sm)
    calls = sm.start_pipeline_execution.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["ClientRequestToken"] == calls[1].kwargs["ClientRequestToken"]
