"""Repository security gate and explicit acknowledgements of existing debt.

Every acknowledgement is bound to one construct and names the phase that removes
or re-evaluates it. New resources and new findings therefore fail synthesis
instead of inheriting a stack-wide suppression.
"""

from dataclasses import dataclass

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks


@dataclass(frozen=True)
class Acknowledgement:
    stack: str
    construct_path: str
    finding_id: str
    reason: str


LAMBDA_BASIC_POLICY = (
    "AwsSolutions-IAM4[Policy::arn:<AWS::Partition>:iam::aws:policy/"
    "service-role/AWSLambdaBasicExecutionRole]"
)
SAGEMAKER_FULL_ACCESS = (
    "AwsSolutions-IAM4[Policy::arn:<AWS::Partition>:iam::aws:policy/AmazonSageMakerFullAccess]"
)
APIGW_LOG_POLICY = (
    "AwsSolutions-IAM4[Policy::arn:<AWS::Partition>:iam::aws:policy/"
    "service-role/AmazonAPIGatewayPushToCloudWatchLogs]"
)


ACKNOWLEDGEMENTS = (
    Acknowledgement(
        "security",
        "AccessLogBucket",
        "AwsSolutions::AwsSolutions-S1",
        "Phase 2 access-log sink must not recursively deliver server access logs to itself.",
    ),
    Acknowledgement(
        "security",
        "CloudTrailLogsRole/DefaultPolicy",
        (
            "AwsSolutions-IAM5[Resource::arn:<AWS::Partition>:logs:<AWS::Region>:"
            "<AWS::AccountId>:log-group:/aws/cloudtrail/mlops-dev-audit:log-stream:*]"
        ),
        "Phase 2 CloudTrail delivery requires the generated log-stream suffix under one group.",
    ),
    # Data: server access logging is evaluated with the Phase 2 audit design.
    *(
        Acknowledgement(
            "data",
            bucket,
            "AwsSolutions::AwsSolutions-S1",
            "Existing private ML bucket; decide centralized access-log destination in Phase 2.",
        )
        for bucket in ("RawBucket", "CuratedBucket", "ArtifactsBucket")
    ),
    Acknowledgement(
        "data",
        "BucketNotificationsHandler050a0587b7544547bf325f094a3db834/Role",
        LAMBDA_BASIC_POLICY,
        "CDK singleton notification provider; replace managed log policy during Phase 5 IAM work.",
    ),
    # Ingestion: existing Lambda/queue findings remain visible until their named phase.
    Acknowledgement(
        "ingestion",
        "ValidateFn/ServiceRole",
        LAMBDA_BASIC_POLICY,
        "Existing validation Lambda; replace managed log policy during Phase 5 IAM work.",
    ),
    Acknowledgement(
        "ingestion",
        "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8a/ServiceRole",
        LAMBDA_BASIC_POLICY,
        "CDK log-retention provider; remove with explicit log groups during Phase 7 logging work.",
    ),
    *(
        Acknowledgement(
            "ingestion",
            queue,
            "AwsSolutions::AwsSolutions-SQS4",
            "Existing queue lacks a TLS-only policy; remediate before the Phase 2 deploy.",
        )
        for queue in ("IngestDlq", "IngestQueue")
    ),
    *(
        Acknowledgement(
            "ingestion",
            "ValidateFn/ServiceRole/DefaultPolicy",
            f"AwsSolutions-IAM5[Action::{action}]",
            "CDK S3 grant uses wildcard actions; narrow during Phase 5 IAM work.",
        )
        for action in (
            "s3:GetObject*",
            "s3:GetBucket*",
            "s3:List*",
            "s3:DeleteObject*",
            "s3:Abort*",
        )
    ),
    *(
        Acknowledgement(
            "ingestion",
            "ValidateFn/ServiceRole/DefaultPolicy",
            f"AwsSolutions-IAM5[Resource::{resource}]",
            "Object access is limited to one imported bucket; replace with a Phase 5 policy.",
        )
        for resource in (
            "Mlops-Dev-Data:ExportsOutputFnGetAttRawBucket0C3EE094ArnD2F95F99/*",
            "Mlops-Dev-Data:ExportsOutputFnGetAttCuratedBucket6A59C97EArn2BF9884A/*",
        )
    ),
    Acknowledgement(
        "ingestion",
        "ValidateFn",
        "AwsSolutions::AwsSolutions-L1",
        "Python 3.12 matches the packaged native runtime; review runtime in Phase 7.",
    ),
    Acknowledgement(
        "ingestion",
        "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8a/ServiceRole/DefaultPolicy",
        "AwsSolutions-IAM5[Resource::*]",
        "CDK log-retention provider manages generated log groups; remove in Phase 7.",
    ),
    # Training role: broad managed policy and generated S3 actions are Phase 5 debt.
    Acknowledgement(
        "training",
        "PipelineExecutionRole",
        SAGEMAKER_FULL_ACCESS,
        "Known broad pipeline role recorded in Phase 0; replace role policy in Phase 5.",
    ),
    *(
        Acknowledgement(
            "training",
            "PipelineExecutionRole/DefaultPolicy",
            f"AwsSolutions-IAM5[Action::{action}]",
            "CDK S3 grants use wildcard actions; replace with Phase 5 pipeline permissions.",
        )
        for action in (
            "s3:GetObject*",
            "s3:GetBucket*",
            "s3:List*",
            "s3:DeleteObject*",
            "s3:Abort*",
        )
    ),
    *(
        Acknowledgement(
            "training",
            "PipelineExecutionRole/DefaultPolicy",
            f"AwsSolutions-IAM5[Resource::{resource}]",
            "Object wildcard is limited to an imported workload bucket; replace in Phase 5.",
        )
        for resource in (
            "Mlops-Dev-Data:ExportsOutputFnGetAttCuratedBucket6A59C97EArn2BF9884A/*",
            "Mlops-Dev-Data:ExportsOutputFnGetAttArtifactsBucket2AAC5544ArnD57FAE19/*",
        )
    ),
    # Serving IAM debt and current API controls are removed in Phases 5-8.
    Acknowledgement(
        "serving",
        "ModelExecutionRole",
        SAGEMAKER_FULL_ACCESS,
        "Known broad model role recorded in Phase 0; replace role policy in Phase 5.",
    ),
    *(
        Acknowledgement(
            "serving",
            "ModelExecutionRole/DefaultPolicy",
            f"AwsSolutions-IAM5[Action::{action}]",
            "CDK S3 grant uses wildcard actions; replace model permissions in Phase 5.",
        )
        for action in (
            "s3:GetObject*",
            "s3:GetBucket*",
            "s3:List*",
            "s3:DeleteObject*",
            "s3:Abort*",
        )
    ),
    Acknowledgement(
        "serving",
        "ModelExecutionRole/DefaultPolicy",
        "AwsSolutions-IAM5[Resource::Mlops-Dev-Data:ExportsOutputFnGetAttArtifactsBucket2AAC5544ArnD57FAE19/*]",
        "Object wildcard is limited to artifacts; use a read-only model prefix in Phase 5.",
    ),
    *(
        Acknowledgement(
            "serving",
            role,
            LAMBDA_BASIC_POLICY,
            "Existing Lambda uses the standard log policy; replace it in Phase 5.",
        )
        for role in ("DeployFn/ServiceRole", "ProxyFn/ServiceRole")
    ),
    Acknowledgement(
        "serving",
        "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8a/ServiceRole",
        LAMBDA_BASIC_POLICY,
        "CDK log-retention provider; remove with explicit log groups during Phase 7.",
    ),
    Acknowledgement(
        "serving",
        "DeployFn/ServiceRole/DefaultPolicy",
        "AwsSolutions-IAM5[Resource::*]",
        "Known SageMaker deployment wildcard recorded in Phase 0; scope in Phase 5.",
    ),
    Acknowledgement(
        "serving",
        "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8a/ServiceRole/DefaultPolicy",
        "AwsSolutions-IAM5[Resource::*]",
        "CDK log-retention provider manages generated log groups; remove in Phase 7.",
    ),
    *(
        Acknowledgement(
            "serving",
            function,
            "AwsSolutions::AwsSolutions-L1",
            "Python 3.12 matches packaged native dependencies; review runtime in Phase 7.",
        )
        for function in ("DeployFn", "ProxyFn")
    ),
    Acknowledgement(
        "serving",
        "ChurnApi",
        "AwsSolutions::AwsSolutions-APIG2",
        "Proxy Lambda performs Pydantic validation; add API Gateway request validation in Phase 7.",
    ),
    Acknowledgement(
        "serving",
        "ChurnApi/CloudWatchRole",
        APIGW_LOG_POLICY,
        "CDK API Gateway account role; replace or explicitly retain during Phase 7 logging work.",
    ),
    *(
        Acknowledgement(
            "serving",
            "ChurnApi/DeploymentStage.dev",
            finding,
            reason,
        )
        for finding, reason in (
            (
                "AwsSolutions::AwsSolutions-APIG1",
                "Access logging is scheduled for Phase 7 after sensitive-field format review.",
            ),
            (
                "AwsSolutions::AwsSolutions-APIG6",
                "Execution logging is scheduled for Phase 7 after sensitive-field format review.",
            ),
            (
                "AwsSolutions::AwsSolutions-APIG3",
                "WAF is intentionally isolated to Phase 8 and starts in count mode.",
            ),
        )
    ),
    *(
        Acknowledgement(
            "serving",
            "ChurnApi/Default/predict/POST",
            finding,
            "Phase 0 records the API-key boundary; replace it with IAM in Phase 6.",
        )
        for finding in (
            "AwsSolutions::AwsSolutions-APIG4",
            "AwsSolutions::AwsSolutions-COG4",
        )
    ),
    # Monitoring Lambda findings remain until IAM and logging phases.
    Acknowledgement(
        "monitoring",
        "RetrainTriggerFn/ServiceRole",
        LAMBDA_BASIC_POLICY,
        "Existing retrain Lambda; replace managed log policy during Phase 5 IAM work.",
    ),
    Acknowledgement(
        "monitoring",
        "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8a/ServiceRole",
        LAMBDA_BASIC_POLICY,
        "CDK log-retention provider; remove with explicit log groups during Phase 7.",
    ),
    Acknowledgement(
        "monitoring",
        "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8a/ServiceRole/DefaultPolicy",
        "AwsSolutions-IAM5[Resource::*]",
        "CDK log-retention provider manages generated log groups; remove in Phase 7.",
    ),
    Acknowledgement(
        "monitoring",
        "RetrainTriggerFn",
        "AwsSolutions::AwsSolutions-L1",
        "Python 3.12 is the deployed baseline; review runtime in Phase 7.",
    ),
)


