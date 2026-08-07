"""Monitoring and the closed loop: a Model Monitor violation starts the retrain
Lambda, which calls StartPipelineExecution. Also the operator dashboard.

`scripts/setup_monitor.py` creates the Model Monitor baseline and schedule. It
uses the SDK, because it needs a live endpoint and captured traffic. This stack
owns the alarm wiring and the dashboard.
"""

from typing import Any

from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sns as sns
from constructs import Construct

from infra.stacks.shared import PlatformConfig, platform_lambda, sagemaker_event_rule


class MonitoringStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        alert_topic: sns.ITopic,
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        endpoint_name = config["endpoint_name"]
        pipeline_name = config["pipeline_name"]

        # Model Monitor emits an event on a violation. The loop keys off the
        # monitoring-schedule status change event. The handler is real source
        # in src/monitoring, not an inline string, so ruff, mypy, and pytest
        # all see it.
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

        sagemaker_event_rule(
            self,
            "DriftViolationRule",
            detail_type="SageMaker Model Monitor Execution Status Change",
            detail={
                "MonitoringScheduleName": [{"prefix": endpoint_name}],
                # This must equal retrain_handler.VIOLATION_STATUS. Keep it a
                # literal. Importing the handler here would run its
                # module-level os.environ lookups during synth.
                # tests/unit/test_monitoring_stack.py asserts that they agree.
                "MonitoringExecutionStatus": ["CompletedWithViolations"],
            },
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
