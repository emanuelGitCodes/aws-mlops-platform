"""Cross-stack helper defaults, asserted on the synthesized templates."""

from tests.unit.conftest import CONFIG

# Lambdas CDK generates for its own providers. `platform_lambda` does not build
# them, so they keep the default `/aws/lambda/<name>` group, which never
# expires. List them by name. A new provider must be reviewed before it joins
# this set.
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
    """Every platform Lambda logs to a group this repo sets the retention on.

    A function with no explicit group still logs, into a default group that
    never expires and that no config value governs. That failure is silent.
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
        # These are application logs. The Security stack audit group is
        # retained instead.
        assert group["DeletionPolicy"] == "Delete"


def test_no_stack_still_builds_a_log_retention_provider(stacks):
    """The provider carries six acknowledgements and three `Resource: *`
    policies. Its return reopens all of them."""
    for stack_name, template in stacks.items():
        resources = template.to_json().get("Resources", {}).values()
        assert "Custom::LogRetention" not in {r["Type"] for r in resources}, stack_name
