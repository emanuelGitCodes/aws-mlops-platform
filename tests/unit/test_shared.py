"""Cross-stack helper defaults, asserted on the synthesized templates."""

from tests.unit.conftest import CONFIG

# List the CDK provider Lambdas that do not use `platform_lambda`.
# These functions use default `/aws/lambda/<name>` log groups.
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
    """Require an explicit retained log group for each platform Lambda."""
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
        # Delete application log groups with their functions.
        assert group["DeletionPolicy"] == "Delete"


def test_no_stack_still_builds_a_log_retention_provider(stacks):
    """Keep the CDK log-retention provider out of every stack."""
    for stack_name, template in stacks.items():
        resources = template.to_json().get("Resources", {}).values()
        assert "Custom::LogRetention" not in {r["Type"] for r in resources}, stack_name
