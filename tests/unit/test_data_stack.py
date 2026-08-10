"""Data stack: bucket hardening and the single account-wide budget."""

import json

from aws_cdk.assertions import Match, Template

from infra.app import load_config
from tests.unit.conftest import CONFIG, synth_env


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
    # Require one account-wide budget.
    template.resource_count_is("AWS::Budgets::Budget", 1)
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


def test_prod_creates_no_second_account_budget():
    """Prevent prod from creating a second account-wide budget."""
    prod_config = load_config("prod")
    assert prod_config["security"]["account_budget"] is False, (
        "prod must not own the account budget while dev does"
    )

    prod = Template.from_stack(synth_env("prod", "Test-Prod-Budget")["data"])
    prod.resource_count_is("AWS::Budgets::Budget", 0)
    # The notification provider exists only with the account budget.
    prod.resource_count_is("Custom::AWS", 0)


def test_exactly_one_environment_owns_the_account_budget():
    """Require exactly one account-budget owner across both configs."""
    owners = [env for env in ("dev", "prod") if load_config(env)["security"]["account_budget"]]
    assert owners == ["dev"], f"expected dev to be the sole budget owner, got {owners}"


def test_only_the_capture_prefix_expires(stacks):
    """Apply artifact expiration only to the capture prefix."""
    buckets = stacks["data"].find_resources("AWS::S3::Bucket")
    with_rules = {
        logical_id: bucket["Properties"]["LifecycleConfiguration"]["Rules"]
        for logical_id, bucket in buckets.items()
        if "LifecycleConfiguration" in bucket["Properties"]
    }

    # Require one expiration rule on the artifacts bucket.
    assert len(with_rules) == 1
    logical_id, rules = next(iter(with_rules.items()))
    assert logical_id.startswith("ArtifactsBucket")

    assert len(rules) == 1
    rule = rules[0]
    assert rule["Prefix"] == "capture/"
    assert rule["Status"] == "Enabled"
    assert rule["ExpirationInDays"] == CONFIG["capture_retention_days"]
    # Expire noncurrent capture versions after one day.
    assert rule["NoncurrentVersionExpiration"]["NoncurrentDays"] == 1


def test_the_baseline_and_model_artifacts_are_outside_the_expiring_prefix(stacks):
    """Keep model artifacts and the baseline outside the capture prefix."""
    from infra.stacks.shared import (
        BASELINE_KEY,
        CAPTURE_PREFIX,
        EVALUATION_REPORT_PREFIX,
        MODEL_ARTIFACT_PREFIX,
    )

    for path in (BASELINE_KEY, MODEL_ARTIFACT_PREFIX, EVALUATION_REPORT_PREFIX):
        assert not path.startswith(f"{CAPTURE_PREFIX}/")
