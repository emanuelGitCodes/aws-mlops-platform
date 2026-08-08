"""Monitoring stack: the drift-to-retrain loop and the operator dashboard."""

from aws_cdk.assertions import Match

from infra.stacks.monitoring_stack import (
    DRIFT_EVENT_DETAIL_TYPE,
    DRIFT_EVENT_SOURCE,
    DRIFT_STATUS,
)
from src.common import drift
from tests.unit.conftest import CONFIG, import_with_stubbed_boto3

# Stub this, like every other handler import in the suite. The module builds a
# real boto3 client at import time, and that client caches credential state
# which leaks into the SageMaker pipeline tests.
VIOLATION_STATUS = import_with_stubbed_boto3("src.monitoring.retrain_handler").VIOLATION_STATUS


def test_the_stack_and_the_drift_module_agree_on_the_event():
    # The stack repeats these three, because importing a handler during synth
    # would run its module-level env lookups. This is what keeps the copies
    # from drifting apart.
    assert DRIFT_EVENT_SOURCE == drift.EVENT_SOURCE
    assert DRIFT_EVENT_DETAIL_TYPE == drift.EVENT_DETAIL_TYPE
    assert DRIFT_STATUS == drift.DRIFT_STATUS
    # The producer's status must satisfy the consumer's guard.
    assert VIOLATION_STATUS == DRIFT_STATUS


def test_the_violation_rule_matches_the_platforms_own_event(stacks):
    template = stacks["monitoring"]

    # Not `aws.sagemaker`. Model Monitor is not in this loop, so nothing
    # emits a SageMaker monitoring event for the rule to catch.
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": Match.object_like(
                {
                    "source": [DRIFT_EVENT_SOURCE],
                    "detail-type": [DRIFT_EVENT_DETAIL_TYPE],
                    "detail": {"status": [DRIFT_STATUS]},
                }
            )
        },
    )


def test_the_drift_evaluation_runs_on_the_configured_schedule(stacks):
    stacks["monitoring"].has_resource_properties(
        "AWS::Events::Rule",
        {"ScheduleExpression": CONFIG["monitor"]["schedule_cron"]},
    )


def test_both_loop_handlers_are_bundled_source(stacks):
    # Real modules, not inline strings, so ruff, mypy, and pytest see them.
    template = stacks["monitoring"]
    for handler in (
        "src.monitoring.retrain_handler.handler",
        "src.monitoring.drift_handler.handler",
    ):
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"Handler": handler, "Code": Match.object_like({"S3Key": Match.any_value()})},
        )


def test_the_drift_lambda_knows_where_the_baseline_and_capture_live(stacks):
    stacks["monitoring"].has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "src.monitoring.drift_handler.handler",
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "BASELINE_KEY": "monitor/baseline/baseline.json",
                        "CAPTURE_PREFIX": "capture",
                    }
                )
            },
        },
    )


def test_the_drift_lambda_has_its_own_role(stack_constructs):
    """It must not reuse the pipeline role, which can start training jobs."""
    monitoring = stack_constructs["monitoring"]
    drift_fn = monitoring.node.find_child("DriftEvaluationFn")
    retrain_fn = monitoring.node.find_child("RetrainTriggerFn")
    assert drift_fn.role is not None
    assert drift_fn.role.node.addr != retrain_fn.role.node.addr


def test_the_drift_lambda_reads_capture_and_never_writes_it(stacks):
    template = stacks["monitoring"]
    # A drift evaluation that could write the capture prefix could forge the
    # evidence it reports on.
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {"Statement": Match.array_with([Match.object_like({"Action": "s3:GetObject"})])}
            )
        },
    )
    policies = template.find_resources("AWS::IAM::Policy")
    actions = [
        statement["Action"]
        for policy in policies.values()
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
    ]
    flat = [a for entry in actions for a in ([entry] if isinstance(entry, str) else entry)]
    assert not [a for a in flat if a.startswith("s3:Put") or a.startswith("s3:Delete")]


def test_the_drift_lambda_may_only_put_events_on_the_default_bus(stacks):
    stacks["monitoring"].has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "events:PutEvents",
                                    "Resource": {
                                        "Fn::Join": Match.array_with(
                                            [
                                                Match.array_with(
                                                    [
                                                        Match.string_like_regexp(
                                                            ".*event-bus/default"
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


def test_the_retrain_lambda_may_start_only_the_one_pipeline(stacks):
    stacks["monitoring"].has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": Match.array_with(
                                        ["sagemaker:StartPipelineExecution"]
                                    ),
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


def test_the_dashboard_and_the_endpoint_alarm_are_unchanged(stacks):
    template = stacks["monitoring"]
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)
    template.resource_count_is("AWS::CloudWatch::Alarm", 1)

    # An alarm with no action only changes colour in the console. This one
    # must page the same topic as the security alarms.
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": f"mlops-{CONFIG['env_name']}-endpoint-5xx",
            "MetricName": "Invocation5XXErrors",
            "AlarmActions": [{"Fn::ImportValue": Match.any_value()}],
        },
    )


def test_the_retrain_lambda_can_read_its_own_execution_history(stacks):
    """The cooldown needs ListPipelineExecutions. Without it the handler
    cannot tell whether a run is already answering this drift."""
    stacks["monitoring"].has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {"Action": Match.array_with(["sagemaker:ListPipelineExecutions"])}
                            )
                        ]
                    )
                }
            )
        },
    )
