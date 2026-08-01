"""Demo helper: hit the API with distribution-shifted traffic so Model Monitor
flags drift and the retrain loop visibly fires.

    uv run --locked --extra dev python scripts/send_drift_traffic.py \\
        --url <api-url> --api-key <key> -n 200
"""

import argparse
import random
import sys
from pathlib import Path

# Allow the documented file-path invocation above to import the repository
# package without requiring PYTHONPATH first.
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

    # Fail loudly if the demo record ever drifts from the shared schema. Not an
    # `assert`: python -O strips those, and this is the only thing keeping the
    # demo payload honest.
    CustomerRecord.model_validate(BASE)
    drift = set(BASE) ^ set(FEATURE_COLUMNS)
    if drift:
        raise SystemExit(f"demo record no longer matches FEATURE_COLUMNS: {sorted(drift)}")

    rng = random.Random(7)
    for i in range(args.n):
        rec = dict(BASE)
        # Deliberately shifted vs. training distribution: extreme tenure + charges.
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
