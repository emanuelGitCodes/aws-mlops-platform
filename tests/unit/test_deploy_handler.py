from unittest import mock

import pytest

from tests.unit.conftest import ClientError as _ClientError
from tests.unit.conftest import import_with_stubbed_boto3

deploy_handler = import_with_stubbed_boto3("src.serving.deploy_handler")

APPROVAL_EVENT = {
    "detail": {
        "ModelPackageArn": "arn:aws:sagemaker:us-east-1:123456789012:model-package/churn/3",
        "ModelApprovalStatus": "Approved",
    }
}


# What SageMaker returns for a DescribeEndpoint on a missing endpoint.
ENDPOINT_MISSING = _ClientError("ValidationException", 'Could not find endpoint "test-endpoint".')


def _mock_sm(endpoint_exists: bool, describe_error: Exception = ENDPOINT_MISSING) -> mock.Mock:
    sm = mock.Mock()
    sm.exceptions.ClientError = _ClientError
    sm.describe_model_package.return_value = {"CustomerMetadataProperties": {"test_auc": "0.8398"}}
    if not endpoint_exists:
        sm.describe_endpoint.side_effect = describe_error
    return sm


def test_non_approval_event_is_skipped():
    event = {"detail": {"ModelPackageArn": "arn", "ModelApprovalStatus": "Rejected"}}
    with mock.patch.object(deploy_handler, "sm") as sm:
        result = deploy_handler.handler(event, None)
    assert "skipped" in result
    sm.create_model.assert_not_called()


def test_first_approval_creates_endpoint():
    sm = _mock_sm(endpoint_exists=False)
    with mock.patch.object(deploy_handler, "sm", sm):
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "created"
    sm.create_endpoint.assert_called_once()
    sm.update_endpoint.assert_not_called()

    model_call = sm.create_model.call_args.kwargs
    assert model_call["Containers"][0]["ModelPackageName"].endswith("churn/3")

    config_call = sm.create_endpoint_config.call_args.kwargs
    variant = config_call["ProductionVariants"][0]
    assert "ServerlessConfig" in variant
    assert "DataCaptureConfig" not in config_call
    assert result["test_auc"] == "0.8398"


def test_subsequent_approval_updates_endpoint():
    sm = _mock_sm(endpoint_exists=True)
    with mock.patch.object(deploy_handler, "sm", sm):
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "updated"
    sm.update_endpoint.assert_called_once()
    sm.create_endpoint.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        _ClientError("AccessDeniedException", "not authorized: sagemaker:DescribeEndpoint"),
        _ClientError("ThrottlingException", "Rate exceeded"),
        _ClientError("ValidationException", "1 validation error detected"),
    ],
)
def test_describe_failure_is_not_mistaken_for_a_missing_endpoint(error):
    """Create an endpoint only for the missing-endpoint error."""
    sm = _mock_sm(endpoint_exists=False, describe_error=error)
    with mock.patch.object(deploy_handler, "sm", sm), pytest.raises(_ClientError):
        deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_endpoint.assert_not_called()
    sm.update_endpoint.assert_not_called()


def test_update_failure_does_not_fall_through_to_create():
    """Do not create an endpoint after an update failure."""
    sm = _mock_sm(endpoint_exists=True)
    sm.update_endpoint.side_effect = _ClientError("ValidationException", "Could not find endpoint")
    with mock.patch.object(deploy_handler, "sm", sm), pytest.raises(_ClientError):
        deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_endpoint.assert_not_called()
