from unittest import mock

import pytest

from src.common import registry
from src.common.features import BASELINE_CHAMPION_AUC, NO_CHAMPION_ARN
from tests.unit.conftest import (
    TEST_AWS_REGION,
    TEST_MODEL_PACKAGE_ARN_PREFIX,
    TEST_MODEL_PACKAGE_GROUP,
)

CHAMPION_ARN = f"{TEST_MODEL_PACKAGE_ARN_PREFIX}/7"


@pytest.mark.parametrize(
    "model",
    [
        {"Containers": [{"ModelPackageName": CHAMPION_ARN}]},
        {"PrimaryContainer": {"ModelPackageName": CHAMPION_ARN}},
    ],
)
def test_extract_model_package_name_supports_one_container_contract(model):
    assert registry.extract_model_package_name(model) == CHAMPION_ARN


@pytest.mark.parametrize(
    "model",
    [
        {"Containers": []},
        {"Containers": [{"ModelPackageName": CHAMPION_ARN}, {}]},
        {"Containers": [{}]},
        {"Containers": [{"ModelPackageName": 7}]},
        {"Containers": "invalid"},
        {"PrimaryContainer": {}},
    ],
)
def test_extract_model_package_name_rejects_invalid_container_shapes(model):
    with pytest.raises(ValueError, match="model"):
        registry.extract_model_package_name(model)


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
