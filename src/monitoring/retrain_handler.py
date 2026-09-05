"""Start a training pipeline execution for a drift violation.

EventBridge sends drift events from `src.monitoring.drift_handler`. This handler
resolves the champion from the Model Registry at invocation time. It sends the
champion as pipeline parameters. The pipeline evaluates challenger AUC. An
approved challenger invokes `src.serving.deploy_handler`.
"""

import datetime
import hashlib
import json
import os
import re
from typing import Any

import boto3

from src.common.drift import DRIFT_STATUS
from src.common.events import log_event
from src.common.registry import get_champion

sm = boto3.client("sagemaker")

PIPELINE_NAME = os.environ["PIPELINE_NAME"]
MODEL_PACKAGE_GROUP = os.environ["MODEL_PACKAGE_GROUP"]

# Start retraining only for this drift status.
VIOLATION_STATUS = DRIFT_STATUS

# Suppress new executions for this many hours after the latest run starts.
# Persistent drift can emit one violation during each hourly evaluation.
RETRAIN_COOLDOWN_HOURS = int(os.environ.get("RETRAIN_COOLDOWN_HOURS", "6"))

# These statuses identify an active pipeline execution.
ACTIVE_STATUSES = frozenset({"Executing", "Stopping"})

RETRAIN_DESCRIPTION = "drift-triggered retrain"
TOKEN_SAFE_CHAR_RE = re.compile(r"[^0-9A-Za-z_-]")
TOKEN_MAX_LENGTH = 128


def _list_pipeline_executions(max_results: int = 1) -> list[dict[str, Any]]:
    """List recent pipeline executions."""
    summaries = sm.list_pipeline_executions(
        PipelineName=PIPELINE_NAME,
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=max(max_results, 1),
    ).get("PipelineExecutionSummaries", [])
    return [dict(summary) for summary in summaries]


def _normalize_client_request_token(raw: str) -> str:
    """Convert raw input into a valid SageMaker idempotency token."""
    token = TOKEN_SAFE_CHAR_RE.sub("-", raw).strip("-_")
    if not token:
        token = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return token[:TOKEN_MAX_LENGTH]


def _client_request_token(event: dict[str, Any]) -> str:
    """Return the deterministic token for one drift event."""
    raw = event.get("id")
    if isinstance(raw, str) and raw.strip():
        return _normalize_client_request_token(raw)

    detail = json.dumps(event.get("detail", {}), sort_keys=True, separators=(",", ":"))
    return _normalize_client_request_token(f"drift-{detail}")


def blocking_execution(
    summaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return the latest execution when it blocks a new run."""
    if summaries is None:
        summaries = _list_pipeline_executions(1)
    if not summaries:
        return None

    latest: dict[str, Any] = summaries[0]
    if latest.get("PipelineExecutionStatus") in ACTIVE_STATUSES:
        return latest

    started = latest.get("StartTime")
    if not isinstance(started, datetime.datetime):
        return None

    age = datetime.datetime.now(datetime.UTC) - started
    return latest if age < datetime.timedelta(hours=RETRAIN_COOLDOWN_HOURS) else None


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    status = event["detail"].get("status")
    if status != VIOLATION_STATUS:
        log_event(
            "retrain_skipped",
            status=status,
            reason="status_mismatch",
        )
        return {"skipped": status}

    blocking = blocking_execution()
    if blocking is not None:
        reason = (
            "in_flight" if blocking["PipelineExecutionStatus"] in ACTIVE_STATUSES else "cooldown"
        )
        log_event(
            "retrain_suppressed",
            pipeline=PIPELINE_NAME,
            reason=reason,
            latest_status=blocking["PipelineExecutionStatus"],
            cooldown_hours=RETRAIN_COOLDOWN_HOURS,
        )
        return {"suppressed": blocking["PipelineExecutionArn"]}

    champion_arn, champion_auc = get_champion(
        MODEL_PACKAGE_GROUP,
        os.environ["AWS_REGION"],
    )

    execution_arn = sm.start_pipeline_execution(
        PipelineName=PIPELINE_NAME,
        PipelineExecutionDescription=RETRAIN_DESCRIPTION,
        ClientRequestToken=_client_request_token(event),
        PipelineParameters=[
            {"Name": "ChampionAuc", "Value": str(champion_auc)},
            {"Name": "ChampionModelPackageArn", "Value": champion_arn},
        ],
    )["PipelineExecutionArn"]
    log_event(
        "retrain_started",
        pipeline=PIPELINE_NAME,
        execution_arn=execution_arn,
        champion_auc=champion_auc,
        champion_arn=champion_arn,
    )
    return {"retrain_started": execution_arn}
