"""Create the Model Monitor baseline + hourly schedule for the live endpoint.

Run once after the endpoint exists (SDK-driven; monitoring schedules need a
live endpoint and a baselining job, so this isn't plain CloudFormation):

    python scripts/setup_monitor.py --endpoint churn-serverless-dev \
        --role-arn <pipeline-role-arn> --artifacts-bucket <bucket> --curated-bucket <bucket>
"""

import argparse

from sagemaker.model_monitor import CronExpressionGenerator, DefaultModelMonitor
from sagemaker.model_monitor.dataset_format import DatasetFormat


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", required=True)
    p.add_argument("--role-arn", required=True)
    p.add_argument("--artifacts-bucket", required=True)
    p.add_argument("--curated-bucket", required=True)
    args = p.parse_args()

    monitor = DefaultModelMonitor(
        role=args.role_arn,
        instance_count=1,
        instance_type="ml.m5.large",
        volume_size_in_gb=20,
        max_runtime_in_seconds=1800,
    )

    monitor.suggest_baseline(
        baseline_dataset=f"s3://{args.curated_bucket}/telco/",
        dataset_format=DatasetFormat.csv(header=True),
        output_s3_uri=f"s3://{args.artifacts_bucket}/monitor/baseline",
        wait=True,
    )

    monitor.create_monitoring_schedule(
        monitor_schedule_name=f"{args.endpoint}-data-quality",
        endpoint_input=args.endpoint,
        output_s3_uri=f"s3://{args.artifacts_bucket}/monitor/reports",
        statistics=monitor.baseline_statistics(),
        constraints=monitor.suggested_constraints(),
        schedule_cron_expression=CronExpressionGenerator.hourly(),
    )
    print(f"monitoring schedule created: {args.endpoint}-data-quality")


if __name__ == "__main__":
    main()
