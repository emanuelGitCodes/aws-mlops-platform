"""Ingestion stack: queue, DLQ and validation wiring."""

from aws_cdk.assertions import Match

from tests.unit.conftest import CONFIG


def test_ingestion_wiring(stacks):
    template = stacks["ingestion"]
    # A queue and a DLQ, with redrive between them.
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


def _validate_policy(template):
    policies = [
        resource
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::IAM::Policy"
        and "ValidateFnServiceRole" in str(resource["Properties"]["Roles"])
    ]
    assert len(policies) == 1
    return policies[0]["Properties"]["PolicyDocument"]["Statement"]


def _actions(statement):
    actions = statement["Action"]
    return frozenset({actions} if isinstance(actions, str) else actions)


def _resources(statement):
    resources = statement["Resource"]
    return resources if isinstance(resources, list) else [resources]


def _has_curated_prefix(statement):
    resource = str(statement["Resource"])
    return "telco/*" in resource or "quarantine/*" in resource


def _find_statement(statements, actions):
    for statement in statements:
        if _actions(statement) == actions:
            return statement
    raise AssertionError(actions)


def test_validate_function_has_scoped_curated_object_access(stacks):
    statements = _validate_policy(stacks["ingestion"])
    curated_statements = []
    for statement in statements:
        if _has_curated_prefix(statement):
            curated_statements.append(statement)
    resources = []
    for statement in statements:
        resources.extend(_resources(statement))
    assert "*" not in resources
    put_actions = frozenset({"s3:PutObject"})
    delete_actions = frozenset({"s3:DeleteObject"})
    assert {_actions(statement) for statement in curated_statements} == {
        put_actions,
        delete_actions,
    }
    put_statement = _find_statement(curated_statements, put_actions)
    delete_statement = _find_statement(curated_statements, delete_actions)
    put_resources = {str(resource) for resource in _resources(put_statement)}
    delete_resources = {str(resource) for resource in _resources(delete_statement)}
    assert any("telco/*" in resource for resource in put_resources)
    assert any("quarantine/*" in resource for resource in put_resources)
    assert len(put_resources) == 2
    assert any("quarantine/*" in resource for resource in delete_resources)
    assert any("telco/*" in resource for resource in delete_resources)
    assert len(delete_resources) == 2


def test_ingestion_queues_require_tls(stacks):
    policies = [
        resource
        for resource in stacks["ingestion"].to_json()["Resources"].values()
        if resource["Type"] == "AWS::SQS::QueuePolicy"
    ]
    assert len(policies) == 2
    for policy in policies:
        statements = policy["Properties"]["PolicyDocument"]["Statement"]
        assert any(
            statement["Effect"] == "Deny"
            and statement["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}
            for statement in statements
        )


def test_a_failed_validation_pages_the_operator(stacks):
    """Ingestion runs unattended. Without the alarm a throwing handler is
    visible only as an absence of curated objects."""
    alarms = {
        resource["Properties"]["AlarmName"]: resource["Properties"]
        for resource in stacks["ingestion"].to_json()["Resources"].values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
    }
    env = CONFIG["env_name"]
    assert set(alarms) == {f"mlops-{env}-ingest-errors", f"mlops-{env}-ingest-dlq-backlog"}
    assert alarms[f"mlops-{env}-ingest-errors"]["MetricName"] == "Errors"
    assert "OpsAlertsTopic" in str(alarms[f"mlops-{env}-ingest-errors"]["AlarmActions"])


def test_a_stuck_message_pages_the_operator(stacks):
    """A poison object sits in the dead-letter queue until someone looks."""
    backlog = next(
        resource["Properties"]
        for resource in stacks["ingestion"].to_json()["Resources"].values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
        and resource["Properties"]["AlarmName"].endswith("-ingest-dlq-backlog")
    )
    assert backlog["MetricName"] == "ApproximateNumberOfMessagesVisible"
    assert backlog["Namespace"] == "AWS/SQS"
    # One dead-lettered message already means a lost object.
    assert backlog["Threshold"] == 1
    assert "OpsAlertsTopic" in str(backlog["AlarmActions"])
