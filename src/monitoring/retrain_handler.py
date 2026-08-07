"""Retrain Lambda: a Model Monitor violation starts a new training-pipeline
execution.

EventBridge triggers it on "SageMaker Model Monitor Execution Status Change".
This closes the drift loop. The monitor finds violations. This handler starts
the pipeline. The pipeline gates a challenger on test AUC. An approved
challenger redeploys the endpoint through ``src.serving.deploy_handler``.

Keep this handler in ``src/``, not inline in the CDK stack. Ruff, mypy, and
pytest see a real module. They do not see a string literal.
"""

import os
import uuid
from typing import Any

import boto3

from src.common.events import log_event

sm = boto3.client("sagemaker")

PIPELINE_NAME = os.environ["PIPELINE_NAME"]

# The only monitoring outcome that must retrain. Model Monitor also reports
# Completed, Failed, and Stopped. None of those three is drift.
VIOLATION_STATUS = "CompletedWithViolations"

RETRAIN_DESCRIPTION = "drift-triggered retrain"


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    status = event["detail"].get("MonitoringExecutionStatus")
    if status != VIOLATION_STATUS:
        return {"skipped": status}

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
