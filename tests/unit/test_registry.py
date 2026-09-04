from unittest import mock

from src.common import registry
from src.common.features import BASELINE_CHAMPION_AUC, NO_CHAMPION_ARN
from tests.unit.conftest import (
    TEST_AWS_REGION,
    TEST_MODEL_PACKAGE_ARN_PREFIX,
    TEST_MODEL_PACKAGE_GROUP,
)

CHAMPION_ARN = f"{TEST_MODEL_PACKAGE_ARN_PREFIX}/7"


def test_get_champion_returns_the_latest_approved_package():
    sm = mock.Mock()
    sm.list_model_packages.return_value = {
        "ModelPackageSummaryList": [{"ModelPackageArn": CHAMPION_ARN}]
    }
    metadata = {"test_auc": "0.8398"}
    sm.describe_model_package.return_value = {"CustomerMetadataProperties": metadata}

    with mock.patch.object(registry.boto3, "client", return_value=sm):
        result = registry.get_champion(TEST_MODEL_PACKAGE_GROUP, TEST_AWS_REGION)

    assert result == (CHAMPION_ARN, 0.8398)
    sm.list_model_packages.assert_called_once_with(
        ModelPackageGroupName=TEST_MODEL_PACKAGE_GROUP,
        ModelApprovalStatus="Approved",
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )
    sm.describe_model_package.assert_called_once_with(ModelPackageName=CHAMPION_ARN)


def test_get_champion_returns_the_baseline_for_an_empty_group():
    sm = mock.Mock()
    sm.list_model_packages.return_value = {"ModelPackageSummaryList": []}

    with mock.patch.object(registry.boto3, "client", return_value=sm):
        result = registry.get_champion(TEST_MODEL_PACKAGE_GROUP, TEST_AWS_REGION)

    assert result == (NO_CHAMPION_ARN, BASELINE_CHAMPION_AUC)
    sm.describe_model_package.assert_not_called()


def test_get_champion_returns_the_baseline_when_test_auc_is_missing():
    sm = mock.Mock()
    sm.list_model_packages.return_value = {
        "ModelPackageSummaryList": [{"ModelPackageArn": CHAMPION_ARN}]
    }
    sm.describe_model_package.return_value = {"CustomerMetadataProperties": {}}

    with mock.patch.object(registry.boto3, "client", return_value=sm):
        result = registry.get_champion(TEST_MODEL_PACKAGE_GROUP, TEST_AWS_REGION)

    assert result == (CHAMPION_ARN, BASELINE_CHAMPION_AUC)
