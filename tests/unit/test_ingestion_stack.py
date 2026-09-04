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
