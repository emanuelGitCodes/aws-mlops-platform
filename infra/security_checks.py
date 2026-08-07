"""Repository security gate and explicit acknowledgements of existing debt.

Each acknowledgement binds to one construct and names the phase that removes or
re-evaluates it. A new resource or a new finding therefore fails synthesis. It
cannot inherit a stack-wide suppression.
"""

from dataclasses import dataclass, replace

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks
from constructs import IConstruct

from infra.stacks.shared import PlatformConfig

# Some acknowledgement strings embed the environment: a deployment stage, the
# audit log group, a cross-stack export, or the model package group. They
# cannot be dev literals shared by every environment. Write these tokens
# instead. `resolved_acknowledgements` fills them in per environment. It uses
# `str.replace`, not `str.format`, so a brace in a future reason string stays
# inert.
ENV_TOKEN = "{env}"
PREFIX_TOKEN = "{prefix}"
GROUP_TOKEN = "{group}"
PIPELINE_TOKEN = "{pipeline}"

# Enablement flag for the account-wide budget. It sits beside the service
# flags, not inside them. `security.services` is validated as exactly six
# flags, and the budget is not one of the services.
ACCOUNT_BUDGET_FLAG = "account_budget"


@dataclass(frozen=True)
class Acknowledgement:
    stack: str
    construct_path: str
    finding_id: str
    reason: str
    # A flag-gated construct exists only where its flag is enabled. Naming the
    # flag here skips the acknowledgement everywhere else. Leaving it None keeps
    # the strict behaviour: a path that matches no construct fails synthesis,
    # which catches a stale acknowledgement.
    requires_flag: str | None = None


