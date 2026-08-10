"""Evaluate the deployed API with raw labeled records from a pipeline
execution.

Examples:
    API_URL=https://.../predict \\
      uv run --locked --extra dev python scripts/evaluate_api.py \\
      --pipeline-execution-arn <arn>

    API_URL=https://.../predict \\
      uv run --locked --extra dev python scripts/evaluate_api.py \\
      --fixture-s3-uri s3://bucket/path/api_test/ --all --profile <profile>

The caller signs each request with SigV4 and needs `execute-api:Invoke` on the
method. Credentials come from the named profile, or from the default chain.
"""

import argparse
import json
import math
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Add the repository root for direct file-path invocation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.features import DEFAULT_THRESHOLD
from src.pipeline.evaluate import calculate_classification_metrics


class ApiEvaluationError(RuntimeError):
    """Raised when a deployed endpoint breaks the prediction contract."""


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Return bucket and prefix for a non-empty S3 URI."""
    if not uri.startswith("s3://"):
        raise ValueError("fixture S3 URI must start with s3://")
    bucket_and_key = uri[5:].split("/", 1)
    if not bucket_and_key[0] or len(bucket_and_key) != 2 or not bucket_and_key[1]:
        raise ValueError("fixture S3 URI must include a bucket and object prefix")
    return bucket_and_key[0], bucket_and_key[1].rstrip("/")


def resolve_fixture_s3_uri(pipeline_execution_arn: str, region: str | None = None) -> str:
    """Find the api_test ProcessingOutput that one pipeline execution wrote."""
    client = boto3.client("sagemaker", region_name=region)
    paginator = client.get_paginator("list_pipeline_execution_steps")
    for page in paginator.paginate(PipelineExecutionArn=pipeline_execution_arn):
        for step in page["PipelineExecutionSteps"]:
            if step["StepName"] != "Preprocess":
                continue
            processing_arn = step["Metadata"]["ProcessingJob"]["Arn"]
            processing_job = client.describe_processing_job(
                ProcessingJobName=processing_arn.rsplit("/", 1)[-1]
            )
            for output in processing_job["ProcessingOutputConfig"]["Outputs"]:
                if output["OutputName"] == "api_test":
                    return output["S3Output"]["S3Uri"]
    raise ApiEvaluationError("pipeline execution does not have an api_test preprocessing output")


def load_fixture(s3_uri: str, region: str | None = None) -> list[dict[str, Any]]:
    """Load the JSON Lines test fixture from S3."""
    bucket, prefix = parse_s3_uri(s3_uri)
    key = prefix if prefix.endswith(".jsonl") else f"{prefix}/api_test.jsonl"
    body = boto3.client("s3", region_name=region).get_object(Bucket=bucket, Key=key)["Body"]
    records = [json.loads(line) for line in body.read().decode().splitlines() if line]
    if not records:
        raise ApiEvaluationError("API evaluation fixture is empty")
    return records


def select_records(
    records: list[dict[str, Any]], limit: int, all_records: bool
) -> list[dict[str, Any]]:
    """Select a repeatable, class-balanced subset. If the caller asks for all
    records, return them all."""
    if all_records or limit >= len(records):
        return records
    if limit < 2:
        raise ValueError("limit must be at least 2 so both classes can be evaluated")

    by_label: dict[int, list[dict[str, Any]]] = {0: [], 1: []}
    for record in records:
        by_label[record["label"]].append(record)
    if not by_label[0] or not by_label[1] or limit == 1:
        return sorted(random.Random(42).sample(records, limit), key=lambda item: item["row_id"])

    positive_count = max(1, round(limit * len(by_label[1]) / len(records)))
    positive_count = min(positive_count, len(by_label[1]), limit - 1)
    negative_count = limit - positive_count
    negative_count = min(negative_count, len(by_label[0]))
    positive_count = min(limit - negative_count, len(by_label[1]))
    rng = random.Random(42)
    selected = rng.sample(by_label[0], negative_count) + rng.sample(by_label[1], positive_count)
    return sorted(selected, key=lambda item: item["row_id"])


def sign_headers(
    api_url: str, body: bytes, session: boto3.Session, region: str | None = None
) -> dict[str, str]:
    """Return the SigV4 headers for one POST to the API.

    The signature covers the body. A caller must sign the exact bytes it
    sends. The service name for API Gateway is `execute-api`.
    """
    credentials = session.get_credentials()
    if credentials is None:
        raise ApiEvaluationError("no AWS credentials found for signing")
    signing_region = region or session.region_name
    if not signing_region:
        raise ApiEvaluationError("no AWS region found for signing")
    request = AWSRequest(
        method="POST",
        url=api_url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(credentials, "execute-api", signing_region).add_auth(request)
    return dict(request.headers)


def post_prediction(
    api_url: str,
    record: dict[str, Any],
    session: boto3.Session,
    region: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST one record to /predict and return the parsed JSON response."""
    body = json.dumps(record).encode()
    request = urllib.request.Request(
        api_url,
        data=body,
        headers=sign_headers(api_url, body, session, region),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload: dict[str, Any] = json.loads(response.read())
    return payload


def invoke_prediction(
    api_url: str,
    record: dict[str, Any],
    session: boto3.Session,
    region: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Call /predict. Validate the probability and the thresholded class."""
    try:
        payload = post_prediction(api_url, record, session, region, timeout=timeout)
    except urllib.error.HTTPError as error:
        raise ApiEvaluationError(f"API returned HTTP {error.code}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ApiEvaluationError(f"API request failed: {error}") from error

    score = payload.get("churn_probability")
    prediction = payload.get("churn")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ApiEvaluationError("API churn_probability must be a finite number")
    if not 0.0 <= score <= 1.0:
        raise ApiEvaluationError("API churn_probability must be between 0 and 1")
    if not isinstance(prediction, bool):
        raise ApiEvaluationError("API churn must be a boolean")
    if prediction != (score >= DEFAULT_THRESHOLD):
        raise ApiEvaluationError(
            f"API churn does not match churn_probability >= {DEFAULT_THRESHOLD:.2f}"
        )
    return {"score": float(score), "prediction": int(prediction)}


def evaluate_api_records(
    records: list[dict[str, Any]],
    api_url: str,
    session: boto3.Session,
    region: str | None = None,
    limit: int = 25,
    all_records: bool = False,
) -> dict[str, Any]:
    """Call the deployed API. Return quality metrics for the selected
    records."""
    selected = select_records(records, limit=limit, all_records=all_records)
    labels, scores = [], []
    for fixture in selected:
        result = invoke_prediction(api_url, fixture["record"], session, region)
        labels.append(int(fixture["label"]))
        scores.append(result["score"])
    return {
        "source": "deployed_api",
        "fixture_record_count": len(records),
        "evaluated_record_count": len(selected),
        "all_records": all_records,
        **calculate_classification_metrics(labels, scores),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture-s3-uri")
    source.add_argument("--pipeline-execution-arn")
    parser.add_argument("--api-url", default=os.getenv("API_URL"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION"))
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE"))
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--all", action="store_true", dest="all_records")
    parser.add_argument("--output", help="optional local JSON report path")
    args = parser.parse_args(argv)
    if not args.api_url:
        parser.error("--api-url/API_URL is required")

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    fixture_s3_uri = args.fixture_s3_uri or resolve_fixture_s3_uri(
        args.pipeline_execution_arn, args.region
    )
    report = evaluate_api_records(
        load_fixture(fixture_s3_uri, args.region),
        api_url=args.api_url,
        session=session,
        region=args.region,
        limit=args.limit,
        all_records=args.all_records,
    )
    report["fixture_s3_uri"] = fixture_s3_uri
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        with open(args.output, "w") as f:
            f.write(f"{rendered}\n")


if __name__ == "__main__":
    main()
