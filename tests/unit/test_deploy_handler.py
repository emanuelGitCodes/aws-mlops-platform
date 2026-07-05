import os
from unittest import mock

os.environ.setdefault("ENDPOINT_NAME", "test-endpoint")
os.environ.setdefault("EXECUTION_ROLE_ARN", "arn:aws:iam::123456789012:role/test")
os.environ.setdefault("CAPTURE_BUCKET", "test-artifacts")

with mock.patch("boto3.client"):
    from src.serving import deploy_handler

APPROVAL_EVENT = {
    "detail": {
        "ModelPackageArn": "arn:aws:sagemaker:us-east-1:123456789012:model-package/churn/3",
        "ModelApprovalStatus": "Approved",
    }
}


class _ClientError(Exception):
    pass


def _mock_sm(endpoint_exists: bool) -> mock.Mock:
    sm = mock.Mock()
    sm.exceptions.ClientError = _ClientError
    if not endpoint_exists:
        sm.describe_endpoint.side_effect = _ClientError("not found")
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
    assert config_call["DataCaptureConfig"]["EnableCapture"] is True


def test_subsequent_approval_updates_endpoint():
    sm = _mock_sm(endpoint_exists=True)
    with mock.patch.object(deploy_handler, "sm", sm):
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "updated"
    sm.update_endpoint.assert_called_once()
    sm.create_endpoint.assert_not_called()
