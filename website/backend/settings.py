"""Read the website backend configuration from the environment.

The values live here, and not beside the code that reads them, because the
deployed instance and `local/compose.yaml` set the same names. One module
states that contract.

The two AWS endpoint variables are absent by name. botocore reads
`AWS_ENDPOINT_URL_S3` and `AWS_ENDPOINT_URL_DYNAMODB` on its own, so local
development points at MinIO and DynamoDB Local without a branch in this code.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """One environment's backend configuration."""

    table_name: str
    artifacts_bucket: str
    evaluation_prefix: str
    predict_url: str
    rate_limit_per_minute: int
    port: int
    # Serve a cached evaluation report for this many seconds.
    results_cache_seconds: int
    # Refuse a request body above this size.
    max_body_bytes: int


def load_settings() -> Settings:
    """Build the settings from the process environment."""
    return Settings(
        table_name=os.environ.get("TABLE_NAME", ""),
        artifacts_bucket=os.environ.get("ARTIFACTS_BUCKET", ""),
        evaluation_prefix=os.environ.get("EVALUATION_PREFIX", "evaluations"),
        predict_url=os.environ.get("PREDICT_URL", ""),
        rate_limit_per_minute=int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10")),
        port=int(os.environ.get("PORT", "8080")),
        results_cache_seconds=int(os.environ.get("RESULTS_CACHE_SECONDS", "300")),
        max_body_bytes=int(os.environ.get("MAX_BODY_BYTES", "16384")),
    )
