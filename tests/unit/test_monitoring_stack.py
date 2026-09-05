"""Monitoring stack: the drift-to-retrain loop and the operator dashboard."""

import json

from aws_cdk.assertions import Match

from infra.stacks.monitoring_stack import (
    DRIFT_EVENT_DETAIL_TYPE,
    DRIFT_EVENT_SOURCE,
    DRIFT_STATUS,
    PIPELINE_EVENT_DETAIL_TYPE,
    PIPELINE_FAILURE_STATES,
)
from infra.stacks.shared import BASELINE_KEY
from src.common import drift
from src.common.drift import BASELINE_RUN_PREFIX, BASELINE_URI_METADATA_KEY
from tests.unit.conftest import CONFIG, import_with_stubbed_boto3

# Stub the module-level boto3 client during handler import.
RETRAIN_HANDLER = import_with_stubbed_boto3("src.monitoring.retrain_handler")
VIOLATION_STATUS = RETRAIN_HANDLER.VIOLATION_STATUS


def _iam_policy_details(template):
    statements = [
        statement
        for policy in template.find_resources("AWS::IAM::Policy").values()
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
    ]
    actions = []
    resources = []
    for statement in statements:
        action = statement["Action"]
        actions.extend([action] if isinstance(action, str) else action)
        resource = statement["Resource"]
        resources.extend([resource] if not isinstance(resource, list) else resource)
    return statements, actions, resources


def test_the_stack_and_the_drift_module_agree_on_the_event():
    # Compare the stack literals with the handler event contract.
    assert DRIFT_EVENT_SOURCE == drift.EVENT_SOURCE
    assert DRIFT_EVENT_DETAIL_TYPE == drift.EVENT_DETAIL_TYPE
    assert DRIFT_STATUS == drift.DRIFT_STATUS
    # Match the producer status with the consumer guard.
    assert VIOLATION_STATUS == DRIFT_STATUS


def test_the_baseline_promotion_contract_has_canonical_names():
    assert BASELINE_RUN_PREFIX == "monitor/baselines"
    assert BASELINE_URI_METADATA_KEY == "baseline_uri"


def test_the_violation_rule_matches_the_platforms_own_event(stacks):
    template = stacks["monitoring"]

    # Match the platform event source.
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
    # Require bundled module handlers.
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
                        "ENDPOINT_NAME": CONFIG["endpoint_name"],
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
    # The drift role has no write action for capture data.
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {"Statement": Match.array_with([Match.object_like({"Action": "s3:GetObject"})])}
            )
        },
    )
    _, actions, _ = _iam_policy_details(template)
    assert not [a for a in actions if a.startswith("s3:Put") or a.startswith("s3:Delete")]


def test_the_drift_lambda_can_read_run_baselines_and_serving_metadata(stacks):
    resources = stacks["monitoring"].to_json()["Resources"]
    policy = next(
        resource
        for logical_id, resource in resources.items()
        if logical_id.startswith("DriftEvaluationFnRoleDefaultPolicy")
    )
    statements = policy["Properties"]["PolicyDocument"]["Statement"]

    get_object = next(
        statement for statement in statements if statement["Action"] == "s3:GetObject"
    )
    object_resources = json.dumps(get_object["Resource"])
    assert f"/{BASELINE_RUN_PREFIX}/*" in object_resources
    assert f"/{BASELINE_KEY}" in object_resources

    expected_resources = {
        "sagemaker:DescribeEndpoint": f":endpoint/{CONFIG['endpoint_name']}",
        "sagemaker:DescribeEndpointConfig": f":endpoint-config/{CONFIG['endpoint_name']}-config-*",
        "sagemaker:DescribeModel": f":model/{CONFIG['endpoint_name']}-model-*",
        "sagemaker:DescribeModelPackage": f":model-package/{CONFIG['model_package_group']}/*",
    }
    for action, resource_suffix in expected_resources.items():
        statement = next(statement for statement in statements if statement["Action"] == action)
        assert resource_suffix in json.dumps(statement["Resource"])
        assert statement["Resource"] != "*"


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


