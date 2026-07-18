"""Demo helper: hit the API with distribution-shifted traffic so Model Monitor
flags drift and the retrain loop visibly fires.

    python scripts/send_drift_traffic.py --url <api-url> --api-key <key> -n 200
"""

import argparse
import random
import sys
from pathlib import Path

# Allow the documented ``python scripts/send_drift_traffic.py`` command to
# import the repository package without requiring PYTHONPATH first.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_api import post_prediction
from src.common.schema import FEATURE_COLUMNS, CustomerRecord

BASE = {
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--api-key", required=True)
    p.add_argument("-n", type=int, default=200)
    args = p.parse_args()

    # Fail loudly if the demo record ever drifts from the shared schema.
    CustomerRecord.model_validate(BASE)
    assert set(BASE) == set(FEATURE_COLUMNS)

    rng = random.Random(7)
    for i in range(args.n):
        rec = dict(BASE)
        # Deliberately shifted vs. training distribution: extreme tenure + charges.
        rec["tenure"] = rng.randint(120, 200)
        rec["MonthlyCharges"] = round(rng.uniform(300, 500), 2)
        rec["TotalCharges"] = round(rec["tenure"] * rec["MonthlyCharges"], 2)
        body = post_prediction(args.url, args.api_key, rec)
        if i % 50 == 0:
            print(i, body)


if __name__ == "__main__":
    main()
