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
    # Exactly one: AWS Budgets is account-scoped and dev and prod share an
    # account, so a second budget anywhere re-measures the same dollars.
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
    """AWS Budgets is account-scoped and both environments share one account.

    A budget in each environment does not scope either one's spend: both
    re-measure the whole account and alarm on the same dollars at every
    threshold. Only the environment whose `account_budget` flag is true may
    build one.
    """
    prod_config = load_config("prod")
    assert prod_config["security"]["account_budget"] is False, (
        "prod must not own the account budget while dev does"
    )

    prod = Template.from_stack(synth_env("prod", "Test-Prod-Budget")["data"])
    prod.resource_count_is("AWS::Budgets::Budget", 0)
    # The notification provider goes with it, or its acknowledgement would
    # match no construct and fail prod synthesis.
    prod.resource_count_is("Custom::AWS", 0)


def test_exactly_one_environment_owns_the_account_budget():
    """The invariant itself, not just today's two values.

    Nothing in CDK can see both environments at once -- each synthesis loads one
    config -- so this is the only place the "exactly one" rule is enforced.
    """
    owners = [env for env in ("dev", "prod") if load_config(env)["security"]["account_budget"]]
    assert owners == ["dev"], f"expected dev to be the sole budget owner, got {owners}"