def _construct_at(stack: cdk.Stack, relative_path: str):
    expected = f"{stack.node.path}/{relative_path}"
    matches = [construct for construct in stack.node.find_all() if construct.node.path == expected]
    if len(matches) != 1:
        raise ValueError(
            f"security acknowledgement path {expected!r} matched {len(matches)} constructs"
        )
    return matches[0]


def apply_security_checks(app: cdk.App, stacks: dict[str, cdk.Stack]) -> None:
    """Register exact existing acknowledgements, then fail on any new finding."""
    for acknowledgement in ACKNOWLEDGEMENTS:
        construct = _construct_at(stacks[acknowledgement.stack], acknowledgement.construct_path)
        target = construct.node.default_child or construct
        finding_id = acknowledgement.finding_id.removeprefix("AwsSolutions::")
        acknowledgment = cdk.Acknowledgment(
            id=finding_id,
            reason=acknowledgement.reason,
        )
        if "::" in finding_id:
            # CDK 2.261 rejects granular cdk-nag IDs containing ARN/finding
            # delimiters. This is the exact metadata emitted by acknowledge().
            target.node.add_metadata(
                cdk.Validations.ACKNOWLEDGED_RULES_METADATA_KEY,
                {f"annotation::{finding_id}": acknowledgement.reason},
            )
        else:
            cdk.Validations.of(target).acknowledge(acknowledgment)

    cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app, verbose=True))
