import hashlib
import json
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


def _names(package_arn: str, memory_mb: int = 2048, max_concurrency: int = 5) -> tuple[str, str]:
    suffix = hashlib.sha256(f"{package_arn}:{memory_mb}:{max_concurrency}".encode()).hexdigest()[
        :16
    ]
    return f"test-endpoint-model-{suffix}", f"test-endpoint-config-{suffix}"


def _model_description(package_arn: str) -> dict:
    return {
        "ExecutionRoleArn": "arn:aws:iam::123456789012:role/test",
        "Containers": [{"ModelPackageName": package_arn}],
    }


def _config_description(
    model_name: str,
    memory_mb: int = 2048,
    max_concurrency: int = 5,
    provisioned_concurrency: int | None = None,
) -> dict:
    serverless = {
        "MemorySizeInMB": memory_mb,
        "MaxConcurrency": max_concurrency,
    }
    if provisioned_concurrency is not None:
        serverless["ProvisionedConcurrency"] = provisioned_concurrency
    return {
        "ProductionVariants": [
            {
                "VariantName": "AllTraffic",
                "ModelName": model_name,
                "ServerlessConfig": serverless,
            }
        ]
    }


# What SageMaker returns for a DescribeEndpoint on a missing endpoint.
ENDPOINT_MISSING = _ClientError("ValidationException", 'Could not find endpoint "test-endpoint".')


def _mock_sm(endpoint_exists: bool, describe_error: Exception = ENDPOINT_MISSING) -> mock.Mock:
    sm = mock.Mock()
    sm.exceptions.ClientError = _ClientError
    sm.describe_model_package.return_value = {
        "ModelApprovalStatus": "Approved",
        "CustomerMetadataProperties": {"test_auc": "0.8398"},
    }
    sm.describe_model.side_effect = _ClientError("ValidationException", "Could not find model")
    sm.describe_endpoint_config.side_effect = _ClientError(
        "ValidationException", "Could not find endpoint config"
    )
    if not endpoint_exists:
        sm.describe_endpoint.side_effect = describe_error
    return sm


def test_resource_helpers_validate_names_and_existing_settings():
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, config_name = _names(package_arn)
    assert deploy_handler._resource_names(package_arn) == (model_name, config_name)
    assert deploy_handler._model_matches(_model_description(package_arn), package_arn)
    assert deploy_handler._config_matches(_config_description(model_name), model_name)
    assert not deploy_handler._config_matches(
        _config_description(model_name, provisioned_concurrency=1), model_name
    )


def test_resource_helpers_reject_malformed_config_and_long_names():
    assert not deploy_handler._config_matches({"ProductionVariants": [{}]}, "model")
    assert not deploy_handler._config_matches(
        {"ProductionVariants": [{"ServerlessConfig": []}]}, "model"
    )
    with mock.patch.object(deploy_handler, "ENDPOINT_NAME", "e" * 60):
        with pytest.raises(ValueError, match="too long"):
            deploy_handler._resource_names("arn:package")


def test_resource_helpers_require_precise_sagemaker_error_messages():
    assert deploy_handler._is_resource_not_found(
        _ClientError("ValidationException", "Could not find model")
    )
    assert not deploy_handler._is_resource_not_found(
        _ClientError("ValidationException", "model has an invalid configuration")
    )
    assert deploy_handler._is_resource_in_use(
        _ClientError("ValidationException", "model already exists")
    )
    assert not deploy_handler._is_resource_in_use(
        _ClientError("ValidationException", "model configuration is invalid")
    )


def test_resource_assurance_reuses_a_matching_resource():
    describe = mock.Mock(return_value={"matching": True})
    create = mock.Mock()

    deploy_handler._ensure_resource(
        describe,
        create,
        {"Name": "resource"},
        {"Name": "resource"},
        lambda description: description["matching"],
        "model",
    )

    describe.assert_called_once_with(Name="resource")
    create.assert_not_called()


