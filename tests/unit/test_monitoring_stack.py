"""Monitoring stack: the drift-to-retrain loop and the operator dashboard."""

from aws_cdk.assertions import Match

from tests.unit.conftest import CONFIG, import_with_stubbed_boto3

# Stub this, like every other handler import in the suite. The module builds a
# real boto3 client at import time, and that client caches credential state
# which leaks into the SageMaker pipeline tests.
VIOLATION_STATUS = import_with_stubbed_boto3("src.monitoring.retrain_handler").VIOLATION_STATUS


def test_monitoring_drift_loop_wiring(stacks):
    template = stacks["monitoring"]

    # The rule status and the handler guard must agree. They cannot share a
    # constant, because importing the handler during synth runs its env
    # lookups.
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": Match.object_like(
                {"detail": Match.object_like({"MonitoringExecutionStatus": [VIOLATION_STATUS]})}
            )
        },
    )
    assert VIOLATION_STATUS == "CompletedWithViolations"

    # The handler is bundled source, not an inline string, which puts it in
    # reach of ruff, mypy, and pytest.
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "src.monitoring.retrain_handler.handler",
            "Code": Match.object_like({"S3Key": Match.any_value()}),
        },
    )
    # The retrain Lambda may start only the one pipeline.
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
                                    # The ARN is an Fn::Join over tokens.
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
    # must page the same topic as the Phase 2 security alarms.
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": f"mlops-{CONFIG['env_name']}-endpoint-5xx",
            "MetricName": "Invocation5XXErrors",
            "AlarmActions": [{"Fn::ImportValue": Match.any_value()}],
        },
    )
