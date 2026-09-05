"""Update the serverless endpoint after a Model Registry approval event.

EventBridge triggers it on "SageMaker Model Package State Change" when a
package in this group becomes Approved. The handler creates a Model and an
EndpointConfig for the new package, then points the endpoint at it. On the
first deploy, it creates the endpoint.
"""

import hashlib
import os
from collections.abc import Callable, Mapping
from typing import Any

import boto3

from src.common.events import log_event
from src.common.registry import extract_model_package_name

sm = boto3.client("sagemaker")

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]
EXECUTION_ROLE_ARN = os.environ["EXECUTION_ROLE_ARN"]
MEMORY_MB = int(os.environ.get("MEMORY_MB", "2048"))
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", "5"))

_NOT_FOUND_CODES = {"ValidationException", "ResourceNotFound", "ResourceNotFoundException"}
_RESOURCE_IN_USE_CODES = {"ResourceInUse", "ResourceInUseException"}
_IN_FLIGHT_ENDPOINT_STATES = {"Creating", "Updating", "SystemUpdating"}


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


def _model_matches(description: Mapping[str, Any], package_arn: str) -> bool:
    """Return true when a model has the expected role and package."""
    if description.get("ExecutionRoleArn") != EXECUTION_ROLE_ARN:
        return False
    try:
        return extract_model_package_name(description) == package_arn
    except ValueError:
        return False


def _config_matches(description: Mapping[str, Any], model_name: str | None = None) -> bool:
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
        and (model_name is None or variant.get("ModelName") == model_name)
        and serverless.get("MemorySizeInMB") == MEMORY_MB
        and serverless.get("MaxConcurrency") == MAX_CONCURRENCY
    )


def _ensure_resource(
    describe: Callable[..., Any],
    create: Callable[..., Any],
    describe_kwargs: dict[str, str],
    create_kwargs: dict[str, Any],
    matcher: Callable[[Mapping[str, Any]], bool],
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


def _endpoint_action(endpoint: Mapping[str, Any], config_name: str) -> str | None:
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
    if status in {"Failed", "UpdateRollbackFailed", "RollingBack", "Deleting"}:
        raise RuntimeError(f"endpoint is {status} with config {current!r}")
    if status != "InService":
        raise RuntimeError(f"endpoint has unexpected status {status!r}")
    return None


def _current_deployment_matches(endpoint: Mapping[str, Any], package_arn: str) -> bool:
    """Return true when an InService endpoint already serves this package."""
    if endpoint.get("EndpointStatus") != "InService":
        return False
    config_name = endpoint.get("EndpointConfigName")
    if not isinstance(config_name, str):
        return False
    try:
        config = sm.describe_endpoint_config(EndpointConfigName=config_name)
    except sm.exceptions.ClientError as error:
        if not _is_resource_not_found(error):
            raise
        return False
    variants = config.get("ProductionVariants") or []
    if not isinstance(variants, list) or len(variants) != 1:
        return False
    variant = variants[0]
    model_name = variant.get("ModelName") if isinstance(variant, dict) else None
    if not isinstance(model_name, str) or not _config_matches(config):
        return False
    try:
        model = sm.describe_model(ModelName=model_name)
    except sm.exceptions.ClientError as error:
        if not _is_resource_not_found(error):
            raise
        return False
    return _model_matches(model, package_arn)


def _deployment_result(package_arn: str, package: Mapping[str, Any], action: str) -> dict[str, Any]:
    """Log one deployment outcome and return its public result."""
    test_auc = (package.get("CustomerMetadataProperties") or {}).get("test_auc")
    event = (
        "endpoint_update_requested"
        if action in {"created", "updated"}
        else "endpoint_update_in_progress"
        if action == "in_progress"
        else "endpoint_already_current"
    )
    log_event(
        event,
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

    package = sm.describe_model_package(ModelPackageName=package_arn)
    if package.get("ModelApprovalStatus") != "Approved":
        log_event(
            "deploy_skipped",
            reason="package_not_currently_approved",
            model_package_arn=package_arn,
            status=package.get("ModelApprovalStatus"),
        )
        return {"skipped": "package not currently approved"}

    try:
        endpoint = sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
    except sm.exceptions.ClientError as error:
        if not _is_resource_not_found(error):
            raise
        endpoint = None
    if endpoint is not None and _current_deployment_matches(endpoint, package_arn):
        return _deployment_result(package_arn, package, "unchanged")

    model_name, config_name = _resource_names(package_arn)
    _ensure_resource(
        sm.describe_model,
        sm.create_model,
        {"ModelName": model_name},
        {
            "ModelName": model_name,
            "ExecutionRoleArn": EXECUTION_ROLE_ARN,
            "Containers": [{"ModelPackageName": package_arn}],
        },
        lambda description: _model_matches(description, package_arn),
        "model",
    )
    _ensure_resource(
        sm.describe_endpoint_config,
        sm.create_endpoint_config,
        {"EndpointConfigName": config_name},
        {
            "EndpointConfigName": config_name,
            "ProductionVariants": [
                {
                    "VariantName": "AllTraffic",
                    "ModelName": model_name,
                    "ServerlessConfig": {
                        "MemorySizeInMB": MEMORY_MB,
                        "MaxConcurrency": MAX_CONCURRENCY,
                    },
                }
            ],
        },
        lambda description: _config_matches(description, model_name),
        "endpoint config",
    )

    if endpoint is None:
        try:
            sm.create_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
        except sm.exceptions.ClientError as create_error:
            if not _is_resource_in_use(create_error):
                raise
            current = sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
            action = _endpoint_action(current, config_name)
            if action is None:
                raise RuntimeError(
                    f"concurrent endpoint {ENDPOINT_NAME!r} does not match approval"
                ) from create_error
        else:
            action = "created"
    else:
        action = _endpoint_action(endpoint, config_name)
        if action is None:
            try:
                sm.update_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
            except sm.exceptions.ClientError as error:
                if not _is_resource_in_use(error):
                    raise
                current = sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
                action = _endpoint_action(current, config_name)
                if action is None:
                    raise RuntimeError(
                        f"concurrent endpoint {ENDPOINT_NAME!r} does not match approval"
                    ) from error
            else:
                action = "updated"

    return _deployment_result(package_arn, package, action)
