"""Start a training pipeline execution for a drift violation.

EventBridge sends drift events from `src.monitoring.drift_handler`. This handler
starts the configured pipeline. The pipeline evaluates challenger AUC. An
approved challenger invokes `src.serving.deploy_handler`.
"""

import datetime
import os
import uuid
from typing import Any

import boto3

from src.common.drift import DRIFT_STATUS
from src.common.events import log_event

sm = boto3.client("sagemaker")

PIPELINE_NAME = os.environ["PIPELINE_NAME"]

# Start retraining only for this drift status.
VIOLATION_STATUS = DRIFT_STATUS

# Suppress new executions for this many hours after the latest run starts.
# Persistent drift can emit one violation during each hourly evaluation.
RETRAIN_COOLDOWN_HOURS = int(os.environ.get("RETRAIN_COOLDOWN_HOURS", "6"))

# These statuses identify an active pipeline execution.
ACTIVE_STATUSES = frozenset({"Executing", "Stopping"})

RETRAIN_DESCRIPTION = "drift-triggered retrain"


def blocking_execution() -> dict[str, Any] | None:
    """Return the latest execution when it blocks a new run."""
    summaries = sm.list_pipeline_executions(
        PipelineName=PIPELINE_NAME,
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )["PipelineExecutionSummaries"]
    if not summaries:
        return None

    latest: dict[str, Any] = dict(summaries[0])
    if latest.get("PipelineExecutionStatus") in ACTIVE_STATUSES:
        return latest

    started = latest.get("StartTime")
    if started is None:
        return None
    age = datetime.datetime.now(datetime.UTC) - started
    return latest if age < datetime.timedelta(hours=RETRAIN_COOLDOWN_HOURS) else None


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    status = event["detail"].get("status")
    if status != VIOLATION_STATUS:
        return {"skipped": status}

    blocking = blocking_execution()
    if blocking is not None:
        log_event(
            "retrain_suppressed",
            pipeline=PIPELINE_NAME,
            reason="in_flight"
            if blocking["PipelineExecutionStatus"] in ACTIVE_STATUSES
            else "cooldown",
            latest_status=blocking["PipelineExecutionStatus"],
            cooldown_hours=RETRAIN_COOLDOWN_HOURS,
        )
        return {"suppressed": blocking["PipelineExecutionArn"]}

    # `StartPipelineExecution` requires `ClientRequestToken`.
    execution_arn = sm.start_pipeline_execution(
        PipelineName=PIPELINE_NAME,
        PipelineExecutionDescription=RETRAIN_DESCRIPTION,
        ClientRequestToken=str(uuid.uuid4()),
    )["PipelineExecutionArn"]
    log_event("retrain_started", pipeline=PIPELINE_NAME, execution_arn=execution_arn)
    return {"retrain_started": execution_arn}
