"""Define drift detection, retraining event routing, alarms, and the dashboard.

The drift Lambda scores capture objects against the training baseline. It emits
a violation event. The retrain Lambda calls `StartPipelineExecution`.
`src/common/drift.py` owns the drift statistic.
"""

from typing import Any

from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from constructs import Construct

from infra.stacks.shared import (
    BASELINE_KEY,
    CAPTURE_PREFIX,
    PlatformConfig,
    handler_error_alarm,
    lambda_event_rule,
    platform_lambda,
)
from src.common.drift import BASELINE_RUN_PREFIX

# Keep these literals synchronized with `src/common/drift.py`.
# Importing the handler evaluates its environment lookups during synthesis.
# `tests/unit/test_monitoring_stack.py` compares both definitions.
DRIFT_EVENT_SOURCE = "mlops.monitoring"
DRIFT_EVENT_DETAIL_TYPE = "Drift Evaluation Result"
DRIFT_STATUS = "DriftDetected"

# SageMaker publishes this event for each pipeline execution state change.
PIPELINE_EVENT_DETAIL_TYPE = "SageMaker Model Building Pipeline Execution Status Change"

# These execution states end a run without a registered model.
PIPELINE_FAILURE_STATES = ["Failed", "Stopped"]


class MonitoringStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        ops_topic: sns.ITopic,
        artifacts_bucket: s3.IBucket,
        package_group_name: str,
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        endpoint_name = config["endpoint_name"]
        pipeline_name = config["pipeline_name"]

        # The drift function scores one capture window against the training baseline.
        # Its dedicated role cannot access training resources.
        drift_fn = platform_lambda(
            self,
            "DriftEvaluationFn",
            config=config,
            least_privilege_logs=True,
            handler="src.monitoring.drift_handler.handler",
            # S3 object reads dominate the drift evaluation time.
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "ARTIFACTS_BUCKET": artifacts_bucket.bucket_name,
                "BASELINE_KEY": BASELINE_KEY,
                "CAPTURE_PREFIX": CAPTURE_PREFIX,
                "ENDPOINT_NAME": endpoint_name,
            },
        )
        # Grant read-only access to the baseline and capture window.
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[
                    artifacts_bucket.arn_for_objects(BASELINE_KEY),
                    artifacts_bucket.arn_for_objects(f"{BASELINE_RUN_PREFIX}/*"),
                    artifacts_bucket.arn_for_objects(f"{CAPTURE_PREFIX}/*"),
                ],
            )
        )

        endpoint_arn = self.format_arn(
            service="sagemaker",
            resource="endpoint",
            resource_name=endpoint_name,
        )
        endpoint_config_arn = self.format_arn(
            service="sagemaker",
            resource="endpoint-config",
            resource_name=f"{endpoint_name}-config-*",
        )
        model_arn = self.format_arn(
            service="sagemaker",
            resource="model",
            resource_name=f"{endpoint_name}-model-*",
        )
        model_package_arn = self.format_arn(
            service="sagemaker",
            resource="model-package",
            resource_name=f"{package_group_name}/*",
        )
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["sagemaker:DescribeEndpoint"], resources=[endpoint_arn])
        )
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:DescribeEndpointConfig"],
                resources=[endpoint_config_arn],
            )
        )
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["sagemaker:DescribeModel"], resources=[model_arn])
        )
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:DescribeModelPackage"],
                resources=[model_package_arn],
            )
        )
        # `ListBucket` uses the bucket ARN. The prefix condition limits the listing.
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[artifacts_bucket.bucket_arn],
                conditions={"StringLike": {"s3:prefix": [f"{CAPTURE_PREFIX}/*"]}},
            )
        )
        # `events:PutEvents` uses the default event bus ARN.
        # The EventBridge rule filters the event source for consumers.
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["events:PutEvents"],
                resources=[
                    self.format_arn(service="events", resource="event-bus", resource_name="default")
                ],
            )
        )

        # The monitor schedule config controls this rule.
        events.Rule(
            self,
            "DriftEvaluationSchedule",
            schedule=events.Schedule.expression(config["monitor"]["schedule_cron"]),
            targets=[targets.LambdaFunction(drift_fn)],
        )

        # A violation starts one training pipeline execution.
        retrain_no_progress_limit = str(config["monitor"]["retrain_no_progress_limit"])
        retrain_fn = platform_lambda(
            self,
            "RetrainTriggerFn",
            config=config,
            handler="src.monitoring.retrain_handler.handler",
            timeout=Duration.minutes(1),
            environment={
                "MODEL_PACKAGE_GROUP": package_group_name,
                "PIPELINE_NAME": pipeline_name,
                "RETRAIN_NO_PROGRESS_LIMIT": retrain_no_progress_limit,
            },
        )
        # The cooldown reads `ListPipelineExecutions` before it starts a run.
        # A persistent shift emits one violation for each scheduled evaluation.
        retrain_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:StartPipelineExecution",
                    "sagemaker:ListPipelineExecutions",
                ],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="pipeline",
                        resource_name=pipeline_name,
                    )
                ],
            )
        )
        # The retrain function resolves the champion from this model package group.
        retrain_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:ListModelPackages"],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="model-package-group",
                        resource_name=package_group_name,
                    )
                ],
            )
        )
        retrain_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:DescribeModelPackage"],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="model-package",
                        resource_name=f"{package_group_name}/*",
                    )
                ],
            )
        )

        lambda_event_rule(
            self,
            "DriftViolationRule",
            source=DRIFT_EVENT_SOURCE,
            detail_type=DRIFT_EVENT_DETAIL_TYPE,
            detail={"status": [DRIFT_STATUS]},
            handler=retrain_fn,
        )

        # A retrain that fails leaves the endpoint on the old model.
        # SageMaker publishes no metric for a failed execution, so this rule is
        # the only signal. The rule name must keep the `-ops-` part.
        # `SecurityStack` scopes the topic and key grants to that prefix.
        events.Rule(
            self,
            "PipelineFailureRule",
            rule_name=f"mlops-{config['env_name']}-ops-pipeline-failed",
            event_pattern=events.EventPattern(
                source=["aws.sagemaker"],
                detail_type=[PIPELINE_EVENT_DETAIL_TYPE],
                detail={
                    "currentPipelineExecutionStatus": PIPELINE_FAILURE_STATES,
                    # Both environments publish to the same default bus.
                    "pipelineArn": events.Match.suffix(f"pipeline/{pipeline_name}"),
                },
            ),
            targets=[
                targets.SnsTopic(
                    # An imported topic has an immutable resource policy, so the
                    # target adds no unconditioned publish grant of its own.
                    # `SecurityStack` owns the grant, scoped to this rule prefix.
                    sns.Topic.from_topic_arn(self, "OpsTopicRef", ops_topic.topic_arn),
                    message=events.RuleTargetInput.from_text(
                        f"The {pipeline_name} pipeline execution ended as "
                        + events.EventField.from_path("$.detail.currentPipelineExecutionStatus")
                        + ": "
                        + events.EventField.from_path("$.detail.pipelineExecutionArn")
                    ),
                )
            ],
        )

        # A handler that throws stops the loop and reports nothing else.
        handler_error_alarm(
            self, "DriftErrors", handler=drift_fn, slug="drift", config=config, topic=ops_topic
        )
        handler_error_alarm(
            self,
            "RetrainErrors",
            handler=retrain_fn,
            slug="retrain",
            config=config,
            topic=ops_topic,
        )

        # A stalled retrain loop logs one structured event before it returns.
        # The metric filter reads only that event name from this function's log group.
        stalled_filter = logs.MetricFilter(
            self,
            "RetrainLoopStalledFilter",
            default_value=0,
            filter_pattern=logs.FilterPattern.string_value("$.event", "=", "retrain_loop_stalled"),
            log_group=retrain_fn.log_group,
            metric_name="RetrainLoopStalled",
            metric_namespace=f"MLOps/Monitoring/{config['env_name']}",
            metric_value="1",
        )
        stalled_alarm = cw.Alarm(
            self,
            "RetrainLoopStalledAlarm",
            alarm_name=f"mlops-{config['env_name']}-retrain-loop-stalled",
            metric=stalled_filter.metric(
                period=Duration.minutes(15),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        stalled_alarm.add_alarm_action(cw_actions.SnsAction(ops_topic))

        dims = {"EndpointName": endpoint_name, "VariantName": "AllTraffic"}

        def _sm_metric(metric_name: str, statistic: str, **kwargs: Any) -> cw.Metric:
            return cw.Metric(
                namespace="AWS/SageMaker",
                metric_name=metric_name,
                dimensions_map=dims,
                statistic=statistic,
                **kwargs,
            )

        dashboard = cw.Dashboard(self, "OpsDashboard", dashboard_name=f"mlops-{config['env_name']}")
        dashboard.add_widgets(
            cw.GraphWidget(
                title="Invocations",
                left=[_sm_metric("Invocations", "Sum")],
            ),
            cw.GraphWidget(
                title="Latency (incl. cold starts)",
                left=[
                    _sm_metric("ModelLatency", "p90"),
                    _sm_metric("OverheadLatency", "p90"),
                ],
            ),
            cw.GraphWidget(
                title="Errors",
                left=[
                    _sm_metric("Invocation4XXErrors", "Sum"),
                    _sm_metric("Invocation5XXErrors", "Sum"),
                ],
            ),
        )

        # The loop runs on a schedule and reports through logs alone. These
        # widgets show whether it ran and whether it started a retrain.
        dashboard.add_widgets(
            cw.GraphWidget(
                title="Drift loop",
                left=[
                    drift_fn.metric_invocations(statistic="Sum", label="Drift evaluations"),
                    retrain_fn.metric_invocations(statistic="Sum", label="Retrain triggers"),
                ],
                right=[
                    drift_fn.metric_errors(statistic="Sum", label="Drift errors"),
                    retrain_fn.metric_errors(statistic="Sum", label="Retrain errors"),
                ],
            ),
        )

        endpoint_5xx_alarm = cw.Alarm(
            self,
            "Endpoint5xxAlarm",
            alarm_name=f"mlops-{config['env_name']}-endpoint-5xx",
            metric=_sm_metric("Invocation5XXErrors", "Sum", period=Duration.minutes(5)),
            threshold=5,
            evaluation_periods=1,
            # An idle serverless endpoint publishes no datapoint.
            # Treat the missing datapoint as non-breaching for this error alarm.
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        # Deliver endpoint errors to the operational alert topic.
        endpoint_5xx_alarm.add_alarm_action(cw_actions.SnsAction(ops_topic))

        # This alarm reports a sustained lack of endpoint invocations.
        endpoint_silent_alarm = cw.Alarm(
            self,
            "EndpointSilentAlarm",
            alarm_name=f"mlops-{config['env_name']}-endpoint-silent",
            # SageMaker publishes no `Invocations` datapoint for an idle hour.
            # `FILL` supplies zero and keeps alarm evaluation active.
            # `treat_missing_data` only classifies gaps in an active evaluation.
            metric=cw.MathExpression(
                expression="FILL(m1, 0)",
                period=Duration.hours(1),
                using_metrics={"m1": _sm_metric("Invocations", "Sum", period=Duration.hours(1))},
            ),
            threshold=1,
            comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            evaluation_periods=config["monitor"]["silence_alarm_hours"],
            treat_missing_data=cw.TreatMissingData.BREACHING,
        )
        endpoint_silent_alarm.add_alarm_action(cw_actions.SnsAction(ops_topic))
