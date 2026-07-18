"""Cross-stack CDK helpers.

New module because these patterns repeat across several stacks and
``lambda_code.py`` is specific to the bundled Lambda asset; no other
stack-shared module exists.
"""

from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from infra.stacks.lambda_code import src_code

_LOG_RETENTION = {
    7: logs.RetentionDays.ONE_WEEK,
    14: logs.RetentionDays.TWO_WEEKS,
    30: logs.RetentionDays.ONE_MONTH,
    90: logs.RetentionDays.THREE_MONTHS,
}


def log_retention(config: dict) -> logs.RetentionDays:
    """Map the environment's ``log_retention_days`` to a RetentionDays value."""
    days = config["log_retention_days"]
    if days not in _LOG_RETENTION:
        raise ValueError(f"unsupported log_retention_days: {days}")
    return _LOG_RETENTION[days]


def platform_lambda(
    scope: Construct,
    construct_id: str,
    *,
    config: dict,
    code: lambda_.Code | None = None,
    **kwargs,
) -> lambda_.Function:
    """Lambda with platform defaults: Python 3.12, config-driven log retention,
    and the shared src/ asset unless other code is supplied."""
    return lambda_.Function(
        scope,
        construct_id,
        runtime=lambda_.Runtime.PYTHON_3_12,
        code=code if code is not None else src_code(),
        log_retention=log_retention(config),
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
    detail: dict,
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