def test_the_retrain_lambda_reads_the_champion_with_scoped_access(stacks):
    template = stacks["monitoring"]
    statements, actions, resources = _iam_policy_details(template)

    assert "sagemaker:ListModelPackages" in actions
    assert "sagemaker:DescribeModelPackage" in actions
    assert "*" not in resources

    list_packages = next(
        statement
        for statement in statements
        if statement["Action"] == "sagemaker:ListModelPackages"
    )
    describe_package = next(
        statement
        for statement in statements
        if statement["Action"] == "sagemaker:DescribeModelPackage"
    )
    assert ":model-package-group/" in json.dumps(list_packages["Resource"])
    assert ":model-package/" in json.dumps(describe_package["Resource"])

    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "src.monitoring.retrain_handler.handler",
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "MODEL_PACKAGE_GROUP": CONFIG["model_package_group"],
                        "RETRAIN_NO_PROGRESS_LIMIT": str(
                            CONFIG["monitor"]["retrain_no_progress_limit"]
                        ),
                    }
                )
            },
        },
    )


def test_the_dashboard_and_the_endpoint_alarm_are_unchanged(stacks):
    template = stacks["monitoring"]
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)
    # Two endpoint alarms, one for each loop handler, and one stalled-loop alarm.
    template.resource_count_is("AWS::CloudWatch::Alarm", 5)

    # Send the endpoint error alarm to the security alert topic.
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": f"mlops-{CONFIG['env_name']}-endpoint-5xx",
            "MetricName": "Invocation5XXErrors",
            "AlarmActions": [{"Fn::ImportValue": Match.any_value()}],
            "TreatMissingData": "notBreaching",
        },
    )


def test_the_stalled_loop_event_has_a_scoped_ops_alarm(stacks):
    resources = stacks["monitoring"].to_json()["Resources"]
    filters = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::Logs::MetricFilter"
    ]
    assert len(filters) == 1
    metric_filter = filters[0]
    assert metric_filter["FilterPattern"] == '{ $.event = "retrain_loop_stalled" }'
    assert "RetrainTriggerFnLogs" in str(metric_filter["LogGroupName"])
    assert metric_filter["MetricTransformations"] == [
        {
            "DefaultValue": 0,
            "MetricName": "RetrainLoopStalled",
            "MetricNamespace": f"MLOps/Monitoring/{CONFIG['env_name']}",
            "MetricValue": "1",
        }
    ]

    alarm = next(
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
        and resource["Properties"]["AlarmName"].endswith("-retrain-loop-stalled")
    )
    assert alarm["MetricName"] == "RetrainLoopStalled"
    assert alarm["Namespace"] == f"MLOps/Monitoring/{CONFIG['env_name']}"
    assert alarm["Threshold"] == 1
    assert alarm["TreatMissingData"] == "notBreaching"
    assert "OpsAlertsTopic" in str(alarm["AlarmActions"])
    assert "SecurityAlertsTopic" not in str(alarm["AlarmActions"])


def test_the_silence_alarm_fills_the_empty_periods(stacks):
    """Use `FILL` to evaluate idle hours as zero invocations."""
    alarm = next(
        resource["Properties"]
        for resource in stacks["monitoring"].to_json()["Resources"].values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
        and resource["Properties"]["AlarmName"].endswith("-endpoint-silent")
    )

    assert "MetricName" not in alarm
    expression = next(entry for entry in alarm["Metrics"] if "Expression" in entry)
    stat = next(entry for entry in alarm["Metrics"] if "MetricStat" in entry)
    assert expression["Expression"] == "FILL(m1, 0)"
    assert stat["MetricStat"]["Metric"]["MetricName"] == "Invocations"
    assert stat["MetricStat"]["Period"] == 3600
    assert alarm["ComparisonOperator"] == "LessThanThreshold"
    assert alarm["EvaluationPeriods"] == CONFIG["monitor"]["silence_alarm_hours"]
    assert alarm["TreatMissingData"] == "breaching"
    # Match the cross-stack alert-topic import.
    assert list(alarm["AlarmActions"][0]) == ["Fn::ImportValue"]


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


