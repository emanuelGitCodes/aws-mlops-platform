"""Apply the repository security gate and construct-specific acknowledgements.

Each acknowledgement binds to one construct. New constructs and findings fail
synthesis. Stack-wide suppressions are not used.
"""

from dataclasses import dataclass, replace

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks
from constructs import IConstruct

from infra.stacks.shared import PlatformConfig

# These tokens represent environment-specific values in acknowledgement text.
# `resolved_acknowledgements` replaces them for each environment.
# `str.replace` preserves unrelated braces in a reason string.
ENV_TOKEN = "{env}"
PREFIX_TOKEN = "{prefix}"
GROUP_TOKEN = "{group}"
PIPELINE_TOKEN = "{pipeline}"

# The account budget flag is separate from the six `security.services` flags.
ACCOUNT_BUDGET_FLAG = "account_budget"

# `build_app` skips `WebsiteStack` when `website.enabled` is false, so every
# website acknowledgement MUST carry this flag.
WEBSITE_FLAG = "website"


@dataclass(frozen=True)
class Acknowledgement:
    stack: str
    construct_path: str
    finding_id: str
    reason: str
    # Set this field only for a flag-gated construct.
    # A missing construct path fails synthesis when this field is `None`.
    requires_flag: str | None = None


LAMBDA_BASIC_POLICY = (
    "AwsSolutions-IAM4[Policy::arn:<AWS::Partition>:iam::aws:policy/"
    "service-role/AWSLambdaBasicExecutionRole]"
)
# No role carries or acknowledges `AmazonSageMakerFullAccess`.
# `test_broad_sagemaker_managed_policy_baseline_has_not_grown` enforces this rule.
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
    # The training role uses wildcards for objects under named prefixes.
    # It also uses wildcards for generated SageMaker job names.
    # SageMaker assigns `pipelines-<execution-id>-<Step>-<suffix>` at run time.
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
    # The model role reads generated object keys under one named prefix.
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
    Acknowledgement(
        "serving",
        "ProxyFnRole/DefaultPolicy",
        (
            "AwsSolutions-IAM5[Resource::{prefix}-Data:ExportsOutputFnGetAttArtifactsBucket"
            "2AAC5544ArnD57FAE19/capture/*]"
        ),
        (
            "The proxy is the capture point, because a serverless endpoint has no data "
            "capture; PutObject writes one generated key per prediction and reads nothing. "
            "Phase 4 re-evaluates this grant when the bucket moves to a customer-managed key."
        ),
    ),
    # The deploy role uses three ARNs with generated trailing values.
    # `deploy_handler` adds the epoch second to model and endpoint-config names.
    # SageMaker assigns the model package version under one group.
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
        "DriftEvaluationFnRole/DefaultPolicy",
        (
            "AwsSolutions-IAM5[Resource::{prefix}-Data:ExportsOutputFnGetAttArtifactsBucket"
            "2AAC5544ArnD57FAE19/capture/*]"
        ),
        (
            "The drift job reads a window of capture objects whose keys are generated per "
            "prediction; the grant is GetObject only, and ListBucket carries a prefix condition. "
            "Phase 4 re-evaluates this grant when the bucket moves to a customer-managed key."
        ),
    ),
    *(
        Acknowledgement(
            "monitoring",
            function,
            "AwsSolutions::AwsSolutions-L1",
            "Python 3.12 is the deployed baseline; review runtime in Phase 7.",
        )
        for function in ("RetrainTriggerFn", "DriftEvaluationFn")
    ),
    Acknowledgement(
        "website",
        "WebsiteInstanceRole",
        "AwsSolutions-IAM4[Policy::arn:<AWS::Partition>:iam::aws:policy/"
        "AmazonSSMManagedInstanceCore]",
        (
            "Phase 7 replaces the SSM managed policy with a scoped session policy; "
            "Session Manager is the only shell path, because the instance opens no "
            "SSH port."
        ),
        requires_flag=WEBSITE_FLAG,
    ),
    Acknowledgement(
        "website",
        "WebsiteInstanceRole/DefaultPolicy",
        "AwsSolutions-IAM5[Resource::*]",
        (
            "Phase 7 website image pull; AWS accepts only '*' as the resource for "
            "ecr:GetAuthorizationToken."
        ),
        requires_flag=WEBSITE_FLAG,
    ),
    Acknowledgement(
        "website",
        "WebsiteInstanceRole/DefaultPolicy",
        (
            "AwsSolutions-IAM5[Resource::{prefix}-Data:ExportsOutputFnGetAtt"
            "ArtifactsBucket2AAC5544ArnD57FAE19/evaluations/*]"
        ),
        (
            "Phase 7 website reads every evaluation report; the object names carry a "
            "generated suffix under one prefix."
        ),
        requires_flag=WEBSITE_FLAG,
    ),
    Acknowledgement(
        "website",
        "WebsiteInstance",
        "AwsSolutions::AwsSolutions-EC28",
        (
            "Phase 7 revisits paid detailed monitoring; the five-minute basic metrics "
            "answer the demo site."
        ),
        requires_flag=WEBSITE_FLAG,
    ),
    Acknowledgement(
        "website",
        "WebsiteInstance",
        "AwsSolutions::AwsSolutions-EC29",
        (
            "Phase 7 keeps the instance replaceable; a new image rolls it, and the "
            "instance holds no state."
        ),
        requires_flag=WEBSITE_FLAG,
    ),
    *(
        Acknowledgement(
            "website",
            "WebsiteDistribution",
            f"AwsSolutions::AwsSolutions-{finding}",
            reason,
            requires_flag=WEBSITE_FLAG,
        )
        for finding, reason in (
            (
                "CFR1",
                "Phase 8 revisits geo restriction; the demo site serves every reader.",
            ),
            (
                "CFR2",
                "Phase 8 starts WAF in count mode; the app rate-limits predictions today.",
            ),
            (
                "CFR3",
                "Phase 7 revisits access logs; a log bucket costs more than the site.",
            ),
            (
                "CFR4",
                "Phase 9 adds a custom domain and ACM; the default certificate pins no "
                "minimum TLS version.",
            ),
            (
                "CFR5",
                "Phase 9 adds TLS to the origin; the security group admits the "
                "CloudFront prefix list only.",
            ),
        )
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
    """Return `ACKNOWLEDGEMENTS` with all environment tokens resolved.

    `apply_security_checks` and the tests use this function. The function
    accepts `PlatformConfig` as the source for all token values.
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
    # Granular ids omit the namespace. Plain rule ids keep the namespace.
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
    """Register configured acknowledgements and fail on new findings."""
    # Runtime flag names cannot index a `TypedDict` directly.
    enabled = {name for name, on in config["security"]["services"].items() if on}
    # Use a literal key for `TypedDict` indexing.
    # `ACCOUNT_BUDGET_FLAG` must match this key.
    if config["security"]["account_budget"]:
        enabled.add(ACCOUNT_BUDGET_FLAG)
    # The flag check below runs before the stack lookup, so a disabled website
    # skips every acknowledgement that names the absent stack.
    if config["website"]["enabled"]:
        enabled.add(WEBSITE_FLAG)
    for acknowledgement in resolved_acknowledgements(config, prefix):
        if acknowledgement.requires_flag and acknowledgement.requires_flag not in enabled:
            continue
        construct = _construct_at(stacks[acknowledgement.stack], acknowledgement.construct_path)
        target = construct.node.default_child or construct
        # A granular id contains an `Action::`, `Resource::`, or `Policy::` delimiter.
        # A plain rule id contains only the leading namespace.
        bare_id = acknowledgement.finding_id.removeprefix("AwsSolutions::")
        if "::" in bare_id:
            # `acknowledge()` rejects granular cdk-nag ids that contain an ARN.
            # Write the matching metadata key without the namespace.
            target.node.add_metadata(
                cdk.Validations.ACKNOWLEDGED_RULES_METADATA_KEY,
                {acknowledgement_metadata_key(acknowledgement.finding_id): acknowledgement.reason},
            )
        else:
            # Register a plain rule id with its namespace.
            cdk.Validations.of(target).acknowledge(
                cdk.Acknowledgment(
                    id=acknowledgement.finding_id,
                    reason=acknowledgement.reason,
                )
            )

    cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app, verbose=True))
