"""Update the serverless endpoint after a Model Registry approval event.

EventBridge triggers it on "SageMaker Model Package State Change" when a
package in this group becomes Approved. The handler creates a Model and an
EndpointConfig for the new package, then points the endpoint at it. On the
first deploy, it creates the endpoint.
"""

import os
import time
from typing import Any

import boto3

from src.common.events import log_event

sm = boto3.client("sagemaker")

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]
EXECUTION_ROLE_ARN = os.environ["EXECUTION_ROLE_ARN"]
MEMORY_MB = int(os.environ.get("MEMORY_MB", "2048"))
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", "5"))

# SageMaker has no modelled not-found error for DescribeEndpoint.
_NOT_FOUND_CODES = {"ValidationException", "ResourceNotFound"}


def _is_endpoint_not_found(error: Exception) -> bool:
    """Return true only when SageMaker reports a missing endpoint.

    SageMaker represents a missing endpoint as `ValidationException`.
    Match the error message with the code.
    """
    details = (getattr(error, "response", None) or {}).get("Error", {})
    return (
        details.get("Code") in _NOT_FOUND_CODES
        and "could not find" in str(details.get("Message", "")).lower()
    )


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    detail = event["detail"]
    if detail.get("ModelApprovalStatus") != "Approved":
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
        "approved_challenger_deployed",
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
