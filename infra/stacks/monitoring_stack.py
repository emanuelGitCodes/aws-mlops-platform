"""Monitoring + the closed loop: Model Monitor violations -> retrain Lambda ->
StartPipelineExecution, plus the operator dashboard.

The Model Monitor baseline + schedule are created by `scripts/setup_monitor.py`
(SDK-driven, needs a live endpoint + captured traffic, so it can't be pure
CloudFormation). This stack owns the alarm wiring and the dashboard.
"""

from typing import Any

from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

from infra.stacks.shared import PlatformConfig, platform_lambda, sagemaker_event_rule


class MonitoringStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, config: PlatformConfig, **kwargs: Any
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        endpoint_name = config["endpoint_name"]
        pipeline_name = config["pipeline_name"]

        # Model Monitor emits a CloudWatch event / metric on violations; we key the
        # loop off the monitoring-schedule status change event.
        retrain_fn = platform_lambda(
            self,
            "RetrainTriggerFn",
            config=config,
            handler="index.handler",
            timeout=Duration.minutes(1),
            environment={"PIPELINE_NAME": pipeline_name},
            code=lambda_.Code.from_inline(
                "import boto3, os, json\n"
                "def handler(event, context):\n"
                "    status = event['detail'].get('MonitoringExecutionStatus')\n"
                "    if status != 'CompletedWithViolations':\n"
                "        return {'skipped': status}\n"
                "    arn = boto3.client('sagemaker').start_pipeline_execution(\n"
                "        PipelineName=os.environ['PIPELINE_NAME'],\n"
                "        PipelineExecutionDescription='drift-triggered retrain',\n"
                "    )['PipelineExecutionArn']\n"
                "    print(json.dumps({'retrain_started': arn}))\n"
                "    return {'retrain_started': arn}\n"
            ),
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

        cw.Alarm(
            self,
            "Endpoint5xxAlarm",
            metric=_sm_metric("Invocation5XXErrors", "Sum", period=Duration.minutes(5)),
            threshold=5,
            evaluation_periods=1,
        )
