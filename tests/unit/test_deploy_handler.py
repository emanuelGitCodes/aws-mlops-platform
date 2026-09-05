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
    if endpoint_exists:
        sm.describe_endpoint.return_value = {
            "EndpointConfigName": "test-endpoint-config-old",
            "EndpointStatus": "InService",
        }
    else:
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


@pytest.mark.parametrize(
    "container_shape",
    [
        {"Containers": []},
        {"Containers": [{"ModelPackageName": APPROVAL_EVENT["detail"]["ModelPackageArn"]}, {}]},
        {"Containers": [{}]},
        {"Containers": [{"ModelPackageName": 7}]},
    ],
)
def test_model_matcher_rejects_invalid_package_shapes(container_shape):
    description = {"ExecutionRoleArn": "arn:aws:iam::123456789012:role/test"}
    description.update(container_shape)

    assert not deploy_handler._model_matches(
        description, APPROVAL_EVENT["detail"]["ModelPackageArn"]
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


def test_duplicate_approval_reuses_resources_and_skips_endpoint_update():
    sm = _mock_sm(endpoint_exists=False)
    model_name, config_name = _names(APPROVAL_EVENT["detail"]["ModelPackageArn"])

    def describe_model(**kwargs):
        if sm.create_model.called:
            return _model_description(APPROVAL_EVENT["detail"]["ModelPackageArn"])
        raise _ClientError("ValidationException", "Could not find model")

    def describe_config(**kwargs):
        if sm.create_endpoint_config.called:
            return _config_description(model_name)
        raise _ClientError("ValidationException", "Could not find endpoint config")

    def describe_endpoint(**kwargs):
        if sm.create_endpoint.called:
            return {"EndpointConfigName": config_name, "EndpointStatus": "InService"}
        raise ENDPOINT_MISSING

    sm.describe_model.side_effect = describe_model
    sm.describe_endpoint_config.side_effect = describe_config
    sm.describe_endpoint.side_effect = describe_endpoint

    with mock.patch.object(deploy_handler, "sm", sm), mock.patch("builtins.print") as log:
        first = deploy_handler.handler(APPROVAL_EVENT, None)
        second = deploy_handler.handler(APPROVAL_EVENT, None)

    assert first["action"] == "created"
    assert second["action"] == "unchanged"
    assert sm.create_model.call_count == 1
    assert sm.create_endpoint_config.call_count == 1
    sm.update_endpoint.assert_not_called()
    assert json.loads(log.call_args.args[0])["event"] == "endpoint_already_current"
    assert sm.create_model.call_args.kwargs["ModelName"] == model_name
    assert sm.create_endpoint_config.call_args.kwargs["EndpointConfigName"] == config_name


def test_approval_event_is_skipped_when_package_is_no_longer_approved():
    sm = _mock_sm(endpoint_exists=False)
    sm.describe_model_package.return_value["ModelApprovalStatus"] = "Rejected"

    with mock.patch.object(deploy_handler, "sm", sm), mock.patch("builtins.print"):
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result == {"skipped": "package not currently approved"}
    sm.create_model.assert_not_called()
    sm.create_endpoint_config.assert_not_called()
    sm.create_endpoint.assert_not_called()


def test_package_permission_failure_happens_before_any_write():
    sm = _mock_sm(endpoint_exists=False)
    sm.describe_model_package.side_effect = _ClientError("AccessDeniedException", "denied")

    with mock.patch.object(deploy_handler, "sm", sm), pytest.raises(_ClientError):
        deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_model.assert_not_called()
    sm.create_endpoint_config.assert_not_called()
    sm.create_endpoint.assert_not_called()


def test_model_permission_failure_is_propagated_before_config_creation():
    sm = _mock_sm(endpoint_exists=False)
    sm.describe_model.side_effect = _ClientError("AccessDeniedException", "denied")

    with mock.patch.object(deploy_handler, "sm", sm), pytest.raises(_ClientError):
        deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_model.assert_not_called()
    sm.create_endpoint_config.assert_not_called()
    sm.create_endpoint.assert_not_called()


def test_model_create_failure_is_propagated():
    sm = _mock_sm(endpoint_exists=False)
    sm.create_model.side_effect = _ClientError("AccessDeniedException", "denied")

    with mock.patch.object(deploy_handler, "sm", sm), pytest.raises(_ClientError):
        deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_endpoint_config.assert_not_called()
    sm.create_endpoint.assert_not_called()


def test_concurrent_model_with_a_different_package_is_rejected():
    sm = _mock_sm(endpoint_exists=False)
    sm.describe_model.side_effect = [
        _ClientError("ValidationException", "Could not find model"),
        _model_description("arn:wrong-package"),
    ]
    sm.create_model.side_effect = _ClientError("ResourceInUseException", "already exists")

    with mock.patch.object(deploy_handler, "sm", sm):
        with pytest.raises(RuntimeError, match="model does not match approval"):
            deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_endpoint_config.assert_not_called()
    sm.create_endpoint.assert_not_called()


def test_existing_model_with_a_different_package_is_rejected():
    sm = _mock_sm(endpoint_exists=False)
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = _model_description("arn:wrong-package")

    with mock.patch.object(deploy_handler, "sm", sm):
        with pytest.raises(RuntimeError, match="model does not match approval"):
            deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_model.assert_not_called()
    sm.create_endpoint_config.assert_not_called()
    sm.create_endpoint.assert_not_called()


def test_matching_primary_container_model_is_reused():
    sm = _mock_sm(endpoint_exists=True)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, config_name = _names(package_arn)
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = {
        "ExecutionRoleArn": "arn:aws:iam::123456789012:role/test",
        "PrimaryContainer": {"ModelPackageName": package_arn},
    }
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.return_value = _config_description(model_name)
    sm.describe_endpoint.return_value = {
        "EndpointConfigName": config_name,
        "EndpointStatus": "InService",
    }

    with mock.patch.object(deploy_handler, "sm", sm):
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "unchanged"
    sm.create_model.assert_not_called()
    sm.create_endpoint_config.assert_not_called()
    sm.update_endpoint.assert_not_called()


def test_legacy_epoch_resources_are_reused_before_hashed_creation():
    sm = _mock_sm(endpoint_exists=True)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = _model_description(package_arn)
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.return_value = _config_description("test-endpoint-model-1700000000")
    sm.describe_endpoint.return_value = {
        "EndpointConfigName": "test-endpoint-config-1700000000",
        "EndpointStatus": "InService",
    }

    with mock.patch.object(deploy_handler, "sm", sm), mock.patch("builtins.print") as log:
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "unchanged"
    sm.create_model.assert_not_called()
    sm.create_endpoint_config.assert_not_called()
    sm.update_endpoint.assert_not_called()
    assert json.loads(log.call_args.args[0])["event"] == "endpoint_already_current"


def test_existing_endpoint_config_with_different_settings_is_rejected():
    sm = _mock_sm(endpoint_exists=False)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, _ = _names(package_arn)
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = _model_description(package_arn)
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.return_value = _config_description(model_name, memory_mb=4096)

    with mock.patch.object(deploy_handler, "sm", sm):
        with pytest.raises(RuntimeError, match="endpoint config does not match approval"):
            deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_model.assert_not_called()
    sm.create_endpoint_config.assert_not_called()
    sm.create_endpoint.assert_not_called()


def test_existing_endpoint_config_with_provisioned_concurrency_is_rejected():
    sm = _mock_sm(endpoint_exists=False)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, _ = _names(package_arn)
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = _model_description(package_arn)
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.return_value = _config_description(
        model_name, provisioned_concurrency=1
    )

    with mock.patch.object(deploy_handler, "sm", sm):
        with pytest.raises(RuntimeError, match="endpoint config does not match approval"):
            deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_endpoint_config.assert_not_called()
    sm.create_endpoint.assert_not_called()


def test_malformed_endpoint_config_is_rejected():
    sm = _mock_sm(endpoint_exists=False)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, _ = _names(package_arn)
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = _model_description(package_arn)
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.return_value = {"ProductionVariants": []}

    with mock.patch.object(deploy_handler, "sm", sm):
        with pytest.raises(RuntimeError, match="endpoint config does not match approval"):
            deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_endpoint_config.assert_not_called()
    sm.create_endpoint.assert_not_called()


def test_resource_in_use_rechecks_and_reuses_matching_model_and_config():
    sm = _mock_sm(endpoint_exists=False)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, config_name = _names(package_arn)
    sm.describe_model.side_effect = [
        _ClientError("ValidationException", "Could not find model"),
        _model_description(package_arn),
    ]
    sm.create_model.side_effect = _ClientError("ResourceInUseException", "already exists")
    sm.describe_endpoint_config.side_effect = [
        _ClientError("ValidationException", "Could not find endpoint config"),
        _config_description(model_name),
    ]
    sm.create_endpoint_config.side_effect = _ClientError("ResourceInUseException", "already exists")
    sm.describe_endpoint.side_effect = ENDPOINT_MISSING

    with mock.patch.object(deploy_handler, "sm", sm):
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "created"
    assert sm.create_model.call_args.kwargs["ModelName"] == model_name
    assert sm.create_endpoint_config.call_args.kwargs["EndpointConfigName"] == config_name
    sm.create_endpoint.assert_called_once()


def test_concurrent_endpoint_creation_reuses_the_matching_config():
    sm = _mock_sm(endpoint_exists=False)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, config_name = _names(package_arn)
    sm.create_endpoint.side_effect = _ClientError("ResourceInUseException", "already exists")
    sm.describe_endpoint.side_effect = [
        ENDPOINT_MISSING,
        {"EndpointConfigName": config_name, "EndpointStatus": "Creating"},
    ]

    with mock.patch.object(deploy_handler, "sm", sm), mock.patch("builtins.print") as log:
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "in_progress"
    assert sm.create_endpoint.call_args.kwargs["EndpointConfigName"] == config_name
    assert (
        model_name
        in sm.create_endpoint_config.call_args.kwargs["ProductionVariants"][0]["ModelName"]
    )
    assert json.loads(log.call_args.args[0])["event"] == "endpoint_update_in_progress"


def test_serverless_setting_change_uses_a_new_deterministic_config():
    sm = _mock_sm(endpoint_exists=True)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, config_name = _names(package_arn, memory_mb=4096)
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = _model_description(package_arn)
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.side_effect = lambda EndpointConfigName: (
        _config_description(model_name, memory_mb=2048)
        if EndpointConfigName == "test-endpoint-config-old"
        else _config_description(model_name, memory_mb=4096)
    )
    sm.describe_endpoint.return_value = {
        "EndpointConfigName": "test-endpoint-config-old",
        "EndpointStatus": "InService",
    }

    with (
        mock.patch.object(deploy_handler, "sm", sm),
        mock.patch.object(deploy_handler, "MEMORY_MB", 4096),
    ):
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "updated"
    sm.update_endpoint.assert_called_once_with(
        EndpointName="test-endpoint", EndpointConfigName=config_name
    )
    assert sm.create_model.call_count == 0
    assert sm.create_endpoint_config.call_count == 0


def test_concurrent_endpoint_update_reuses_the_matching_config():
    sm = _mock_sm(endpoint_exists=True)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, config_name = _names(package_arn)
    sm.describe_model.side_effect = None
    sm.describe_model.side_effect = lambda ModelName: _model_description(
        package_arn if ModelName == model_name else "arn:wrong-package"
    )
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.side_effect = lambda EndpointConfigName: (
        _config_description("old-model", memory_mb=2048)
        if EndpointConfigName == "test-endpoint-config-old"
        else _config_description(model_name)
    )
    sm.describe_endpoint.side_effect = [
        {"EndpointConfigName": "test-endpoint-config-old", "EndpointStatus": "InService"},
        {"EndpointConfigName": config_name, "EndpointStatus": "Updating"},
    ]
    sm.update_endpoint.side_effect = _ClientError("ResourceInUseException", "updating")

    with mock.patch.object(deploy_handler, "sm", sm), mock.patch("builtins.print") as log:
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "in_progress"
    sm.update_endpoint.assert_called_once()
    assert json.loads(log.call_args.args[0])["event"] == "endpoint_update_in_progress"


def test_same_in_flight_config_does_not_send_a_second_update():
    sm = _mock_sm(endpoint_exists=True)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, config_name = _names(package_arn)
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = _model_description(package_arn)
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.return_value = _config_description(model_name)
    sm.describe_endpoint.return_value = {
        "EndpointConfigName": "test-endpoint-config-old",
        "EndpointStatus": "Updating",
        "PendingDeploymentSummary": {"EndpointConfigName": config_name},
    }

    with mock.patch.object(deploy_handler, "sm", sm), mock.patch("builtins.print") as log:
        result = deploy_handler.handler(APPROVAL_EVENT, None)

    assert result["action"] == "in_progress"
    sm.update_endpoint.assert_not_called()
    assert json.loads(log.call_args.args[0])["event"] == "endpoint_update_in_progress"


@pytest.mark.parametrize("status", ["Failed", "RollingBack", "UpdateRollbackFailed", "Deleting"])
def test_handler_rejects_endpoint_failure_states(status):
    sm = _mock_sm(endpoint_exists=True)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, config_name = _names(package_arn)
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = _model_description(package_arn)
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.return_value = _config_description(model_name)
    sm.describe_endpoint.return_value = {
        "EndpointConfigName": config_name,
        "EndpointStatus": status,
    }

    with mock.patch.object(deploy_handler, "sm", sm):
        with pytest.raises(RuntimeError, match=status):
            deploy_handler.handler(APPROVAL_EVENT, None)

    sm.update_endpoint.assert_not_called()


def test_different_in_flight_config_fails_without_a_second_update():
    sm = _mock_sm(endpoint_exists=True)
    package_arn = APPROVAL_EVENT["detail"]["ModelPackageArn"]
    model_name, config_name = _names(package_arn)
    sm.describe_model.side_effect = None
    sm.describe_model.return_value = _model_description(package_arn)
    sm.describe_endpoint_config.side_effect = None
    sm.describe_endpoint_config.return_value = _config_description(model_name)
    sm.describe_endpoint.return_value = {
        "EndpointConfigName": "test-endpoint-config-other",
        "EndpointStatus": "SystemUpdating",
        "PendingDeploymentSummary": {"EndpointConfigName": "pending-config-other"},
    }

    with mock.patch.object(deploy_handler, "sm", sm):
        with pytest.raises(RuntimeError, match="another pending config"):
            deploy_handler.handler(APPROVAL_EVENT, None)

    sm.update_endpoint.assert_not_called()


def test_name_length_is_checked_before_model_creation():
    sm = _mock_sm(endpoint_exists=False)
    with (
        mock.patch.object(deploy_handler, "sm", sm),
        mock.patch.object(deploy_handler, "ENDPOINT_NAME", "e" * 60),
    ):
        with pytest.raises(ValueError, match="too long"):
            deploy_handler.handler(APPROVAL_EVENT, None)

    sm.create_model.assert_not_called()


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