LAMBDA_BASIC_POLICY = (
    "AwsSolutions-IAM4[Policy::arn:<AWS::Partition>:iam::aws:policy/"
    "service-role/AWSLambdaBasicExecutionRole]"
)
# No role carries `AmazonSageMakerFullAccess`, so nothing acknowledges it.
# `test_broad_sagemaker_managed_policy_baseline_has_not_grown` keeps it out.
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
            "<AWS::AccountId>:log-group:/aws/cloudtrail/mlops-{env}-audit:log-stream:*]"
        ),
        "Phase 2 CloudTrail delivery requires the generated log-stream suffix under one group.",
    ),
    Acknowledgement(
        "security_monitoring",
        "AWS679f53fac002430cb0da5b7982bd2287/ServiceRole",
        LAMBDA_BASIC_POLICY,
        "Phase 3E account-BPA provider; replace managed log policy during Phase 5 IAM work.",
        requires_flag="account_bpa",
    ),
    Acknowledgement(
        "security_monitoring",
        "AccountPublicAccessBlock/CustomResourcePolicy",
        "AwsSolutions-IAM5[Resource::*]",
        (
            "Phase 3E account-level Block Public Access is not bucket-scoped; AWS accepts "
            "only '*' as the resource for the s3:*AccountPublicAccessBlock actions."
        ),
        requires_flag="account_bpa",
    ),
    Acknowledgement(
        "data",
        "BucketNotificationsHandler050a0587b7544547bf325f094a3db834/Role",
        LAMBDA_BASIC_POLICY,
        "CDK singleton notification provider; replace managed log policy during Phase 5 IAM work.",
    ),
    Acknowledgement(
        "data",
        "AWS679f53fac002430cb0da5b7982bd2287/ServiceRole",
        LAMBDA_BASIC_POLICY,
        "Phase 2 budget API provider; replace managed log policy during Phase 5 IAM work.",
        requires_flag=ACCOUNT_BUDGET_FLAG,
    ),
    Acknowledgement(
        "ingestion",
        "ValidateFn/ServiceRole",
        LAMBDA_BASIC_POLICY,
        "Existing validation Lambda; replace managed log policy during Phase 5 IAM work.",
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
            "{prefix}-Data:ExportsOutputFnGetAttRawBucket0C3EE094ArnD2F95F99/*",
            "{prefix}-Data:ExportsOutputFnGetAttCuratedBucket6A59C97EArn2BF9884A/*",
        )
    ),
    Acknowledgement(
        "ingestion",
        "ValidateFn",
        "AwsSolutions::AwsSolutions-L1",
        "Python 3.12 matches the packaged native runtime; review runtime in Phase 7.",
    ),
    # Training role. Two wildcard classes remain: the object wildcard under
    # each named prefix, and the two generated job names. SageMaker names every
    # pipeline job `pipelines-<execution-id>-<Step>-<suffix>`, which no policy
    # can enumerate before the run.
    *(
        Acknowledgement(
            "training",
            "PipelineExecutionRole/DefaultPolicy",
            f"AwsSolutions-IAM5[Resource::{resource}]",
            (
                "Phase 5D scoped this to one prefix of one workload bucket; the object "
                "wildcard is the narrowest form S3 accepts."
            ),
        )
        for resource in (
            "{prefix}-Data:ExportsOutputFnGetAttCuratedBucket6A59C97EArn2BF9884A/telco/*",
            "{prefix}-Data:ExportsOutputFnGetAttArtifactsBucket2AAC5544ArnD57FAE19/{pipeline}/*",
            "{prefix}-Data:ExportsOutputFnGetAttArtifactsBucket2AAC5544ArnD57FAE19/training/*",
            "{prefix}-Data:ExportsOutputFnGetAttArtifactsBucket2AAC5544ArnD57FAE19/evaluations/*",
            "{prefix}-Data:ExportsOutputFnGetAttArtifactsBucket2AAC5544ArnD57FAE19/monitor/*",
        )
    ),
    *(
        Acknowledgement(
            "training",
            "PipelineExecutionRole/DefaultPolicy",
            f"AwsSolutions-IAM5[Resource::arn:<AWS::Partition>:sagemaker:<AWS::Region>:"
            f"<AWS::AccountId>:{resource}]",
            (
                "Phase 5D: SageMaker generates the job name per execution, so `pipelines-*` "
                "is the tightest ARN a policy can name."
            ),
        )
        for resource in ("processing-job/pipelines-*", "training-job/pipelines-*")
    ),
    *(
        Acknowledgement(
            "training",
            "PipelineExecutionRole/DefaultPolicy",
            f"AwsSolutions-IAM5[Resource::arn:<AWS::Partition>:logs:<AWS::Region>:"
            f"<AWS::AccountId>:log-group:/aws/sagemaker/{job_type}Jobs:*]",
            (
                "Phase 5D: the stream wildcard is one SageMaker-owned log group, and the "
                "per-job stream name is generated at run time."
            ),
        )
        for job_type in ("Processing", "Training")
    ),
    Acknowledgement(
        "training",
        "PipelineExecutionRole/DefaultPolicy",
        (
            "AwsSolutions-IAM5[Resource::arn:<AWS::Partition>:sagemaker:<AWS::Region>:"
            "<AWS::AccountId>:model-package/{group}/*]"
        ),
        (
            "Phase 5D: the package version is assigned at registration, so the wildcard "
            "is confined to this platform's own model package group."
        ),
    ),
    # Serving. Only the object wildcard under one prefix remains, and no
    # policy can address those keys without it.
    Acknowledgement(
        "serving",
        "ModelExecutionRole/DefaultPolicy",
        (
            "AwsSolutions-IAM5[Resource::{prefix}-Data:ExportsOutputFnGetAttArtifactsBucket"
            "2AAC5544ArnD57FAE19/training/*]"
        ),
        (
            "Phase 5B scoped the model role to read-only GetObject under the training "
            "prefix; the object wildcard is inherent to reading generated artifact keys."
        ),
    ),
    Acknowledgement(
        "serving",
        "ModelExecutionRole/DefaultPolicy",
        (
            "AwsSolutions-IAM5[Resource::arn:<AWS::Partition>:logs:<AWS::Region>:"
            "<AWS::AccountId>:log-group:/aws/sagemaker/Endpoints/churn-serverless-{env}:*]"
        ),
        (
            "Phase 5B endpoint logging: the suffix is the generated log-stream wildcard "
            "under one SageMaker-owned group, which is what PutLogEvents requires."
        ),
    ),
    # Deploy role. Three ARNs remain, and each trailing wildcard is
    # unavoidable. `deploy_handler` suffixes every model and endpoint-config
    # name with the epoch second, and the model package is addressed by version
    # under one group.
    *(
        Acknowledgement(
            "serving",
            "DeployFnRole/DefaultPolicy",
            (
                "AwsSolutions-IAM5[Resource::arn:<AWS::Partition>:sagemaker:<AWS::Region>:"
                f"<AWS::AccountId>:{resource}]"
            ),
            reason,
        )
        for resource, reason in (
            (
                "model/churn-serverless-{env}-model-*",
                "Phase 5C scoped CreateModel to this endpoint's own generated model names.",
            ),
            (
                "endpoint-config/churn-serverless-{env}-config-*",
                "Phase 5C scoped the endpoint-config actions to this endpoint's generated names.",
            ),
            (
                "model-package/{group}/*",
                "Phase 5C scoped DescribeModelPackage to versions of this platform's own group.",
            ),
        )
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
            "ChurnApi/DeploymentStage.{env}",
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
    Acknowledgement(
        "monitoring",
        "RetrainTriggerFn/ServiceRole",
        LAMBDA_BASIC_POLICY,
        "Existing retrain Lambda; replace managed log policy during Phase 5 IAM work.",
    ),
    Acknowledgement(
        "monitoring",
        "RetrainTriggerFn",
        "AwsSolutions::AwsSolutions-L1",
        "Python 3.12 is the deployed baseline; review runtime in Phase 7.",
    ),
)


