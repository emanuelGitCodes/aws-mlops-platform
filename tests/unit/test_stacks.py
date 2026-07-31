"""CDK assertion tests: synth each stack and verify the security-critical wiring.

Asset bundling is stubbed via the `aws:cdk:bundling-stacks` context so tests
don't need pip/Docker.
"""

import hashlib
import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from infra.app import build_app, load_config, stack_prefix
from infra.security_checks import resolved_acknowledgements
from infra.stacks.security_monitoring_stack import (
    IMPLEMENTED_SERVICE_FLAGS,
    PHASE_3_SERVICE_FLAGS,
    SecurityMonitoringStack,
)

CONFIG = load_config("dev")


def synth_env(env_name: str, prefix: str) -> dict:
    """Build and synth every stack for one environment.

    The single place the test app context is configured, so a test can never
    synthesize under different assumptions than the rest of the suite.
    """
    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    stacks = build_app(app, load_config(env_name), prefix)
    app.synth()
    return stacks


@pytest.fixture(scope="module")
def stack_constructs() -> dict:
    """All stacks built once; the construct tree can't change after first synth."""
    return synth_env("dev", "Test")


@pytest.fixture(scope="module")
def stacks(stack_constructs) -> dict:
    return {name: Template.from_stack(stack) for name, stack in stack_constructs.items()}


def test_buckets_are_locked_down(stacks):
    template = stacks["data"]
    template.resource_count_is("AWS::S3::Bucket", 3)
    template.all_resources_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": Match.object_like(
                {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True,
                }
            ),
            "BucketEncryption": Match.any_value(),
            "VersioningConfiguration": {"Status": "Enabled"},
        },
    )
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {"Budget": Match.object_like({"BudgetLimit": {"Amount": CONFIG["budget_usd"]}})},
    )
    template.resource_count_is("AWS::S3::BucketPolicy", 3)
    template.all_resources_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Effect": "Deny",
                                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                                }
                            )
                        ]
                    )
                }
            )
        },
    )

    document = template.to_json()
    buckets = [
        resource["Properties"]
        for resource in document["Resources"].values()
        if resource["Type"] == "AWS::S3::Bucket"
    ]
    assert {bucket["LoggingConfiguration"]["LogFilePrefix"] for bucket in buckets} == {
        "raw/",
        "curated/",
        "artifacts/",
    }
    assert all(
        set(bucket["LoggingConfiguration"]["DestinationBucketName"]) == {"Fn::ImportValue"}
        and bucket["LoggingConfiguration"]["DestinationBucketName"]["Fn::ImportValue"].startswith(
            "Test-Security:"
        )
        for bucket in buckets
    )

    budget = next(
        resource["Properties"]
        for resource in document["Resources"].values()
        if resource["Type"] == "AWS::Budgets::Budget"
    )
    assert "NotificationsWithSubscribers" not in budget

    notification_resources = [
        resource for resource in document["Resources"].values() if resource["Type"] == "Custom::AWS"
    ]
    assert len(notification_resources) == 3
    rendered_calls = json.dumps(notification_resources, sort_keys=True)
    for threshold in (50, 80, 100):
        assert f'\\"Threshold\\":{threshold}' in rendered_calls
        assert f"actual-greater-than-{threshold}-percent" in rendered_calls
    assert rendered_calls.count('\\"action\\":\\"createNotification\\"') == 3
    assert rendered_calls.count('\\"action\\":\\"deleteNotification\\"') == 3
    assert rendered_calls.count('\\"ComparisonOperator\\":\\"GREATER_THAN\\"') == 6
    assert rendered_calls.count('\\"NotificationType\\":\\"ACTUAL\\"') == 6
    assert rendered_calls.count('\\"ThresholdType\\":\\"PERCENTAGE\\"') == 6
    assert rendered_calls.count('\\"SubscriptionType\\":\\"SNS\\"') == 3
    assert rendered_calls.count("Test-Security:") == 3

    provider_policies = [
        resource["Properties"]["PolicyDocument"]
        for resource in document["Resources"].values()
        if resource["Type"] == "AWS::IAM::Policy"
        and "BudgetAlert" in resource["Properties"]["PolicyName"]
    ]
    assert len(provider_policies) == 3
    for policy in provider_policies:
        statements = policy["Statement"]
        assert len(statements) == 1
        assert statements[0]["Action"] == "budgets:ModifyBudget"
        assert statements[0]["Effect"] == "Allow"


