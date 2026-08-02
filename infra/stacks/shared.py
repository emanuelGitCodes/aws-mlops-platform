"""Cross-stack CDK helpers and the environment config contract.

New module because these patterns repeat across several stacks and
``lambda_code.py`` is specific to the bundled Lambda asset; no other
stack-shared module exists.

The ``*Config`` TypedDicts below are the single source of truth for the
shape of ``infra/config/{dev,prod}.yaml``. They are build-time only and
deliberately separate from ``src/common/schema.py``, which is the runtime
data contract shipped into Lambda.
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
    """``monitor:`` — Model Monitor scheduling."""

    schedule_cron: str


class SecurityServicesConfig(TypedDict):
    """``security.services:`` — the six Phase 3 enablement flags.

    ``SecurityMonitoringStack`` requires exactly these keys; keep in sync
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
    # AWS Budgets is account-scoped, and these stacks are environment-agnostic
    # (no `env=cdk.Environment`), so dev and prod share one account. Exactly one
    # environment may own the account budget; a second one re-measures the same
    # dollars and alarms twice on them. Gated like the account-level Block
    # Public Access flag, and for the same reason.
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
    security: SecurityConfig


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
    **kwargs: Any,
) -> lambda_.Function:
    """Lambda with platform defaults: Python 3.12, an own log group at the
    config's retention, and the shared src/ asset unless other code is supplied.

    The group is explicit rather than `log_retention=`, which CDK deprecated and
    removes in the next major. That prop also built a singleton provider Lambda
    and role per stack whose `Resource: *` log policy carried six of the cdk-nag
    acknowledgements; an owned `LogGroup` deletes all of it.

    The name is CDK-generated, not `/aws/lambda/<function>`: the function name is
    generated too, so naming the group after it is circular. Lambda still writes
    to it because `AWSLambdaBasicExecutionRole` grants the log actions on `*`,
    not on an `/aws/lambda/` prefix. `DESTROY` because these are application
    logs, not the retained audit evidence in the Security stack -- and with a
    generated name a retained group would be orphaned by the next deploy rather
    than reused.
    """
    return lambda_.Function(
        scope,
        construct_id,
        runtime=lambda_.Runtime.PYTHON_3_12,
        code=code if code is not None else src_code(),
        log_group=logs.LogGroup(
            scope,
            f"{construct_id}Logs",
            retention=log_retention(config),
            removal_policy=RemovalPolicy.DESTROY,
        ),
        **kwargs,
    )


def sagemaker_execution_role(scope: Construct, construct_id: str) -> iam.Role:
    """Execution role SageMaker assumes (broad managed policy; acknowledged in
    security_checks.py)."""
    return iam.Role(
        scope,
        construct_id,
        assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
        managed_policies=[
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSageMakerFullAccess")
        ],
    )


def sagemaker_event_rule(
    scope: Construct,
    construct_id: str,
    *,
    detail_type: str,
    detail: dict[str, Any],
    handler: lambda_.IFunction,
) -> events.Rule:
    """EventBridge rule on an aws.sagemaker event that invokes a Lambda."""
    return events.Rule(
        scope,
        construct_id,
        event_pattern=events.EventPattern(
            source=["aws.sagemaker"],
            detail_type=[detail_type],
            detail=detail,
        ),
        targets=[targets.LambdaFunction(handler)],
    )
