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
RETRAIN_NO_PROGRESS_LIMIT = int(os.environ.get("RETRAIN_NO_PROGRESS_LIMIT", "3"))

# These statuses identify an active pipeline execution.
ACTIVE_STATUSES = frozenset({"Executing", "Stopping"})
COMPLETED_STATUSES = frozenset({"Succeeded"})

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


def _list_recent_model_package_times(max_results: int) -> list[datetime.datetime]:
    """List the latest model package creation timestamps."""
    max_results = max(max_results, 1)
    summaries = sm.list_model_packages(
        ModelPackageGroupName=MODEL_PACKAGE_GROUP,
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=max_results,
    ).get("ModelPackageSummaryList", [])
    times: list[datetime.datetime] = []
    for summary in summaries:
        created = summary.get("CreationTime")
        if isinstance(created, datetime.datetime):
            times.append(created)
    return times


def _execution_has_model_package(
    execution_start: datetime.datetime,
    package_times: list[datetime.datetime],
    next_execution_start: datetime.datetime | None = None,
) -> bool:
    """Check whether a model package appears for one pipeline execution."""
    for package_time in package_times:
        if package_time <= execution_start:
            break
        if next_execution_start is not None and package_time > next_execution_start:
            continue
        return True
    return False


def _unproductive_retrain_count() -> int:
    """Count consecutive drift-triggered completed retrains without packages."""
    recent_limit = RETRAIN_NO_PROGRESS_LIMIT * 2 + 1
    executions = _list_pipeline_executions(recent_limit)
    package_times = _list_recent_model_package_times(recent_limit)
    next_execution_start: datetime.datetime | None = None
    consecutive = 0
    for execution in executions:
        if execution.get("PipelineExecutionDescription") != RETRAIN_DESCRIPTION:
            break
        execution_status = execution.get("PipelineExecutionStatus")
        started = execution.get("StartTime")
        if not isinstance(started, datetime.datetime):
            continue

        if execution_status in COMPLETED_STATUSES:
            if _execution_has_model_package(
                execution_start=started,
                package_times=package_times,
                next_execution_start=next_execution_start,
            ):
                break
            consecutive += 1
            if consecutive >= RETRAIN_NO_PROGRESS_LIMIT:
                return consecutive

        next_execution_start = started
    return consecutive


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

    unproductive_retrains = _unproductive_retrain_count()
    if unproductive_retrains >= RETRAIN_NO_PROGRESS_LIMIT:
        log_event(
            "retrain_loop_stalled",
            pipeline=PIPELINE_NAME,
            consecutive_unproductive_retrains=unproductive_retrains,
            no_progress_limit=RETRAIN_NO_PROGRESS_LIMIT,
        )
        return {"suppressed": "loop_stalled"}

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
