"""Demo helper. It sends distribution-shifted traffic to the API, so the drift
job reports drift and the retrain loop fires where you can see it.

    uv run --locked --extra dev python scripts/send_drift_traffic.py \\
        --api-url <api-url> --api-key <key> \\
        --pipeline-execution-arn <arn> -n 200

The background records come from the same held-out `api_test` fixture that
``evaluate_api.py`` replays, and only the tenure and charge columns are
shifted. Every other column therefore keeps the training distribution, so the
drift the job reports is the shift this script applied and nothing else.

Generating the background instead — one fixed record repeated, or values drawn
uniformly from the vocabulary — moves every other column too. The loop still
fires, but on a population that differs everywhere, which demonstrates nothing
about the intended shift.
"""

import argparse
import os
import random
import sys
from pathlib import Path
from typing import Any

# This lets the file-path invocation above import the repository package. The
# caller does not have to set PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_api import load_fixture, post_prediction, resolve_fixture_s3_uri
from src.common.features import FEATURE_COLUMNS
from src.common.schema import CustomerRecord

# The shift: a customer base with far longer tenure and far higher charges than
# anything the model trained on. `TotalCharges` follows from the other two, so
# leaving it consistent keeps the record plausible.
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
    """Draw `count` background records and shift each one.

    Sampling with replacement keeps the script usable when the fixture holds
    fewer records than the window needs.
    """
    rng = random.Random(seed)
    return [shift(rng.choice(records)["record"], rng) for _ in range(count)]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture-s3-uri")
    source.add_argument("--pipeline-execution-arn")
    parser.add_argument("--api-url", default=os.getenv("API_URL"))
    parser.add_argument("--api-key", default=os.getenv("API_KEY"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION"))
    parser.add_argument("-n", type=int, default=200)
    args = parser.parse_args(argv)
    if not args.api_url or not args.api_key:
        parser.error("--api-url/API_URL and --api-key/API_KEY are required")

    fixture_s3_uri = args.fixture_s3_uri or resolve_fixture_s3_uri(
        args.pipeline_execution_arn, args.region
    )
    window = build_window(load_fixture(fixture_s3_uri, args.region), args.n)

    # Fail loudly before sending anything. Do not use `assert`. Python -O
    # strips assertions, and this check is the only thing that keeps the
    # generated payload valid.
    CustomerRecord.model_validate(window[0])

    print(f"background records: {fixture_s3_uri}")
    print(f"shifting {', '.join(SHIFTED_COLUMNS)} across {args.n} requests")
    for index, record in enumerate(window):
        body = post_prediction(args.api_url, args.api_key, record)
        if index % 50 == 0:
            print(index, body)


if __name__ == "__main__":
    main()