def test_security_audit_foundation(stacks):
    template = stacks["security"]
    document = template.to_json()

    assert document["Parameters"]["SecurityAlertEmail"] == {
        "Type": "String",
        "Description": "Email endpoint for dev security and budget alerts",
    }
    assert set(document["Outputs"]) >= {
        "TrailName",
        "AuditBucketName",
        "AccessLogBucketName",
        "AuditLogGroupName",
        "SecurityAlertsTopicArn",
        "AuditKeyAlias",
    }

    template.resource_count_is("AWS::KMS::Key", 1)
    template.has_resource_properties(
        "AWS::KMS::Key",
        {
            "EnableKeyRotation": True,
            "KeyPolicy": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Sid": "AllowCloudTrailAuditEncryption",
                                    "Principal": {"Service": "cloudtrail.amazonaws.com"},
                                    "Action": ["kms:GenerateDataKey*", "kms:DescribeKey"],
                                    "Condition": Match.object_like(
                                        {
                                            "StringEquals": Match.object_like(
                                                {"aws:SourceArn": Match.any_value()}
                                            ),
                                            "StringLike": Match.object_like(
                                                {
                                                    "kms:EncryptionContext:aws:cloudtrail:arn": (
                                                        Match.any_value()
                                                    )
                                                }
                                            ),
                                        }
                                    ),
                                }
                            ),
                            Match.object_like(
                                {
                                    "Sid": "AllowRegionalCloudWatchLogsEncryption",
                                    "Principal": {"Service": Match.any_value()},
                                }
                            ),
                            Match.object_like({"Sid": "AllowCloudWatchEncryptedAlerts"}),
                            Match.object_like({"Sid": "AllowBudgetsEncryptedAlerts"}),
                        ]
                    )
                }
            ),
        },
    )
    template.has_resource_properties("AWS::KMS::Alias", {"AliasName": "alias/mlops-dev-audit"})

    template.resource_count_is("AWS::S3::Bucket", 2)
    template.all_resources_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": Match.object_like(
                {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True,
                }
            ),
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
            "VersioningConfiguration": {"Status": "Enabled"},
        },
    )
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            }
        },
    )
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": Match.object_like(
                {
                    "ServerSideEncryptionConfiguration": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "BucketKeyEnabled": True,
                                    "ServerSideEncryptionByDefault": Match.object_like(
                                        {"SSEAlgorithm": "aws:kms"}
                                    ),
                                }
                            )
                        ]
                    )
                }
            ),
            "LoggingConfiguration": Match.object_like({"LogFilePrefix": "cloudtrail/"}),
        },
    )

    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {
            "KmsKeyId": Match.any_value(),
            "LogGroupName": "/aws/cloudtrail/mlops-dev-audit",
            "RetentionInDays": 90,
        },
    )
    template.has_resource_properties(
        "AWS::CloudTrail::Trail",
        {
            "EnableLogFileValidation": True,
            "EventSelectors": [{"IncludeManagementEvents": True, "ReadWriteType": "All"}],
            "IncludeGlobalServiceEvents": True,
            "IsLogging": True,
            "IsMultiRegionTrail": True,
            "IsOrganizationTrail": False,
            "KMSKeyId": Match.any_value(),
            "TrailName": "mlops-dev-audit",
        },
    )

    template.has_resource_properties(
        "AWS::SNS::Topic",
        {
            "KmsMasterKeyId": Match.any_value(),
            "TopicName": "mlops-dev-security-alerts",
        },
    )
    template.has_resource_properties(
        "AWS::SNS::Subscription",
        {
            "Endpoint": {"Ref": "SecurityAlertEmail"},
            "Protocol": "email",
        },
    )
    template.has_resource_properties(
        "AWS::SNS::TopicPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like({"Sid": "AllowCloudWatchAlarmPublish"}),
                            Match.object_like({"Sid": "AllowBudgetsPublish"}),
                        ]
                    )
                }
            )
        },
    )
    template.resource_count_is("AWS::Logs::MetricFilter", 6)
    template.resource_count_is("AWS::CloudWatch::Alarm", 6)

    resources = document["Resources"]
    retained_types = {"AWS::KMS::Key", "AWS::S3::Bucket", "AWS::Logs::LogGroup"}
    for resource in resources.values():
        if resource["Type"] in retained_types:
            assert resource["DeletionPolicy"] == "Retain"
            assert resource["UpdateReplacePolicy"] == "Retain"

    trail_properties = next(
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::CloudTrail::Trail"
    )
    event_selector = trail_properties["EventSelectors"][0]
    assert "DataResources" not in event_selector
    assert "InsightSelectors" not in trail_properties
    assert ":log-group:/aws/cloudtrail/mlops-dev-audit:*" in json.dumps(
        trail_properties["CloudWatchLogsLogGroupArn"]
    )

    role_policy = next(
        resource["Properties"]["PolicyDocument"]
        for resource in resources.values()
        if resource["Type"] == "AWS::IAM::Policy"
    )
    assert ":log-group:/aws/cloudtrail/mlops-dev-audit:log-stream:*" in json.dumps(role_policy)

    key_policy = next(
        resource["Properties"]["KeyPolicy"]
        for resource in resources.values()
        if resource["Type"] == "AWS::KMS::Key"
    )
    service_sids = {
        statement["Sid"]
        for statement in key_policy["Statement"]
        if "Service" in statement.get("Principal", {})
    }
    assert service_sids == {
        "AllowCloudTrailAuditEncryption",
        "AllowRegionalCloudWatchLogsEncryption",
        "AllowCloudWatchEncryptedAlerts",
        "AllowBudgetsEncryptedAlerts",
    }

    topic_policy = next(
        resource["Properties"]["PolicyDocument"]
        for resource in resources.values()
        if resource["Type"] == "AWS::SNS::TopicPolicy"
    )
    service_statements = {
        statement["Sid"]: statement
        for statement in topic_policy["Statement"]
        if statement["Sid"] in {"AllowCloudWatchAlarmPublish", "AllowBudgetsPublish"}
    }
    assert set(service_statements) == {"AllowCloudWatchAlarmPublish", "AllowBudgetsPublish"}
    for statement in service_statements.values():
        assert "aws:SourceAccount" in statement["Condition"]["StringEquals"]
        assert "aws:SourceArn" in statement["Condition"]["ArnLike"]

    access_log_policy = next(
        resource["Properties"]["PolicyDocument"]
        for logical_id, resource in resources.items()
        if logical_id.startswith("AccessLogBucketPolicy")
    )
    data_log_statement = next(
        statement
        for statement in access_log_policy["Statement"]
        if statement.get("Sid") == "AllowDataBucketAccessLogs"
    )
    assert data_log_statement["Principal"] == {"Service": "logging.s3.amazonaws.com"}
    assert data_log_statement["Action"] == "s3:PutObject"
    assert len(data_log_statement["Resource"]) == 3
    assert set(data_log_statement["Condition"]) == {"ArnLike", "StringEquals"}
    assert data_log_statement["Condition"]["StringEquals"] == {
        "aws:SourceAccount": {"Ref": "AWS::AccountId"}
    }
    assert "mlops-dev-data-*" in json.dumps(
        data_log_statement["Condition"]["ArnLike"]["aws:SourceArn"]
    )

    # TLS-only: every bucket policy denies insecure transport
    template.all_resources_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Effect": "Deny",
                                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                                }
                            )
                        ]
                    )
                }
            )
        },
    )


