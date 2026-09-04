"""Read the Model Registry champion for the pipeline and retrain Lambda.

This module owns the shared Model Registry champion lookup. The pipeline
definition and retrain Lambda use it. `features.py` owns the raw-value feature
contract. `schema.py` owns the Pydantic runtime contract. `drift.py` owns the
PSI statistic. `events.py` owns the log convention. None of these modules makes
an AWS Model Registry call.
"""

# The SageMaker managed image uses an older Python version.
# Deferred annotations preserve compatibility with that image.
from __future__ import annotations

import boto3

from src.common.features import BASELINE_CHAMPION_AUC, NO_CHAMPION_ARN

__all__ = ["get_champion"]


def get_champion(model_package_group: str, region: str) -> tuple[str, float]:
    """Return the latest approved package ARN and its AUC. If the group holds
    no approved package, return the 0.5 baseline."""
    sm = boto3.client("sagemaker", region_name=region)
    packages = sm.list_model_packages(
        ModelPackageGroupName=model_package_group,
        ModelApprovalStatus="Approved",
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )["ModelPackageSummaryList"]
    if not packages:
        return NO_CHAMPION_ARN, BASELINE_CHAMPION_AUC
    arn = packages[0]["ModelPackageArn"]
    description = sm.describe_model_package(ModelPackageName=arn)
    metadata = description.get("CustomerMetadataProperties", {})
    return arn, float(metadata.get("test_auc", BASELINE_CHAMPION_AUC))
