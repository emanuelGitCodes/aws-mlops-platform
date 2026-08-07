"""Monitoring and the closed loop: the drift Lambda scores a capture window,
emits a violation event, and the retrain Lambda calls StartPipelineExecution.
Also the operator dashboard.

The platform owns both ends of this loop. SageMaker Model Monitor supports
neither serverless endpoints nor new customers, so the statistic lives in
`src/common/drift.py`, the baseline comes from the preprocessing step, and the
capture objects come from the proxy Lambda.
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

# These three repeat `src/common/drift.py`. Keep them literals. Importing a
# handler here would run its module-level os.environ lookups during synth.
# tests/unit/test_monitoring_stack.py asserts that the two sides agree.
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

        # Scores one capture window against the training baseline. It carries
        # its own role rather than sharing the pipeline role, so a drift
        # evaluation can never reach what a training run can.
        drift_fn = platform_lambda(
            self,
            "DriftEvaluationFn",
            config=config,
            least_privilege_logs=True,
            handler="src.monitoring.drift_handler.handler",
            # Reading an hour of capture objects one at a time is the slow
            # part, not the statistic.
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "ARTIFACTS_BUCKET": artifacts_bucket.bucket_name,
                "BASELINE_KEY": BASELINE_KEY,
                "CAPTURE_PREFIX": CAPTURE_PREFIX,
            },
        )
        # Read the baseline and the capture window. The job never writes, so a
        # compromised drift evaluation cannot forge the record it reads.
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[
                    artifacts_bucket.arn_for_objects(BASELINE_KEY),
                    artifacts_bucket.arn_for_objects(f"{CAPTURE_PREFIX}/*"),
                ],
            )
        )
        # `ListBucket` takes the bucket ARN, so the prefix condition is what
        # keeps this off the rest of the bucket.
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[artifacts_bucket.bucket_arn],
                conditions={"StringLike": {"s3:prefix": [f"{CAPTURE_PREFIX}/*"]}},
            )
        )
        # The default bus. `events:PutEvents` takes the bus ARN, and the source
        # is not a resource, so the rule below is what stops any other consumer
        # acting on this event.
        drift_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["events:PutEvents"],
                resources=[
                    self.format_arn(service="events", resource="event-bus", resource_name="default")
                ],
            )
        )

        # The schedule is the same config key the Model Monitor schedule used.
        events.Rule(
            self,
            "DriftEvaluationSchedule",
            schedule=events.Schedule.expression(config["monitor"]["schedule_cron"]),
            targets=[targets.LambdaFunction(drift_fn)],
        )

        # A violation starts a training run. The handler is real source in
        # src/monitoring, not an inline string, so ruff, mypy, and pytest all
        # see it.
        retrain_fn = platform_lambda(
            self,
            "RetrainTriggerFn",
            config=config,
            handler="src.monitoring.retrain_handler.handler",
            timeout=Duration.minutes(1),
            environment={"PIPELINE_NAME": pipeline_name},
        )
        retrain_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:StartPipelineExecution"],
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

        # Operator dashboard.
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
        )
        # Without an action, this alarm only changes colour in the console. It
        # delivers to the same topic as the security alarms.
        endpoint_5xx_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))