def test_security_detection_patterns_and_alarms_are_exact(stacks):
    document = stacks["security"].to_json()
    resources = document["Resources"]
    expected_patterns = {
        '{$.userIdentity.type="Root" && $.userIdentity.invokedBy NOT EXISTS && '
        '$.eventType !="AwsServiceEvent"}',
        '{($.errorCode="*UnauthorizedOperation") || ($.errorCode="AccessDenied*")}',
        "{($.eventSource=iam.amazonaws.com) && "
        "(($.eventName=DeleteGroupPolicy) || ($.eventName=DeleteRolePolicy) || "
        "($.eventName=DeleteUserPolicy) || ($.eventName=PutGroupPolicy) || "
        "($.eventName=PutRolePolicy) || ($.eventName=PutUserPolicy) || "
        "($.eventName=CreatePolicy) || ($.eventName=DeletePolicy) || "
        "($.eventName=CreatePolicyVersion) || ($.eventName=DeletePolicyVersion) || "
        "($.eventName=AttachRolePolicy) || ($.eventName=DetachRolePolicy) || "
        "($.eventName=AttachUserPolicy) || ($.eventName=DetachUserPolicy) || "
        "($.eventName=AttachGroupPolicy) || ($.eventName=DetachGroupPolicy))}",
        "{($.eventName=CreateTrail) || ($.eventName=UpdateTrail) || "
        "($.eventName=DeleteTrail) || ($.eventName=StartLogging) || "
        "($.eventName=StopLogging)}",
        "{($.eventSource=kms.amazonaws.com) && (($.eventName=DisableKey) || "
        "($.eventName=ScheduleKeyDeletion))}",
        "{($.eventSource=s3.amazonaws.com) && (($.eventName=PutBucketAcl) || "
        "($.eventName=PutBucketPolicy) || ($.eventName=PutBucketCors) || "
        "($.eventName=PutBucketLifecycle) || ($.eventName=PutBucketReplication) || "
        "($.eventName=DeleteBucketPolicy) || ($.eventName=DeleteBucketCors) || "
        "($.eventName=DeleteBucketLifecycle) || ($.eventName=DeleteBucketReplication))}",
    }

    metric_filters = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::Logs::MetricFilter"
    ]
    assert {metric_filter["FilterPattern"] for metric_filter in metric_filters} == (
        expected_patterns
    )
    for metric_filter in metric_filters:
        assert metric_filter["LogGroupName"] == {"Ref": "AuditLogGroup6D13791A"}
        assert metric_filter["MetricTransformations"] == [
            {
                "DefaultValue": 0,
                "MetricName": metric_filter["MetricTransformations"][0]["MetricName"],
                "MetricNamespace": "MLOps/Security",
                "MetricValue": "1",
            }
        ]

    alarms = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
    ]
    topic_ref = {"Ref": "SecurityAlertsTopic1CE4D100"}
    assert len(alarms) == 6
    # Phase 2E (issue 10): only unauthorized-api-calls requires a sustained
    # burst (3 of 3 five-minute datapoints); the other five page on the
    # first event and must render no DatapointsToAlarm property at all.
    expected_evaluation = {
        "root-user-activity": (1, None),
        "unauthorized-api-calls": (3, 3),
        "iam-policy-changes": (1, None),
        "cloudtrail-configuration-changes": (1, None),
        "kms-key-disable-or-deletion": (1, None),
        "s3-bucket-policy-changes": (1, None),
    }
    for alarm in alarms:
        slug = alarm["AlarmName"].split("-security-", 1)[1]
        periods, datapoints = expected_evaluation[slug]
        assert alarm["ActionsEnabled"] is True
        assert alarm["AlarmActions"] == [topic_ref]
        assert alarm["ComparisonOperator"] == "GreaterThanOrEqualToThreshold"
        assert alarm["EvaluationPeriods"] == periods
        assert alarm.get("DatapointsToAlarm") == datapoints
        assert alarm["Namespace"] == "MLOps/Security"
        assert alarm["Period"] == 300
        assert alarm["Statistic"] == "Sum"
        assert alarm["Threshold"] == 1
        assert alarm["TreatMissingData"] == "notBreaching"
    assert {alarm["AlarmName"].split("-security-", 1)[1] for alarm in alarms} == set(
        expected_evaluation
    )