def test_monitoring_alarms_publish_to_the_ops_topic(stacks):
    """Keep endpoint alarms off the security topic.

    An idle dev endpoint is the expected state, so the silence alarm fires on
    any quiet day. Routing it to the security topic would add routine noise to
    the channel that carries CIS and detection findings.
    """
    alarms = [
        resource["Properties"]
        for resource in stacks["monitoring"].to_json()["Resources"].values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
    ]
    env = CONFIG["env_name"]
    assert {alarm["AlarmName"] for alarm in alarms} == {
        f"mlops-{env}-endpoint-5xx",
        f"mlops-{env}-endpoint-silent",
        f"mlops-{env}-drift-errors",
        f"mlops-{env}-retrain-errors",
        f"mlops-{env}-retrain-loop-stalled",
    }

    for alarm in alarms:
        (action,) = alarm["AlarmActions"]
        imported = action["Fn::ImportValue"]
        assert "OpsAlertsTopic" in imported, alarm["AlarmName"]
        assert "SecurityAlertsTopic" not in imported, alarm["AlarmName"]


def test_a_failed_pipeline_execution_pages_the_operator(stacks):
    """A failed retrain leaves the endpoint on the old model. SageMaker
    publishes no metric for it, so the rule is the only signal."""
    stacks["monitoring"].has_resource_properties(
        "AWS::Events::Rule",
        {
            "Name": f"mlops-{CONFIG['env_name']}-ops-pipeline-failed",
            "EventPattern": {
                "source": ["aws.sagemaker"],
                "detail-type": [PIPELINE_EVENT_DETAIL_TYPE],
                "detail": {
                    "currentPipelineExecutionStatus": PIPELINE_FAILURE_STATES,
                    "pipelineArn": [{"suffix": f"pipeline/{CONFIG['pipeline_name']}"}],
                },
            },
            "Targets": [
                Match.object_like(
                    {
                        "Arn": {"Fn::ImportValue": Match.string_like_regexp(".*OpsAlertsTopic.*")},
                        "InputTransformer": Match.any_value(),
                    }
                )
            ],
        },
    )


def test_the_failure_rule_keeps_the_name_prefix_the_topic_grant_scopes(stacks):
    """`SecurityStack` grants `events.amazonaws.com` publish on the ops topic
    for `mlops-<env>-ops-*` only. A renamed rule cannot publish."""
    names = [
        resource["Properties"]["Name"]
        for resource in stacks["monitoring"].to_json()["Resources"].values()
        if resource["Type"] == "AWS::Events::Rule" and "Name" in resource["Properties"]
    ]
    assert names
    for name in names:
        assert name.startswith(f"mlops-{CONFIG['env_name']}-ops-")


def test_the_ops_topic_reference_stays_immutable(stack_constructs):
    """A mutable topic makes the SNS target add an unscoped publish grant."""
    reference = stack_constructs["monitoring"].node.find_child("OpsTopicRef")
    assert reference.node.default_child is None


def test_each_loop_handler_has_its_own_error_alarm(stacks):
    """A handler that throws stops the loop and reports nothing else. Without
    the alarm the only symptom is an absence of drift evaluations."""
    alarms = {
        resource["Properties"]["AlarmName"]: resource["Properties"]
        for resource in stacks["monitoring"].to_json()["Resources"].values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
    }
    for slug in ("drift", "retrain"):
        alarm = alarms[f"mlops-{CONFIG['env_name']}-{slug}-errors"]
        assert alarm["Namespace"] == "AWS/Lambda"
        assert alarm["MetricName"] == "Errors"
        assert alarm["Threshold"] == 1
        # An idle handler publishes no datapoint.
        assert alarm["TreatMissingData"] == "notBreaching"


def test_the_dashboard_shows_whether_the_loop_ran(stacks):
    """The loop reports through logs alone. Without these widgets an operator
    cannot see that the hourly evaluation stopped."""
    dashboard = next(
        resource["Properties"]
        for resource in stacks["monitoring"].to_json()["Resources"].values()
        if resource["Type"] == "AWS::CloudWatch::Dashboard"
    )
    body = str(dashboard["DashboardBody"])
    assert "Drift loop" in body
    for label in ("Drift evaluations", "Retrain triggers", "Drift errors", "Retrain errors"):
        assert label in body, label
