"""Cross-stack CDK helpers and the environment config contract.

This module exists because these patterns repeat across several stacks.
``lambda_code.py`` covers only the bundled Lambda asset.

The ``*Config`` TypedDicts define the shape of
``infra/config/{dev,prod}.yaml``. They are build-time only. Keep them
separate from ``src/common/schema.py``, which is the runtime contract.
"""

from typing import Any, TypedDict

from aws_cdk import RemovalPolicy
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from infra.stacks.lambda_code import src_code


class ServerlessConfig(TypedDict):
    """``serverless:`` — SageMaker serverless endpoint sizing."""

    memory_mb: int
    max_concurrency: int


class MonitorConfig(TypedDict):
    """``monitor:`` — the drift job schedule and the endpoint alarms."""

    schedule_cron: str
    silence_alarm_hours: int


class SecurityServicesConfig(TypedDict):
    """``security.services:`` — the six security-service enablement flags.

    ``SecurityMonitoringStack`` requires exactly these keys. Keep them in sync
    with ``PHASE_3_SERVICE_FLAGS``.
    """

    access_analyzer: bool
    guardduty: bool
    config_recorder: bool
    security_hub: bool
    account_bpa: bool
    eventbridge_alerts: bool


class SecurityConfig(TypedDict):
    """``security:`` — audit retention, budget alarms, and service flags."""

    audit_log_retention_days: int
    budget_thresholds: list[int]
    # AWS Budgets is account-scoped, and dev and prod share one account. Only
    # one environment may own the budget. A second one measures the same
    # dollars and alarms twice.
    account_budget: bool
    services: SecurityServicesConfig


class PlatformConfig(TypedDict):
    """One environment's complete config, as loaded from YAML."""

    env_name: str
    model_package_group: str
    model_approval_status: str
    endpoint_name: str
    pipeline_name: str
    serverless: ServerlessConfig
    monitor: MonitorConfig
    budget_usd: int
    log_retention_days: int
    # Days a captured prediction survives. The drift job reads one hour, so
    # anything older only serves an investigation of a past violation.
    capture_retention_days: int
    security: SecurityConfig


# S3 prefixes shared between a writer and an IAM grant. A rename in one place
# only fails at runtime, never at synth, so each is pinned to its writer in
# `tests/unit/test_pipeline.py`. `src/pipeline/` runs in the SageMaker image,
# where `infra` is not installed, so it cannot import these.
#
# - `config`: SecurityMonitoring sets it on the delivery channel. Security
#   scopes the audit-bucket policy to it.
# - `training`: the training step writes `model.tar.gz` here. It is the only
#   prefix the model container reads.
# - `evaluations` and `monitor`: written by the evaluation and preprocessing
#   steps. The pipeline role is scoped to both.
# - `capture`: the proxy Lambda writes one object per served prediction. The
#   drift Lambda reads them.
CONFIG_DELIVERY_PREFIX = "config"
MODEL_ARTIFACT_PREFIX = "training"
EVALUATION_REPORT_PREFIX = "evaluations"
MONITOR_OUTPUT_PREFIX = "monitor"
CAPTURE_PREFIX = "capture"

# The one key the drift Lambda reads. The preprocessing step writes it through
# the pipeline's `BASELINE_DESTINATION_PREFIX`, which repeats the same path.
BASELINE_KEY = f"{MONITOR_OUTPUT_PREFIX}/baseline/baseline.json"


_LOG_RETENTION = {
    7: logs.RetentionDays.ONE_WEEK,
    14: logs.RetentionDays.TWO_WEEKS,
    30: logs.RetentionDays.ONE_MONTH,
    90: logs.RetentionDays.THREE_MONTHS,
}


def log_retention(config: PlatformConfig) -> logs.RetentionDays:
    """Map the environment's ``log_retention_days`` to a RetentionDays value."""
    days = config["log_retention_days"]
    if days not in _LOG_RETENTION:
        raise ValueError(f"unsupported log_retention_days: {days}")
    return _LOG_RETENTION[days]


def platform_lambda(
    scope: Construct,
    construct_id: str,
    *,
    config: PlatformConfig,
    code: lambda_.Code | None = None,
    least_privilege_logs: bool = False,
    **kwargs: Any,
) -> lambda_.Function:
    """Lambda with platform defaults: Python 3.12, its own log group at the
    config retention, and the shared src/ asset unless other code is supplied.

    The log group is explicit. CDK deprecated `log_retention=`, and that prop
    builds a provider Lambda per stack whose `Resource: *` log policy needs six
    cdk-nag acknowledgements.

    The group name is CDK-generated, not `/aws/lambda/<function>`. The function
    name is generated too, so naming the group after it would be circular.
    Lambda still writes to it, because the managed log policy grants the log
    actions on `*`. Use `DESTROY`, because a retained group with a generated
    name would be orphaned by the next deploy.
    """
    log_group = logs.LogGroup(
        scope,
        f"{construct_id}Logs",
        retention=log_retention(config),
        removal_policy=RemovalPolicy.DESTROY,
    )
    role: iam.IRole | None = None
    if least_privilege_logs:
        # `AWSLambdaBasicExecutionRole` grants the log actions on every log
        # group in the account. Supplying a role stops CDK from attaching that
        # policy, so the function writes only to the group created above. This
        # is opt-in, because roles are converted one per change set.
        role = iam.Role(
            scope,
            f"{construct_id}Role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description=f"{construct_id} execution role; writes only to its own log group",
        )
        log_group.grant_write(role)
    return lambda_.Function(
        scope,
        construct_id,
        runtime=lambda_.Runtime.PYTHON_3_12,
        code=code if code is not None else src_code(),
        log_group=log_group,
        role=role,
        **kwargs,
    )


def sagemaker_execution_role(
    scope: Construct, construct_id: str, *, least_privilege: bool = False
) -> iam.Role:
    """Execution role SageMaker assumes.

    The role carries `AmazonSageMakerFullAccess` unless `least_privilege` is
    set. With that flag it carries no managed policy, and the caller grants
    every permission explicitly.

    Never pass `role_name`, and never rename the construct. Both roles this
    function builds are pinned by ARN outside CloudFormation, so each must be
    updated in place. A replaced model role strands the endpoint at its next
    cold start. A replaced pipeline role strands the deployed pipeline
    definition, which pins that ARN.
    """
    return iam.Role(
        scope,
        construct_id,
        assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
        managed_policies=(
            None
            if least_privilege
            else [iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSageMakerFullAccess")]
        ),
    )


def lambda_event_rule(
    scope: Construct,
    construct_id: str,
    *,
    detail_type: str,
    detail: dict[str, Any],
    handler: lambda_.IFunction,
    source: str = "aws.sagemaker",
) -> events.Rule:
    """EventBridge rule on one event source that invokes a Lambda.

    The default source covers the registry and endpoint events. The drift loop
    passes its own source, because the platform emits that event itself.
    """
    return events.Rule(
        scope,
        construct_id,
        event_pattern=events.EventPattern(
            source=[source],
            detail_type=[detail_type],
            detail=detail,
        ),
        targets=[targets.LambdaFunction(handler)],
    )