def test_ingestion_wiring(stacks):
    template = stacks["ingestion"]
    # queue + DLQ, with redrive between them
    template.resource_count_is("AWS::SQS::Queue", 2)
    template.has_resource_properties(
        "AWS::SQS::Queue",
        {"RedrivePolicy": Match.object_like({"maxReceiveCount": 3})},
    )
    template.has_resource_properties(
        "AWS::Events::Rule",
        {"EventPattern": Match.object_like({"source": ["aws.s3"]})},
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "src.ingestion.validate_handler.handler",
            "Runtime": "python3.12",
            "Environment": {"Variables": Match.object_like({"CURATED_BUCKET": Match.any_value()})},
        },
    )


def test_serving_endpoint_auth_and_least_privilege(stacks):
    template = stacks["serving"]

    # the public method requires an API key
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {"HttpMethod": "POST", "ApiKeyRequired": True},
    )
    # proxy role can only invoke the one endpoint
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "sagemaker:InvokeEndpoint",
                                    # arn is an Fn::Join over region/account tokens
                                    "Resource": {
                                        "Fn::Join": Match.array_with(
                                            [
                                                Match.array_with(
                                                    [
                                                        Match.string_like_regexp(
                                                            f".*endpoint/{CONFIG['endpoint_name']}"
                                                        )
                                                    ]
                                                )
                                            ]
                                        )
                                    },
                                }
                            )
                        ]
                    )
                }
            )
        },
    )
    # approval events from our package group trigger the deploy Lambda
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": Match.object_like(
                {
                    "detail": Match.object_like(
                        {"ModelPackageGroupName": [CONFIG["model_package_group"]]}
                    )
                }
            )
        },
    )


