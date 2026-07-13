#!/usr/bin/env python3
"""CDK app entrypoint. Select env with: cdk deploy -c env=dev|prod"""

import pathlib
import sys

import aws_cdk as cdk
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from infra.security_checks import apply_security_checks
from infra.stacks.data_stack import DataStack
from infra.stacks.ingestion_stack import IngestionStack
from infra.stacks.monitoring_stack import MonitoringStack
from infra.stacks.registry_stack import RegistryStack
from infra.stacks.security_stack import SecurityStack
from infra.stacks.serving_stack import ServingStack
from infra.stacks.training_stack import TrainingStack

app = cdk.App()
env_name = app.node.try_get_context("env") or "dev"
config = yaml.safe_load((pathlib.Path(__file__).parent / "config" / f"{env_name}.yaml").read_text())
prefix = f"Mlops-{env_name.capitalize()}"

security = SecurityStack(app, f"{prefix}-Security", config=config)
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
monitoring = MonitoringStack(app, f"{prefix}-Monitoring", config=config)

apply_security_checks(
    app,
    {
        "data": data,
        "security": security,
        "ingestion": ingestion,
        "training": training,
        "registry": registry,
        "serving": serving,
        "monitoring": monitoring,
    },
)

app.synth()
