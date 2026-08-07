"""Deploy Lambda: a Model Registry approval event updates the serverless
endpoint.

EventBridge triggers it on "SageMaker Model Package State Change" when a
package in this group becomes Approved. The handler creates a Model and an
EndpointConfig for the new package, then points the endpoint at it. On the
first deploy it creates the endpoint instead.
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
    """Return True only for "this endpoint does not exist yet".

    SageMaker reports a missing endpoint as a ValidationException, not as a
    modelled not-found error, so this function must read the message too. If
    AWS rewords the message, the caller re-raises. A loud failure on a first
    deploy is safer than a create for the wrong reason.
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
    # SageMaker Serverless Inference does not support DataCaptureConfig. A
    # serverless endpoint has no idle hosting cost, so it stays serverless.
    # Model Monitor capture needs a different serving design later.
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

    # Only a missing endpoint may fall through to create. Catching every
    # ClientError turned an AccessDenied or a throttle into a create_endpoint,
    # which then failed with an error describing the wrong problem. Keep
    # `update_endpoint` outside the try for the same reason.
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