def test_monitoring_drift_loop_wiring(stacks):
    template = stacks["monitoring"]

    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": Match.object_like(
                {
                    "detail": Match.object_like(
                        {"MonitoringExecutionStatus": ["CompletedWithViolations"]}
                    )
                }
            )
        },
    )
    # retrain Lambda may only start the one pipeline
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "sagemaker:StartPipelineExecution",
                                    # arn is an Fn::Join over region/account tokens
                                    "Resource": {
                                        "Fn::Join": Match.array_with(
                                            [
                                                Match.array_with(
                                                    [
                                                        Match.string_like_regexp(
                                                            f".*pipeline/{CONFIG['pipeline_name']}"
                                                        )
                                                    ]
                                                )
                                            ]
                                        )
                                    },
                                }
                            )
                        ]
                    )
                }
            )
        },
    )
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)
    template.resource_count_is("AWS::CloudWatch::Alarm", 1)

    # An alarm with no action only changes colour in the console. This one
    # must page the same operator topic as the Phase 2 security alarms.
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": f"mlops-{CONFIG['env_name']}-endpoint-5xx",
            "MetricName": "Invocation5XXErrors",
            "AlarmActions": [{"Fn::ImportValue": Match.any_value()}],
        },
    )


def test_registry_and_training(stacks):
    stacks["registry"].has_resource_properties(
        "AWS::SageMaker::ModelPackageGroup",
        {"ModelPackageGroupName": CONFIG["model_package_group"]},
    )


def _registry_group_name(stacks: dict) -> str:
    """The physical model package group name one environment synthesizes."""
    resources = Template.from_stack(stacks["registry"]).find_resources(
        "AWS::SageMaker::ModelPackageGroup"
    )
    assert len(resources) == 1
    name: str = next(iter(resources.values()))["Properties"]["ModelPackageGroupName"]
    return name


def _approval_rule_patterns(stacks: dict) -> list[dict]:
    """Every registry-approval EventBridge pattern in one environment's serving stack."""
    rules = Template.from_stack(stacks["serving"]).find_resources("AWS::Events::Rule")
    return [
        rule["Properties"]["EventPattern"]
        for rule in rules.values()
        if "ModelPackageGroupName" in json.dumps(rule["Properties"]["EventPattern"])
    ]


def test_environments_never_share_a_model_package_group():
    """Two environments must not resolve to the same physical registry group.

    No stack sets `env=cdk.Environment`, so every environment deploys into
    whatever account the credentials point at — in practice the same one.
    A shared group name means the second RegistryStack cannot create the
    group at all, and both ServingStacks' approval rules match identical
    events: dev auto-approves challengers, so a dev retrain would deploy
    itself onto the prod endpoint.
    """
    environments = {env: synth_env(env, stack_prefix(env)) for env in ("dev", "prod")}

    group_names = {env: _registry_group_name(stacks) for env, stacks in environments.items()}
    assert len(set(group_names.values())) == len(group_names), group_names

    # The approval rules key off the group name, so distinct names must also
    # leave no two environments listening to the same event.
    patterns = [
        json.dumps(pattern, sort_keys=True)
        for stacks in environments.values()
        for pattern in _approval_rule_patterns(stacks)
    ]
    assert len(patterns) == len(environments)
    assert len(set(patterns)) == len(patterns), patterns


