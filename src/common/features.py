"""Dependency-free feature contract shared by training and serving.

Keep the ordered model columns separate from the Pydantic validation model so
SageMaker preprocessing can import the training contract in the stock sklearn
image, which does not include Pydantic.
"""

# Order matters: this is the feature order used for both training and inference.
FEATURE_COLUMNS = [
    "gender",
    "SeniorCitizen",
    "Partner",
    "Dependents",
    "tenure",
    "PhoneService",
    "MultipleLines",
    "InternetService",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
    "Contract",
    "PaperlessBilling",
    "PaymentMethod",
    "MonthlyCharges",
    "TotalCharges",
]
LABEL_COLUMN = "Churn"

# Decision rule shared by serving and evaluation: churn iff score >= threshold.
DEFAULT_THRESHOLD = 0.5
