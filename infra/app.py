#!/usr/bin/env python3
"""Build the CDK app for the selected environment."""

import pathlib
import sys
from typing import cast

import aws_cdk as cdk
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from infra.security_checks import apply_security_checks
from infra.stacks.cicd_stack import CicdStack
from infra.stacks.data_stack import DataStack
from infra.stacks.ingestion_stack import IngestionStack
from infra.stacks.monitoring_stack import MonitoringStack
from infra.stacks.registry_stack import RegistryStack
from infra.stacks.security_monitoring_stack import SecurityMonitoringStack
from infra.stacks.security_stack import SecurityStack
from infra.stacks.serving_stack import ServingStack
from infra.stacks.shared import PlatformConfig
from infra.stacks.training_stack import TrainingStack
from infra.stacks.website_stack import WebsiteStack


def load_config(env_name: str) -> PlatformConfig:
    """Load one YAML config and narrow it to `PlatformConfig`."""
    path = pathlib.Path(__file__).parent / "config" / f"{env_name}.yaml"
    return cast(PlatformConfig, yaml.safe_load(path.read_text()))


def stack_prefix(env_name: str) -> str:
    """Return the stack-name prefix for one environment."""
    return f"Mlops-{env_name.capitalize()}"


def build_app(app: cdk.App, config: PlatformConfig, prefix: str) -> dict[str, cdk.Stack]:
    """Build the stack dependency graph and apply the security checks."""
    security = SecurityStack(app, f"{prefix}-Security", config=config)
    security_monitoring = SecurityMonitoringStack(
        app,
        f"{prefix}-SecurityMonitoring",
        alert_topic=security.alert_topic,
        access_log_bucket=security.access_log_bucket,
        audit_bucket=security.audit_bucket,
        audit_key=security.audit_key,
        config=config,
    )
    data = DataStack(
        app,
        f"{prefix}-Data",
        access_log_bucket=security.access_log_bucket,
        alert_topic=security.alert_topic,
        config=config,
    )
    ingestion = IngestionStack(
        app,
        f"{prefix}-Ingestion",
        raw_bucket=data.raw_bucket,
        curated_bucket=data.curated_bucket,
        config=config,
    )
    registry = RegistryStack(app, f"{prefix}-Registry", config=config)
    training = TrainingStack(
        app,
        f"{prefix}-Training",
        curated_bucket=data.curated_bucket,
        artifacts_bucket=data.artifacts_bucket,
        config=config,
    )
    serving = ServingStack(
        app,
        f"{prefix}-Serving",
        artifacts_bucket=data.artifacts_bucket,
        package_group_name=registry.package_group_name,
        config=config,
    )
    cicd = CicdStack(
        app,
        f"{prefix}-Cicd",
        config=config,
        predict_execute_api_arn=serving.predict_execute_api_arn,
        serving_stack_arn=serving.stack_id,
    )
    monitoring = MonitoringStack(
        app,
        f"{prefix}-Monitoring",
        ops_topic=security.ops_topic,
        artifacts_bucket=data.artifacts_bucket,
        config=config,
    )

    stacks = {
        "data": data,
        "security": security,
        "security_monitoring": security_monitoring,
        "ingestion": ingestion,
        "training": training,
        "registry": registry,
        "serving": serving,
        "monitoring": monitoring,
        "cicd": cicd,
    }
    # The website is optional. A disabled environment builds no instance.
    if config["website"]["enabled"]:
        stacks["website"] = WebsiteStack(
            app,
            f"{prefix}-Website",
            artifacts_bucket=data.artifacts_bucket,
            predict_execute_api_arn=serving.predict_execute_api_arn,
            predict_url=serving.predict_url,
            config=config,
        )
    apply_security_checks(app, stacks, config, prefix)
    return stacks


def main() -> None:
    app = cdk.App()
    env_name = app.node.try_get_context("env") or "dev"
    build_app(app, load_config(env_name), stack_prefix(env_name))
    app.synth()


if __name__ == "__main__":
    main()