def test_security_acknowledgements_are_exact_and_expiring(stack_constructs):
    """Every accepted finding is attached to one real construct and a future phase."""
    acknowledgements = resolved_acknowledgements(CONFIG["env_name"], "Test")
    assert acknowledgements
    for acknowledgement in acknowledgements:
        stack = stack_constructs[acknowledgement.stack]
        expected_path = f"{stack.node.path}/{acknowledgement.construct_path}"
        matches = [node for node in stack.node.find_all() if node.node.path == expected_path]
        assert len(matches) == 1, expected_path
        assert "Phase " in acknowledgement.reason
        target = matches[0].node.default_child or matches[0]
        finding_id = acknowledgement.finding_id.removeprefix("AwsSolutions::")
        metadata_key = f"annotation::{finding_id}"
        assert any(
            entry.type == cdk.Validations.ACKNOWLEDGED_RULES_METADATA_KEY
            and entry.data.get(metadata_key) == acknowledgement.reason
            for entry in target.node.metadata
        ), metadata_key


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_every_environment_builds_under_its_real_prefix(env_name):
    """Both environments must build under the stack prefix the app really uses.

    `prod` was unbuildable because an acknowledgement hardcoded dev's stage
    name, so the CI promotion path could never have reached a prod deploy.

    Scope: this covers `construct_path`, which `_construct_at` fails on
    loudly. It does NOT cover `finding_id` — cdk-nag reports unacknowledged
    findings through the CLI validation report, and in-process `app.synth()`
    returns cleanly even when five of them are wrong. `make synth-all` is the
    gate for those, which is why CI must synth both environments.
    """
    synth_env(env_name, stack_prefix(env_name))


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_acknowledgements_leave_no_unresolved_tokens(env_name):
    """A mistyped token would silently stop matching instead of failing loudly."""
    for acknowledgement in resolved_acknowledgements(env_name, stack_prefix(env_name)):
        assert "{" not in acknowledgement.construct_path, acknowledgement
        assert "{" not in acknowledgement.finding_id, acknowledgement


def test_security_monitoring_enables_only_phase_3a_and_3e(stacks):
    """Dev enables the analyzer and account BPA; 3B GuardDuty is deferred (Free plan)."""
    services = CONFIG["security"]["services"]
    assert services["access_analyzer"] is True
    assert services["account_bpa"] is True
    assert services["guardduty"] is False
    assert {name for name, enabled in services.items() if enabled} == {
        "access_analyzer",
        "account_bpa",
    }

    template = stacks["security_monitoring"]
    template.resource_count_is("AWS::AccessAnalyzer::Analyzer", 1)
    template.has_resource_properties(
        "AWS::AccessAnalyzer::Analyzer",
        {
            "AnalyzerName": "mlops-dev-external-access",
            "Type": "ACCOUNT",
        },
    )
    analyzer_properties = next(
        resource["Properties"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::AccessAnalyzer::Analyzer"
    )
    assert set(analyzer_properties) == {"AnalyzerName", "Tags", "Type"}
    assert {tag["Key"]: tag["Value"] for tag in analyzer_properties["Tags"]} == {
        "Project": "aws-mlops-platform",
        "Environment": "dev",
        "SecurityPhase": "3A",
    }

    guardduty_types = {
        resource["Type"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"].startswith("AWS::GuardDuty::")
    }
    assert guardduty_types == set()


def test_guardduty_detector_contract_stays_locked_for_deferred_phase_3b():
    """The flag-gated detector keeps its exact Phase 3B shape for the future retry."""
    config = load_config("dev")
    config["security"]["services"]["guardduty"] = True

    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    stack = SecurityMonitoringStack(
        app,
        "Test-SecurityMonitoring-GuardDutyRetry",
        alert_topic=None,
        access_log_bucket=None,
        audit_key=None,
        config=config,
    )
    app.synth()
    template = Template.from_stack(stack)

    template.resource_count_is("AWS::GuardDuty::Detector", 1)
    detector_properties = next(
        resource["Properties"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::GuardDuty::Detector"
    )
    assert set(detector_properties) == {
        "Enable",
        "Features",
        "FindingPublishingFrequency",
        "Tags",
    }
    assert detector_properties["Enable"] is True
    assert detector_properties["FindingPublishingFrequency"] == "FIFTEEN_MINUTES"
    assert detector_properties["Features"] == [
        {"Name": name, "Status": "DISABLED"}
        for name in (
            "S3_DATA_EVENTS",
            "EKS_AUDIT_LOGS",
            "EBS_MALWARE_PROTECTION",
            "RDS_LOGIN_EVENTS",
            "LAMBDA_NETWORK_LOGS",
            "AI_ANALYST",
        )
    ]
    assert {tag["Key"]: tag["Value"] for tag in detector_properties["Tags"]} == {
        "Project": "aws-mlops-platform",
        "Environment": "dev",
        "SecurityPhase": "3B",
    }

    guardduty_types = {
        resource["Type"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"].startswith("AWS::GuardDuty::")
    }
    assert guardduty_types == {"AWS::GuardDuty::Detector"}


def _account_bpa_call(template, key):
    """Rebuild one SDK call from the custom resource, resolving the account Ref."""
    resource = next(
        value
        for value in template.to_json()["Resources"].values()
        if value["Type"] == "Custom::AWS"
    )
    parts = resource["Properties"][key]["Fn::Join"][1]
    for part in parts:
        # The only intrinsic in the payload must be the account pseudo-parameter;
        # a literal account id must never reach the template.
        assert isinstance(part, str) or part == {"Ref": "AWS::AccountId"}
    rendered = "".join(part if isinstance(part, str) else "<ACCOUNT>" for part in parts)
    return json.loads(rendered)


def test_account_bpa_blocks_all_four_public_access_routes(stacks):
    """Phase 3E sets every account-level switch and reverts to no config on delete."""
    template = stacks["security_monitoring"]
    template.resource_count_is("Custom::AWS", 1)

    # Create and Update must be identical, or a later settings change would
    # synthesize without ever reaching the account.
    for key in ("Create", "Update"):
        call = _account_bpa_call(template, key)
        assert call["service"] == "S3Control"
        assert call["action"] == "putPublicAccessBlock"
        assert call["parameters"]["AccountId"] == "<ACCOUNT>"
        assert call["parameters"]["PublicAccessBlockConfiguration"] == {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        }
        assert call["physicalResourceId"] == {"id": "mlops-dev-account-bpa"}

    delete = _account_bpa_call(template, "Delete")
    assert delete["service"] == "S3Control"
    assert delete["action"] == "deletePublicAccessBlock"
    assert delete["parameters"] == {"AccountId": "<ACCOUNT>"}

    custom_resource = next(
        value
        for value in template.to_json()["Resources"].values()
        if value["Type"] == "Custom::AWS"
    )
    assert custom_resource["Properties"]["InstallLatestAwsSdk"] is False

    # The provider role must gain nothing beyond the three account-level actions.
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": [
                        {
                            "Action": [
                                "s3:PutAccountPublicAccessBlock",
                                "s3:DeleteAccountPublicAccessBlock",
                            ],
                            "Effect": "Allow",
                            "Resource": "*",
                        }
                    ]
                }
            )
        },
    )


