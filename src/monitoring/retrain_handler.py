"""Retrain Lambda: a drift violation starts a new training-pipeline execution.

EventBridge triggers it on the platform's own drift event, which
``src.monitoring.drift_handler`` emits. This closes the drift loop. The drift
job finds violations. This handler starts the pipeline. The pipeline gates a
challenger on test AUC. An approved challenger redeploys the endpoint through
``src.serving.deploy_handler``.

Keep this handler in ``src/``, not inline in the CDK stack. Ruff, mypy, and
pytest see a real module. They do not see a string literal.
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

# The only outcome that must retrain. The drift job also reports an evaluated
# window with no drift, and a window too small to score. Neither is drift.
VIOLATION_STATUS = DRIFT_STATUS

# Hours after a run starts during which another violation must not start a
# second one. The drift job evaluates hourly, and a shift that persists
# violates on each evaluation.
#
# Retraining cannot end that shift on its own. The pipeline trains on
# `curated/telco/`, and captured traffic lands under the artifacts bucket's
# capture prefix; the two never meet. A run therefore produces the same model
# and the same baseline until new data is ingested, so the violation repeats
# whatever the run concludes. Only newly ingested data changes the answer.
RETRAIN_COOLDOWN_HOURS = int(os.environ.get("RETRAIN_COOLDOWN_HOURS", "6"))

# Statuses that mean a run is still going. Starting a second one against the
# same pipeline duplicates the cost and races the first to the registry.
ACTIVE_STATUSES = frozenset({"Executing", "Stopping"})

RETRAIN_DESCRIPTION = "drift-triggered retrain"


def blocking_execution() -> dict[str, Any] | None:
    """Return the most recent execution when it should suppress a new one.

    A violation is still reported by the drift job and still logged here. This
    only declines to spend a training run on it.
    """
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

    # StartPipelineExecution models ClientRequestToken as required. Botocore
    # fills the token in when the caller omits it. Pass the same value it would
    # generate.
    execution_arn = sm.start_pipeline_execution(
        PipelineName=PIPELINE_NAME,
        PipelineExecutionDescription=RETRAIN_DESCRIPTION,
        ClientRequestToken=str(uuid.uuid4()),
    )["PipelineExecutionArn"]
    log_event("retrain_started", pipeline=PIPELINE_NAME, execution_arn=execution_arn)
    return {"retrain_started": execution_arn}
