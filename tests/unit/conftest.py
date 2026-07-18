"""Shared unit-test setup: handler env stubs, boto3-stubbed imports, the
canonical valid sample record, and the repo root path."""

import importlib
import os
import pathlib
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Handler modules read these at import time; set them before any test imports.
os.environ.setdefault("ENDPOINT_NAME", "test-endpoint")
os.environ.setdefault("EXECUTION_ROLE_ARN", "arn:aws:iam::123456789012:role/test")
os.environ.setdefault("CURATED_BUCKET", "test-curated")

# One valid CustomerRecord payload, shared by every test module that needs it.
VALID = {
    "gender": "Female",
    "SeniorCitizen": 0,
    "Partner": "Yes",
    "Dependents": "No",
    "tenure": 12,
    "PhoneService": "Yes",
    "MultipleLines": "No",
    "InternetService": "DSL",
    "OnlineSecurity": "No",
    "OnlineBackup": "Yes",
    "DeviceProtection": "No",
    "TechSupport": "No",
    "StreamingTV": "No",
    "StreamingMovies": "No",
    "Contract": "Month-to-month",
    "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check",
    "MonthlyCharges": 53.85,
    "TotalCharges": 646.2,
}


def import_with_stubbed_boto3(module_name: str):
    """Import a handler module with its module-level boto3 clients mocked."""
    with mock.patch("boto3.client"):
        return importlib.import_module(module_name)
