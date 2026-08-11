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
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from constructs import Construct

from infra.stacks.shared import (
    BASELINE_KEY,
    CAPTURE_PREFIX,
    PlatformConfig,
    lambda_event_rule,
    platform_lambda,
)

# Keep these literals synchronized with `src/common/drift.py`.
# Importing the handler evaluates its environment lookups during synthesis.
# `tests/unit/test_monitoring_stack.py` compares both definitions.
DRIFT_EVENT_SOURCE = "mlops.monitoring"
DRIFT_EVENT_DETAIL_TYPE = "Drift Evaluation Result"
DRIFT_STATUS = "DriftDetected"


class MonitoringStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        alert_topic: sns.ITopic,
        artifacts_bucket: s3.IBucket,
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
            },
        )
        # Grant read-only access to the baseline and capture window.
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[
                    artifacts_bucket.arn_for_objects(BASELINE_KEY),
                    artifacts_bucket.arn_for_objects(f"{CAPTURE_PREFIX}/*"),
                ],
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
        retrain_fn = platform_lambda(
            self,
            "RetrainTriggerFn",
            config=config,
            handler="src.monitoring.retrain_handler.handler",
            timeout=Duration.minutes(1),
            environment={"PIPELINE_NAME": pipeline_name},
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

        lambda_event_rule(
            self,
            "DriftViolationRule",
            source=DRIFT_EVENT_SOURCE,
            detail_type=DRIFT_EVENT_DETAIL_TYPE,
            detail={"status": [DRIFT_STATUS]},
            handler=retrain_fn,
        )

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
        # Deliver endpoint errors to the security alert topic.
        endpoint_5xx_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

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
        endpoint_silent_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))
