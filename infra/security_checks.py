"""Repository security gate and explicit acknowledgements of existing debt.

Every acknowledgement is bound to one construct and names the phase that removes
or re-evaluates it. New resources and new findings therefore fail synthesis
instead of inheriting a stack-wide suppression.
"""

from dataclasses import dataclass, replace

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks
from constructs import IConstruct

from infra.stacks.shared import PlatformConfig

# Acknowledgement strings that name a deployment stage, the audit log group, a
# cross-stack export, or the model package group embed the environment, so they
# cannot be written as dev literals shared by every environment. Write these
# tokens instead; they are resolved per environment by
# `resolved_acknowledgements`. Plain `str.replace` rather than `str.format`, so
# a brace in a future reason string is inert.
ENV_TOKEN = "{env}"
PREFIX_TOKEN = "{prefix}"
GROUP_TOKEN = "{group}"

# Enablement flag for the account-wide budget. It lives beside the Phase 3
# service flags rather than inside them: `security.services` is validated as
# exactly the six Phase 3 flags, and this is a Phase 2 resource.
ACCOUNT_BUDGET_FLAG = "account_budget"


@dataclass(frozen=True)
class Acknowledgement:
    stack: str
    construct_path: str
    finding_id: str
    reason: str
    # Flag-gated constructs exist only where their flag is enabled -- the Phase 3
    # sub-phases, and the account-scoped budget that only one environment owns.
    # Naming the flag here skips the acknowledgement everywhere else; leaving it
    # None keeps the strict behavior, where a path that matches no construct
    # fails synthesis and catches a stale acknowledgement.
    requires_flag: str | None = None


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
    # Ingestion: existing Lambda/queue findings remain visible until their named phase.
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
            "{prefix}-Data:ExportsOutputFnGetAttCuratedBucket6A59C97EArn2BF9884A/*",
            "{prefix}-Data:ExportsOutputFnGetAttArtifactsBucket2AAC5544ArnD57FAE19/*",
        )
    ),
    # Serving IAM debt and current API controls are removed in Phases 5-8.
    # Phase 5B removed the model role's `AmazonSageMakerFullAccess` and the five
    # CDK S3 grant wildcards; what remains is the object wildcard under one
    # prefix, which no policy can express without one.
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
    # Phase 5C removed the deploy role's managed log policy and the six-action
    # `Resource: "*"` SageMaker statement recorded in Phase 0. What remains is
    # three ARNs whose trailing wildcard is inherent: `deploy_handler` suffixes
    # every model and endpoint-config name with the epoch second, and the model
    # package is addressed by version under one group.
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
    # Monitoring Lambda findings remain until IAM and logging phases.
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
    )


def resolved_acknowledgements(config: PlatformConfig, prefix: str) -> tuple[Acknowledgement, ...]:
    """`ACKNOWLEDGEMENTS` with the environment tokens filled in.

    The single place tokens are resolved, shared by `apply_security_checks` and
    the tests, so the two can never disagree about what a path resolves to.
    Takes the whole config rather than the individual values it substitutes:
    Phase 5C needed the model package group as well as the environment name, and
    every token after it comes from the same place instead of a longer signature.
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
    """The metadata key CDK ends up recording for `finding_id`.

    The two registration paths namespace their keys differently, and the
    difference is silent: a wrong key records fine and simply never matches a
    finding. Derived in one place, shared by `apply_security_checks` and the
    tests, so neither can drift from what is actually registered.
    """
    bare_id = finding_id.removeprefix("AwsSolutions::")
    # Granular ids are keyed un-namespaced; plain rule ids keep the namespace.
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
    """Register exact existing acknowledgements, then fail on any new finding."""
    # Collected by name, because a TypedDict cannot be indexed by a flag name
    # that is only known at runtime.
    enabled = {name for name, on in config["security"]["services"].items() if on}
    # Indexed by literal because mypy requires one for a TypedDict; the constant
    # names the same key, and a mismatch fails synthesis loudly rather than
    # silently -- the acknowledgement would be skipped while its construct still
    # exists, leaving an unacknowledged cdk-nag finding.
    if config["security"]["account_budget"]:
        enabled.add(ACCOUNT_BUDGET_FLAG)
    for acknowledgement in resolved_acknowledgements(config, prefix):
        if acknowledgement.requires_flag and acknowledgement.requires_flag not in enabled:
            continue
        construct = _construct_at(stacks[acknowledgement.stack], acknowledgement.construct_path)
        target = construct.node.default_child or construct
        # A granular id carries its own `Action::`/`Resource::`/`Policy::`
        # delimiter; a plain rule id carries only the leading namespace. The two
        # take different registration paths and disagree about the namespace, so
        # the distinction is drawn once, here.
        bare_id = acknowledgement.finding_id.removeprefix("AwsSolutions::")
        if "::" in bare_id:
            # cdk-nag's granular ids embed ARNs, which `acknowledge()` rejects
            # outright, so write the metadata it would have written. The key
            # takes the *un-namespaced* id: a namespaced key stops matching
            # silently, which is the same lapse the plain path suffered below.
            target.node.add_metadata(
                cdk.Validations.ACKNOWLEDGED_RULES_METADATA_KEY,
                {acknowledgement_metadata_key(acknowledgement.finding_id): acknowledgement.reason},
            )
        else:
            # Acknowledge under the id exactly as written -- namespace included.
            # Stripping it used to work: 2.261 matched a bare `AwsSolutions-S1`,
            # so the prefix looked redundant. 2.262 matches only the namespaced
            # form and silently stops suppressing, which lapses every plain
            # acknowledgement at once and reopens 13 findings. The namespaced
            # form is accepted by both versions; the bare form is not.
            cdk.Validations.of(target).acknowledge(
                cdk.Acknowledgment(
                    id=acknowledgement.finding_id,
                    reason=acknowledgement.reason,
                )
            )

    cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app, verbose=True))
