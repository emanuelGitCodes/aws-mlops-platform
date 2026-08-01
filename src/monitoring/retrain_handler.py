"""Retrain Lambda: a Model Monitor violation -> a new training-pipeline execution.

Triggered by EventBridge on "SageMaker Model Monitor Execution Status Change".
This is the closing edge of the drift loop: the monitor finds violations, this
starts the pipeline, the pipeline gates a challenger on test AUC, and an
approved challenger redeploys the endpoint via ``src.serving.deploy_handler``.

Previously this lived as a string literal passed to ``Code.from_inline`` in
``infra/stacks/monitoring_stack.py``, where ruff, mypy and pytest could not see
it -- all three are blocking gates in CI, so the one handler that closes the
loop was also the only one with no static checking and no tests.
"""

import os
import uuid
from typing import Any

import boto3

from src.common.events import log_event

sm = boto3.client("sagemaker")

PIPELINE_NAME = os.environ["PIPELINE_NAME"]

# The only monitoring outcome that should retrain. Model Monitor also reports
# Completed (no violations), Failed, and Stopped; none of those are drift.
VIOLATION_STATUS = "CompletedWithViolations"

RETRAIN_DESCRIPTION = "drift-triggered retrain"


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    status = event["detail"].get("MonitoringExecutionStatus")
    if status != VIOLATION_STATUS:
        return {"skipped": status}

    # StartPipelineExecution models ClientRequestToken as required; botocore
    # auto-fills idempotency tokens, so the inline version omitted it and still
    # worked. Passing the same thing botocore would generate keeps behaviour
    # identical and the call honestly typed.
    execution_arn = sm.start_pipeline_execution(
        PipelineName=PIPELINE_NAME,
        PipelineExecutionDescription=RETRAIN_DESCRIPTION,
        ClientRequestToken=str(uuid.uuid4()),
    )["PipelineExecutionArn"]
    log_event("retrain_started", pipeline=PIPELINE_NAME, execution_arn=execution_arn)
    return {"retrain_started": execution_arn}
