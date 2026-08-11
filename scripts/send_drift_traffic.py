"""Send distribution-shifted traffic through the drift and retraining loop.

    uv run --locked --extra dev python scripts/send_drift_traffic.py \\
        --api-url <api-url> --pipeline-execution-arn <arn> -n 200

The script signs each request with SigV4. The caller needs
`execute-api:Invoke` on the method.

The script loads background records from the held-out `api_test` fixture.
It shifts only the tenure and charge columns. Other columns keep their fixture
values.
"""

import argparse
import os
import random
import sys
from pathlib import Path
from typing import Any

# Add the repository root for direct file-path invocation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3

from scripts.evaluate_api import load_fixture, post_prediction, resolve_fixture_s3_uri
from src.common.features import FEATURE_COLUMNS
from src.common.schema import CustomerRecord

# Shift tenure and charges beyond the training distribution.
# Derive `TotalCharges` from tenure and monthly charges.
SHIFTED_COLUMNS = ("tenure", "MonthlyCharges", "TotalCharges")
TENURE_RANGE = (120, 200)
MONTHLY_CHARGES_RANGE = (300.0, 500.0)


def shift(record: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Return one record with only `SHIFTED_COLUMNS` moved off the training
    distribution."""
    shifted = {column: record[column] for column in FEATURE_COLUMNS}
    tenure = rng.randint(*TENURE_RANGE)
    monthly_charges = round(rng.uniform(*MONTHLY_CHARGES_RANGE), 2)
    shifted["tenure"] = tenure
    shifted["MonthlyCharges"] = monthly_charges
    shifted["TotalCharges"] = round(tenure * monthly_charges, 2)
    return shifted


def build_window(records: list[dict[str, Any]], count: int, seed: int = 7) -> list[dict[str, Any]]:
    """Draw `count` records with replacement and shift each record."""
    rng = random.Random(seed)
    return [shift(rng.choice(records)["record"], rng) for _ in range(count)]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture-s3-uri")
    source.add_argument("--pipeline-execution-arn")
    parser.add_argument("--api-url", default=os.getenv("API_URL"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION"))
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE"))
    parser.add_argument("-n", type=int, default=200)
    args = parser.parse_args(argv)
    if not args.api_url:
        parser.error("--api-url/API_URL is required")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)

    fixture_s3_uri = args.fixture_s3_uri or resolve_fixture_s3_uri(
        args.pipeline_execution_arn, args.region
    )
    window = build_window(load_fixture(fixture_s3_uri, args.region), args.n)

    # Validate the first generated payload before sending requests.
    # Do not use `assert`. Python `-O` removes assertions.
    CustomerRecord.model_validate(window[0])

    print(f"background records: {fixture_s3_uri}")
    print(f"shifting {', '.join(SHIFTED_COLUMNS)} across {args.n} requests")
    for index, record in enumerate(window):
        body = post_prediction(args.api_url, record, session, args.region)
        if index % 50 == 0:
            print(index, body)


if __name__ == "__main__":
    main()
