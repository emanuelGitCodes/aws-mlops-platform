"""Define cross-stack CDK helpers and the environment config contract.

The ``*Config`` types define ``infra/config/{dev,prod}.yaml`` at build time.
``src/common/schema.py`` defines the runtime request contract.
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
    """Define the SageMaker serverless endpoint size."""

    memory_mb: int
    max_concurrency: int


class MonitorConfig(TypedDict):
    """Define the drift schedule and endpoint alarm settings."""

    schedule_cron: str
    silence_alarm_hours: int


class SecurityServicesConfig(TypedDict):
    """Define the six `security.services` enablement flags.

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
    """Define audit retention, budget alarms, and service flags."""

    audit_log_retention_days: int
    budget_thresholds: list[int]
    # AWS Budgets operates at account scope. Only one environment owns the budget.
    account_budget: bool
    services: SecurityServicesConfig


class CicdConfig(TypedDict):
    """Define the GitHub Actions deployment identity."""

    github_repository: str
    # The OIDC provider is account-wide. Dev owns it. Prod reads it by ARN.
    owns_oidc_provider: bool


class WebsiteConfig(TypedDict):
    """Define the public demo website.

    `build_app` skips `WebsiteStack` when `enabled` is false, so the
    environment pays for no instance.
    """

    enabled: bool
    instance_type: str
    # Limit how many predictions one caller may request each minute.
    rate_limit_per_minute: int
    # The CloudFront origin-facing managed prefix list for the deploy region.
    cloudfront_prefix_list_id: str


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
    # Set the lifetime for objects under the capture prefix.
    capture_retention_days: int
    security: SecurityConfig
    cicd: CicdConfig
    website: WebsiteConfig


# These S3 prefixes connect writers with IAM grants.
# A mismatched prefix fails at run time. `tests/unit/test_pipeline.py` compares them.
# The SageMaker image does not install `infra` for `src/pipeline/` imports.
#
# - `config`: Config writes audit data under this prefix.
# - `training`: The training step writes `model.tar.gz` under this prefix.
# - `evaluations`: The evaluation step writes reports under this prefix.
# - `monitor`: The preprocessing step writes the drift baseline under this prefix.
# - `capture`: The proxy writes predictions and the drift Lambda reads them.
CONFIG_DELIVERY_PREFIX = "config"
MODEL_ARTIFACT_PREFIX = "training"
EVALUATION_REPORT_PREFIX = "evaluations"
MONITOR_OUTPUT_PREFIX = "monitor"
CAPTURE_PREFIX = "capture"

# The preprocessing step writes this key. The drift Lambda reads it.
BASELINE_KEY = f"{MONITOR_OUTPUT_PREFIX}/baseline/baseline.json"


_LOG_RETENTION = {
    7: logs.RetentionDays.ONE_WEEK,
    14: logs.RetentionDays.TWO_WEEKS,
    30: logs.RetentionDays.ONE_MONTH,
    90: logs.RetentionDays.THREE_MONTHS,
}


def github_deploy_role_name(env_name: str) -> str:
    """Return the shared CI deploy role name for one environment.

    `CicdStack`, `SecurityMonitoringStack`, and `SecurityStack` use this name.
    """
    return f"mlops-{env_name}-github-deploy"


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
    """Create a Python 3.12 Lambda with platform defaults.

    The function uses an explicit log group with the configured retention.
    CDK generates the log group name. Stack deletion removes the log group.
    The function uses the shared `src/` asset unless `code` is supplied.
    """
    log_group = logs.LogGroup(
        scope,
        f"{construct_id}Logs",
        retention=log_retention(config),
        removal_policy=RemovalPolicy.DESTROY,
    )
    role: iam.IRole | None = None
    if least_privilege_logs:
        # `AWSLambdaBasicExecutionRole` grants access to all account log groups.
        # This role writes only to the explicit log group.
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
    """Create an execution role for SageMaker.

    The role carries `AmazonSageMakerFullAccess` unless `least_privilege` is
    set. With that flag it carries no managed policy, and the caller grants
    every permission explicitly.

    Never pass `role_name`. Never rename the construct. Update each role in
    place. The endpoint and pipeline definition pin their role ARNs.
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
    """Create an EventBridge rule that invokes a Lambda.

    The default source covers registry and endpoint events. The drift loop
    supplies its platform event source.
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