def _resolve(text: str, config: PlatformConfig, prefix: str) -> str:
    return (
        text.replace(ENV_TOKEN, config["env_name"])
        .replace(PREFIX_TOKEN, prefix)
        .replace(GROUP_TOKEN, config["model_package_group"])
        .replace(PIPELINE_TOKEN, config["pipeline_name"])
    )


def resolved_acknowledgements(config: PlatformConfig, prefix: str) -> tuple[Acknowledgement, ...]:
    """Return `ACKNOWLEDGEMENTS` with the environment tokens filled in.

    This is the only place that resolves tokens. `apply_security_checks` and
    the tests share it, so the two cannot disagree about what a path resolves
    to. It takes the whole config instead of the individual values, because
    each new token would otherwise lengthen the signature.
    """
    return tuple(
        replace(
            acknowledgement,
            construct_path=_resolve(acknowledgement.construct_path, config, prefix),
            finding_id=_resolve(acknowledgement.finding_id, config, prefix),
        )
        for acknowledgement in ACKNOWLEDGEMENTS
    )


def acknowledgement_metadata_key(finding_id: str) -> str:
    """Return the metadata key CDK records for `finding_id`.

    The two registration paths namespace their keys differently, and the
    difference is silent. A wrong key records without error and then never
    matches a finding. This function derives the key once.
    `apply_security_checks` and the tests share it.
    """
    bare_id = finding_id.removeprefix("AwsSolutions::")
    # Granular ids are keyed without the namespace. Plain rule ids keep it.
    return f"annotation::{bare_id}" if "::" in bare_id else finding_id


def _construct_at(stack: cdk.Stack, relative_path: str) -> IConstruct:
    expected = f"{stack.node.path}/{relative_path}"
    matches = [construct for construct in stack.node.find_all() if construct.node.path == expected]
    if len(matches) != 1:
        raise ValueError(
            f"security acknowledgement path {expected!r} matched {len(matches)} constructs"
        )
    return matches[0]


def apply_security_checks(
    app: cdk.App, stacks: dict[str, cdk.Stack], config: PlatformConfig, prefix: str
) -> None:
    """Register the existing acknowledgements, then fail on any new finding."""
    # Collect the names, because a TypedDict cannot be indexed by a flag name
    # known only at runtime.
    enabled = {name for name, on in config["security"]["services"].items() if on}
    # Index by literal, because mypy requires one for a TypedDict. The constant
    # names the same key. A mismatch fails synthesis loudly. Otherwise the
    # acknowledgement would be skipped while its construct still exists, and
    # that leaves an unacknowledged cdk-nag finding.
    if config["security"]["account_budget"]:
        enabled.add(ACCOUNT_BUDGET_FLAG)
    for acknowledgement in resolved_acknowledgements(config, prefix):
        if acknowledgement.requires_flag and acknowledgement.requires_flag not in enabled:
            continue
        construct = _construct_at(stacks[acknowledgement.stack], acknowledgement.construct_path)
        target = construct.node.default_child or construct
        # A granular id carries its own `Action::`, `Resource::`, or `Policy::`
        # delimiter. A plain rule id carries only the leading namespace. The two
        # take different registration paths and disagree about the namespace, so
        # this line draws the distinction once.
        bare_id = acknowledgement.finding_id.removeprefix("AwsSolutions::")
        if "::" in bare_id:
            # A granular cdk-nag id embeds an ARN, and `acknowledge()` rejects
            # those, so write the metadata it would have written. The key takes
            # the id without the namespace. A namespaced key stops matching,
            # and it does so without any error.
            target.node.add_metadata(
                cdk.Validations.ACKNOWLEDGED_RULES_METADATA_KEY,
                {acknowledgement_metadata_key(acknowledgement.finding_id): acknowledgement.reason},
            )
        else:
            # Acknowledge under the id as written, with the namespace.
            # aws-cdk-lib 2.261 also matches the bare form. 2.262 matches only
            # the namespaced form, and it stops suppressing without warning.
            # A bare id there lapses every plain acknowledgement and reopens 13
            # findings.
            cdk.Validations.of(target).acknowledge(
                cdk.Acknowledgment(
                    id=acknowledgement.finding_id,
                    reason=acknowledgement.reason,
                )
            )

    cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app, verbose=True))
