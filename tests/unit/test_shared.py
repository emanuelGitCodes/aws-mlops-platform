"""Cross-stack helper defaults, asserted on the synthesized templates."""

from tests.unit.conftest import CONFIG

# Lambdas CDK generates for its own providers. They are not built by
# `platform_lambda`, so they keep the default `/aws/lambda/<name>` group with
# never-expiring retention. Listed rather than skipped, so a new provider has
# to be looked at instead of quietly joining the exempt set.
PROVIDER_FUNCTIONS = {
    ("data", "BucketNotificationsHandler050a0587b7544547bf325f094a3db8347ECC3691"),
    ("data", "AWS679f53fac002430cb0da5b7982bd22872D164C4C"),
    ("security_monitoring", "AWS679f53fac002430cb0da5b7982bd22872D164C4C"),
}


def _functions(stacks: dict) -> dict:
    return {
        (stack_name, logical_id): resource
        for stack_name, template in stacks.items()
        for logical_id, resource in template.to_json().get("Resources", {}).items()
        if resource.get("Type") == "AWS::Lambda::Function"
    }


def test_platform_lambdas_own_their_log_group(stacks):
    """Every platform Lambda logs to a group this repo controls the retention of.

    `platform_lambda` used the deprecated `log_retention=`, which sent the group
    to a CDK-generated provider Lambda instead. Dropping the prop without a
    replacement is silent: the function still logs, to a default group that
    never expires and that no config value governs.
    """
    owned = {
        key: resource
        for key, resource in _functions(stacks).items()
        if key not in PROVIDER_FUNCTIONS
    }
    assert owned, "no platform Lambdas found"

    for (stack_name, logical_id), function in owned.items():
        logging_config = function["Properties"].get("LoggingConfig")
        assert logging_config, f"{stack_name}/{logical_id} has no explicit log group"
        group_id = logging_config["LogGroup"]["Ref"]
        group = stacks[stack_name].to_json()["Resources"][group_id]
        assert group["Type"] == "AWS::Logs::LogGroup"
        assert group["Properties"]["RetentionInDays"] == CONFIG["log_retention_days"]
        # Application logs, unlike the Security stack's retained audit group.
        assert group["DeletionPolicy"] == "Delete"


def test_no_stack_still_builds_a_log_retention_provider(stacks):
    """The provider is what carried six acknowledgements and three `Resource: *`
    policies; its return would reopen all of them."""
    for stack_name, template in stacks.items():
        resources = template.to_json().get("Resources", {}).values()
        assert "Custom::LogRetention" not in {r["Type"] for r in resources}, stack_name
