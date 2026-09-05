"""Update the serverless endpoint after a Model Registry approval event.

EventBridge triggers it on "SageMaker Model Package State Change" when a
package in this group becomes Approved. The handler creates a Model and an
EndpointConfig for the new package, then points the endpoint at it. On the
first deploy, it creates the endpoint.
"""

import hashlib
import os
import time
from collections.abc import Callable
from typing import Any

import boto3

from src.common.events import log_event

sm = boto3.client("sagemaker")

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]
EXECUTION_ROLE_ARN = os.environ["EXECUTION_ROLE_ARN"]
MEMORY_MB = int(os.environ.get("MEMORY_MB", "2048"))
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", "5"))

_NOT_FOUND_CODES = {"ValidationException", "ResourceNotFound", "ResourceNotFoundException"}
_RESOURCE_IN_USE_CODES = {"ResourceInUse", "ResourceInUseException"}
_IN_FLIGHT_ENDPOINT_STATES = {"Creating", "Updating", "RollingBack", "SystemUpdating"}


def _is_resource_not_found(error: Exception) -> bool:
    details = (getattr(error, "response", None) or {}).get("Error", {})
    message = str(details.get("Message", "")).lower()
    return details.get("Code") in _NOT_FOUND_CODES and message.startswith("could not find ")


def _is_endpoint_not_found(error: Exception) -> bool:
    """Return true when SageMaker reports a missing endpoint."""
    return _is_resource_not_found(error)


def _is_resource_in_use(error: Exception) -> bool:
    details = (getattr(error, "response", None) or {}).get("Error", {})
    code = details.get("Code")
    return (
        code in _RESOURCE_IN_USE_CODES
        or code == "ValidationException"
        and "already exist" in str(details.get("Message", "")).lower()
    )


def _resource_names(package_arn: str) -> tuple[str, str]:
    """Return stable names for one package and serverless configuration."""
    suffix = hashlib.sha256(f"{package_arn}:{MEMORY_MB}:{MAX_CONCURRENCY}".encode()).hexdigest()[
        :16
    ]
    names = (f"{ENDPOINT_NAME}-model-{suffix}", f"{ENDPOINT_NAME}-config-{suffix}")
    if max(map(len, names)) > 63:
        raise ValueError(f"endpoint name {ENDPOINT_NAME!r} is too long for SageMaker names")
    return names


def _model_matches(description: dict[str, Any], package_arn: str) -> bool:
    """Return true when a model has the expected role and package."""
    containers = description.get("Containers") or [description.get("PrimaryContainer")]
    return (
        description.get("ExecutionRoleArn") == EXECUTION_ROLE_ARN
        and isinstance(containers, list)
        and len(containers) == 1
        and isinstance(containers[0], dict)
        and containers[0].get("ModelPackageName") == package_arn
    )


def _config_matches(description: dict[str, Any], model_name: str) -> bool:
    """Return true when an endpoint config has the expected variant."""
    variants = description.get("ProductionVariants") or []
    if not isinstance(variants, list) or len(variants) != 1:
        return False
    variant = variants[0]
    if not isinstance(variant, dict):
        return False
    serverless = variant.get("ServerlessConfig") or {}
    return (
        isinstance(serverless, dict)
        and not serverless.get("ProvisionedConcurrency")
        and variant.get("VariantName") == "AllTraffic"
        and variant.get("ModelName") == model_name
        and serverless.get("MemorySizeInMB") == MEMORY_MB
        and serverless.get("MaxConcurrency") == MAX_CONCURRENCY
    )


def _ensure_resource(
    describe: Callable[..., Any],
    create: Callable[..., Any],
    describe_kwargs: dict[str, str],
    create_kwargs: dict[str, Any],
    matcher: Callable[[dict[str, Any]], bool],
    resource: str,
) -> None:
    """Create a missing resource or reuse an exact concurrent match."""
    try:
        description = describe(**describe_kwargs)
    except sm.exceptions.ClientError as error:
        if not _is_resource_not_found(error):
            raise
    else:
        if not matcher(description):
            raise RuntimeError(f"existing SageMaker {resource} does not match approval")
        return

    try:
        create(**create_kwargs)
    except sm.exceptions.ClientError as error:
        if not _is_resource_in_use(error):
            raise
        description = describe(**describe_kwargs)
        if not matcher(description):
            raise RuntimeError(
                f"concurrent SageMaker {resource} does not match approval"
            ) from error


def _endpoint_action(endpoint: dict[str, Any], config_name: str) -> str | None:
    """Return a safe no-op action, or None when an update is required."""
    status = endpoint.get("EndpointStatus")
    current = endpoint.get("EndpointConfigName")
    pending = endpoint.get("PendingDeploymentSummary") or {}
    pending_config = pending.get("EndpointConfigName") if isinstance(pending, dict) else None
    if status in _IN_FLIGHT_ENDPOINT_STATES:
        if pending_config and pending_config != config_name:
            raise RuntimeError(f"endpoint is {status} with another pending config")
        if current == config_name or pending_config == config_name:
            return "in_progress"
        raise RuntimeError(f"endpoint is {status} with config {current!r}")
    if status == "InService" and current == config_name:
        return "unchanged"
    if status in {"Failed", "UpdateRollbackFailed", "Deleting"}:
        raise RuntimeError(f"endpoint is {status} with config {current!r}")
    if status != "InService":
        raise RuntimeError(f"endpoint has unexpected status {status!r}")
    return None


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    detail = event["detail"]
    if detail.get("ModelApprovalStatus") != "Approved":
        log_event(
            "deploy_skipped",
            reason="not_an_approval",
            status=detail.get("ModelApprovalStatus"),
        )
        return {"skipped": "not an approval"}
    package_arn = detail["ModelPackageArn"]

    suffix = str(int(time.time()))
    model_name = f"{ENDPOINT_NAME}-model-{suffix}"
    config_name = f"{ENDPOINT_NAME}-config-{suffix}"

    sm.create_model(
        ModelName=model_name,
        ExecutionRoleArn=EXECUTION_ROLE_ARN,
        Containers=[{"ModelPackageName": package_arn}],
    )
    # SageMaker Serverless Inference does not support `DataCaptureConfig`.
    sm.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[
            {
                "VariantName": "AllTraffic",
                "ModelName": model_name,
                "ServerlessConfig": {
                    "MemorySizeInMB": MEMORY_MB,
                    "MaxConcurrency": MAX_CONCURRENCY,
                },
            }
        ],
    )

    # Create only when `describe_endpoint` reports a missing endpoint.
    # Propagate all other client errors.
    try:
        sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
    except sm.exceptions.ClientError as error:
        if not _is_endpoint_not_found(error):
            raise
        sm.create_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
        action = "created"
    else:
        sm.update_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
        action = "updated"

    package = sm.describe_model_package(ModelPackageName=package_arn)
    test_auc = package.get("CustomerMetadataProperties", {}).get("test_auc")
    log_event(
        "endpoint_update_requested",
        action=action,
        endpoint=ENDPOINT_NAME,
        model_package_arn=package_arn,
        test_auc=test_auc,
    )
    return {
        "endpoint": ENDPOINT_NAME,
        "action": action,
        "package": package_arn,
        "test_auc": test_auc,
    }
