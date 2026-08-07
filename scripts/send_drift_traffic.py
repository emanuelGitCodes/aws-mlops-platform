"""Demo helper. It sends distribution-shifted traffic to the API, so Model
Monitor reports drift and the retrain loop fires where you can see it.

    uv run --locked --extra dev python scripts/send_drift_traffic.py \\
        --url <api-url> --api-key <key> -n 200
"""

import argparse
import random
import sys
from pathlib import Path

# This lets the file-path invocation above import the repository package. The
# caller does not have to set PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_api import post_prediction
from src.common.schema import FEATURE_COLUMNS, CustomerRecord

BASE: dict[str, object] = {
    "gender": "Female",
    "SeniorCitizen": 0,
    "Partner": "Yes",
    "Dependents": "No",
    "tenure": 12,
    "PhoneService": "Yes",
    "MultipleLines": "No",
    "InternetService": "Fiber optic",
    "OnlineSecurity": "No",
    "OnlineBackup": "No",
    "DeviceProtection": "No",
    "TechSupport": "No",
    "StreamingTV": "Yes",
    "StreamingMovies": "Yes",
    "Contract": "Month-to-month",
    "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check",
    "MonthlyCharges": 70.0,
    "TotalCharges": 840.0,
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--api-key", required=True)
    p.add_argument("-n", type=int, default=200)
    args = p.parse_args()

    # Fail loudly if the demo record no longer matches the shared schema. Do
    # not use `assert`. Python -O strips assertions, and this check is the only
    # thing that keeps the demo payload correct.
    CustomerRecord.model_validate(BASE)
    drift = set(BASE) ^ set(FEATURE_COLUMNS)
    if drift:
        raise SystemExit(f"demo record no longer matches FEATURE_COLUMNS: {sorted(drift)}")

    rng = random.Random(7)
    for i in range(args.n):
        rec = dict(BASE)
        # Shifted away from the training distribution: extreme tenure and
        # extreme charges.
        tenure = rng.randint(120, 200)
        monthly_charges = round(rng.uniform(300, 500), 2)
        rec["tenure"] = tenure
        rec["MonthlyCharges"] = monthly_charges
        rec["TotalCharges"] = round(tenure * monthly_charges, 2)
        body = post_prediction(args.url, args.api_key, rec)
        if i % 50 == 0:
            print(i, body)


if __name__ == "__main__":
    main()
