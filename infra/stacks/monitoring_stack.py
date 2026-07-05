"""Monitoring + the closed loop: Model Monitor violations -> retrain Lambda ->
StartPipelineExecution, plus the operator dashboard.

The Model Monitor baseline + schedule are created by `scripts/setup_monitor.py`
(SDK-driven, needs a live endpoint + captured traffic, so it can't be pure
CloudFormation). This stack owns the alarm wiring and the dashboard.
"""

from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct


class MonitoringStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, config: dict, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        endpoint_name = config["endpoint_name"]
        pipeline_name = config["pipeline_name"]

        # Model Monitor emits a CloudWatch event / metric on violations; we key the
        # loop off the monitoring-schedule status change event.
        retrain_fn = lambda_.Function(
            self,
            "RetrainTriggerFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            timeout=Duration.minutes(1),
            log_retention=logs.RetentionDays.TWO_WEEKS,
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
                    f"arn:aws:sagemaker:{self.region}:{self.account}:pipeline/{pipeline_name}"
                ],
            )
        )

        events.Rule(
            self,
            "DriftViolationRule",
            event_pattern=events.EventPattern(
                source=["aws.sagemaker"],
                detail_type=["SageMaker Model Monitor Execution Status Change"],
                detail={
                    "MonitoringScheduleName": [{"prefix": endpoint_name}],
                    "MonitoringExecutionStatus": ["CompletedWithViolations"],
                },
            ),
            targets=[targets.LambdaFunction(retrain_fn)],
        )

        # Operator dashboard.
        dims = {"EndpointName": endpoint_name, "VariantName": "AllTraffic"}
        dashboard = cw.Dashboard(self, "OpsDashboard", dashboard_name=f"mlops-{config['env_name']}")
        dashboard.add_widgets(
            cw.GraphWidget(
                title="Invocations",
                left=[
                    cw.Metric(
                        namespace="AWS/SageMaker",
                        metric_name="Invocations",
                        dimensions_map=dims,
                        statistic="Sum",
                    )
                ],
            ),
            cw.GraphWidget(
                title="Latency (incl. cold starts)",
                left=[
                    cw.Metric(
                        namespace="AWS/SageMaker",
                        metric_name="ModelLatency",
                        dimensions_map=dims,
                        statistic="p90",
                    ),
                    cw.Metric(
                        namespace="AWS/SageMaker",
                        metric_name="OverheadLatency",
                        dimensions_map=dims,
                        statistic="p90",
                    ),
                ],
            ),
            cw.GraphWidget(
                title="Errors",
                left=[
                    cw.Metric(
                        namespace="AWS/SageMaker",
                        metric_name="Invocation4XXErrors",
                        dimensions_map=dims,
                        statistic="Sum",
                    ),
                    cw.Metric(
                        namespace="AWS/SageMaker",
                        metric_name="Invocation5XXErrors",
                        dimensions_map=dims,
                        statistic="Sum",
                    ),
                ],
            ),
        )

        cw.Alarm(
            self,
            "Endpoint5xxAlarm",
            metric=cw.Metric(
                namespace="AWS/SageMaker",
                metric_name="Invocation5XXErrors",
                dimensions_map=dims,
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=5,
            evaluation_periods=1,
        )