@pytest.mark.parametrize(
    "flag",
    sorted(set(PHASE_3_SERVICE_FLAGS) - IMPLEMENTED_SERVICE_FLAGS),
)
def test_enabling_an_unimplemented_service_flag_fails_loudly(flag):
    """A flag with no CDK behind it must raise, not deploy nothing silently.

    Without this, flipping e.g. config_recorder to true would synth and deploy
    cleanly while creating no resource at all -- the security service would
    look enabled and not be.
    """
    config = load_config("dev")
    config["security"]["services"][flag] = True

    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    with pytest.raises(ValueError, match="no stack implementation") as excinfo:
        SecurityMonitoringStack(
            app,
            # Stack ids must match /^[A-Za-z][A-Za-z0-9-]*$/, so drop the
            # underscores rather than letting CDK reject the name first.
            f"Test-SecurityMonitoring-Unimplemented-{flag.replace('_', '-')}",
            alert_topic=None,
            access_log_bucket=None,
            audit_key=None,
            config=config,
        )
    assert flag in str(excinfo.value)


def test_implemented_service_flags_are_a_subset_of_the_declared_contract():
    """Catches a typo in IMPLEMENTED_SERVICE_FLAGS that would disable the guard."""
    assert IMPLEMENTED_SERVICE_FLAGS <= set(PHASE_3_SERVICE_FLAGS)


def test_prod_security_monitoring_stays_a_disabled_shell():
    """Production remains unchanged until its separately approved rollout."""
    config = load_config("prod")
    assert set(config["security"]["services"].values()) == {False}

    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    stack = SecurityMonitoringStack(
        app,
        "Test-Prod-SecurityMonitoring",
        alert_topic=None,
        access_log_bucket=None,
        audit_key=None,
        config=config,
    )
    app.synth()
    resources = Template.from_stack(stack).to_json().get("Resources", {})
    assert set(resources) <= {"CDKMetadata"}


