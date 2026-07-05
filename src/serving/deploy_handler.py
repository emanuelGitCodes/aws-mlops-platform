"""Deploy Lambda: Model Registry approval event -> update the serverless endpoint.

Triggered by EventBridge on "SageMaker Model Package State Change" when a
package in our group flips to Approved. Creates a Model + EndpointConfig for
the new package and points the endpoint at it (create if first deploy).
"""

import os
import time

import boto3

sm = boto3.client("sagemaker")

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]
EXECUTION_ROLE_ARN = os.environ["EXECUTION_ROLE_ARN"]
MEMORY_MB = int(os.environ.get("MEMORY_MB", "2048"))
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", "5"))
CAPTURE_BUCKET = os.environ["CAPTURE_BUCKET"]


def handler(event, context):
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
        DataCaptureConfig={
            "EnableCapture": True,
            "InitialSamplingPercentage": 100,
            "DestinationS3Uri": f"s3://{CAPTURE_BUCKET}/data-capture",
            "CaptureOptions": [{"CaptureMode": "Input"}, {"CaptureMode": "Output"}],
            "CaptureContentTypeHeader": {"CsvContentTypes": ["text/csv"]},
        },
    )

    try:
        sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
        sm.update_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
        action = "updated"
    except sm.exceptions.ClientError:
        sm.create_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
        action = "created"

    print(f"{action} endpoint {ENDPOINT_NAME} -> {package_arn}")
    return {"endpoint": ENDPOINT_NAME, "action": action, "package": package_arn}