def test_resource_assurance_rejects_mismatch_and_propagates_errors():
    with pytest.raises(RuntimeError, match="does not match approval"):
        deploy_handler._ensure_resource(
            mock.Mock(return_value={"matching": False}),
            mock.Mock(),
            {"Name": "resource"},
            {"Name": "resource"},
            lambda description: description["matching"],
            "model",
        )

    describe = mock.Mock(side_effect=_ClientError("AccessDeniedException", "denied"))
    sm = mock.Mock()
    sm.exceptions.ClientError = _ClientError
    with mock.patch.object(deploy_handler, "sm", sm):
        with pytest.raises(_ClientError):
            deploy_handler._ensure_resource(
                describe,
                mock.Mock(),
                {"Name": "resource"},
                {"Name": "resource"},
                lambda description: True,
                "model",
            )


def test_resource_assurance_rejects_a_concurrent_mismatch():
    describe = mock.Mock(
        side_effect=[
            _ClientError("ValidationException", "Could not find model"),
            {"matching": False},
        ]
    )
    create = mock.Mock(side_effect=_ClientError("ResourceInUseException", "already exists"))

    sm = mock.Mock()
    sm.exceptions.ClientError = _ClientError
    with mock.patch.object(deploy_handler, "sm", sm):
        with pytest.raises(RuntimeError, match="does not match approval"):
            deploy_handler._ensure_resource(
                describe,
                create,
                {"Name": "resource"},
                {"Name": "resource"},
                lambda description: description["matching"],
                "model",
            )


@pytest.mark.parametrize("status", ["Failed", "UpdateRollbackFailed", "Deleting"])
def test_endpoint_action_rejects_unusable_endpoint_states(status):
    with pytest.raises(RuntimeError, match=status):
        deploy_handler._endpoint_action(
            {"EndpointStatus": status, "EndpointConfigName": "test-config"},
            "test-config",
        )


def test_endpoint_action_tracks_pending_deployment_config():
    endpoint = {
        "EndpointStatus": "Updating",
        "EndpointConfigName": "old-config",
        "PendingDeploymentSummary": {"EndpointConfigName": "new-config"},
    }
    assert deploy_handler._endpoint_action(endpoint, "new-config") == "in_progress"
    with pytest.raises(RuntimeError, match="another pending config"):
        deploy_handler._endpoint_action(endpoint, "other-config")


def test_endpoint_action_rejects_unknown_or_unresolved_states():
    with pytest.raises(RuntimeError, match="Updating"):
        deploy_handler._endpoint_action(
            {"EndpointStatus": "Updating", "EndpointConfigName": "old-config"},
            "new-config",
        )
    assert (
        deploy_handler._endpoint_action(
            {"EndpointStatus": "InService", "EndpointConfigName": "test-config"},
            "test-config",
        )
        == "unchanged"
    )
    with pytest.raises(RuntimeError, match="unexpected status"):
        deploy_handler._endpoint_action(
            {"EndpointStatus": "Pending", "EndpointConfigName": "test-config"},
            "test-config",
        )


def test_non_approval_event_is_skipped():
    event = {"detail": {"ModelPackageArn": "arn", "ModelApprovalStatus": "Rejected"}}
    with mock.patch.object(deploy_handler, "sm") as sm, mock.patch("builtins.print") as log:
        result = deploy_handler.handler(event, None)
    assert "skipped" in result
    assert json.loads(log.call_args.args[0])["event"] == "deploy_skipped"
    sm.create_model.assert_not_called()


def test_first_approval_creates_endpoint():
    sm = _mock_sm(endpoint_exists=False)
    with mock.patch.object(deploy_handler, "sm", sm), mock.patch("builtins.print") as log:
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
    assert json.loads(log.call_args.args[0])["event"] == "endpoint_update_requested"


def test_subsequent_approval_updates_endpoint():
    sm = _mock_sm(endpoint_exists=True)
    with mock.patch.object(deploy_handler, "sm", sm), mock.patch("builtins.print") as log:
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "updated"
    sm.update_endpoint.assert_called_once()
    sm.create_endpoint.assert_not_called()
    assert json.loads(log.call_args.args[0])["event"] == "endpoint_update_requested"


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