def test_disabling_a_phase_3_flag_still_synthesizes():
    """Turning a sub-phase back off must not break synthesis, or rollback is stuck.

    Acknowledgements are matched to real constructs, so one naming a flag-gated
    Phase 3 construct fails synthesis the moment that flag goes false -- which is
    exactly the rollback path. Without requires_service, flipping account_bpa
    back off would leave the environment unable to synthesize the revert.
    """
    config = load_config("dev")
    config["security"]["services"]["account_bpa"] = False

    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    stacks = build_app(app, config, "Test-Rollback")
    app.synth()

    resources = Template.from_stack(stacks["security_monitoring"]).to_json()["Resources"]
    assert "Custom::AWS" not in {value["Type"] for value in resources.values()}


def test_broad_sagemaker_managed_policy_baseline_has_not_grown(stacks):
    """Phase 5 owns these two known roles; Phase 1 rejects a third attachment."""
    roles = []
    for stack_name, template in stacks.items():
        for logical_id, resource in template.to_json().get("Resources", {}).items():
            if resource.get("Type") != "AWS::IAM::Role":
                continue
            policies = resource.get("Properties", {}).get("ManagedPolicyArns", [])
            if any("AmazonSageMakerFullAccess" in str(policy) for policy in policies):
                roles.append((stack_name, logical_id))

    assert roles == [
        ("training", "PipelineExecutionRoleF9B1F2D0"),
        ("serving", "ModelExecutionRole3247A550"),
    ]


def test_literal_wildcard_resource_baseline_has_not_grown(stacks):
    """Reject new Resource '*' statements while known generated debt awaits Phases 5 and 7."""
    wildcard_policies = []
    for stack_name, template in stacks.items():
        for logical_id, resource in template.to_json().get("Resources", {}).items():
            if resource.get("Type") != "AWS::IAM::Policy":
                continue
            statements = resource["Properties"]["PolicyDocument"]["Statement"]
            if any(statement.get("Resource") == "*" for statement in statements):
                wildcard_policies.append((stack_name, logical_id))

    assert wildcard_policies == [
        # Phase 3E: the s3:*AccountPublicAccessBlock actions are account-level
        # and AWS accepts only "*" as their resource.
        ("security_monitoring", "AccountPublicAccessBlockCustomResourcePolicy3665E1EC"),
        (
            "ingestion",
            "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8aServiceRoleDefaultPolicyADDA7DEB",
        ),
        ("serving", "DeployFnServiceRoleDefaultPolicy7D43372B"),
        (
            "serving",
            "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8aServiceRoleDefaultPolicyADDA7DEB",
        ),
        (
            "monitoring",
            "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8aServiceRoleDefaultPolicyADDA7DEB",
        ),
    ]


def test_iam_policy_baseline_has_not_changed(stacks):
    """Any role or policy change requires an explicit Phase 1 baseline review."""
    fingerprints = {}
    for stack_name, template in stacks.items():
        iam_resources = {
            logical_id: resource
            for logical_id, resource in template.to_json().get("Resources", {}).items()
            if resource.get("Type") in {"AWS::IAM::Policy", "AWS::IAM::Role"}
        }
        fingerprints[stack_name] = hashlib.sha256(
            json.dumps(iam_resources, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    assert fingerprints == {
        "security": "9925908b0ff292a103399b71a26a17717dccd31daf542493a0723645d056dd24",
        # Phase 3E added the account-BPA custom resource provider role (basic
        # Lambda execution only) and its three-action policy. Nothing else.
        "security_monitoring": "9e5660c56071f5d663e8b941a28ab57830ce3afb9e0852a142bd7e879919d496",
        "data": "2939699d4ec8219e7af89d0bc03ac579b55c02c28f638d251fe25296fd6b67c1",
        "ingestion": "bfa13d3f2b0fa9b7ae49f81dfd29907f683ecca6347e1cc4327834f094702f41",
        "registry": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        "training": "d5cc3390088645f797b05769e35bec78b3073ace00e81b8cfff2ecd42ad50b10",
        "serving": "c3f8089244512e2866a5648c556a434b6d77403d5b8340f3de0e44b388d22989",
        "monitoring": "10990e799b97ab9b8f63102cf5e8363c2de9dd883cf36d08f6f3f0aa0a980c3c",
    }

    stacks["training"].has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [Match.object_like({"Principal": {"Service": "sagemaker.amazonaws.com"}})]
                    )
                }
            )
        },
    )
