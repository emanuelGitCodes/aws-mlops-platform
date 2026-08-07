import sys
from unittest import mock

import pytest

from infra.app import load_config
from scripts import setup_monitor

# Do not stub `sagemaker` into sys.modules here. `make install` syncs the
# `pipeline` extra, and test_pipeline.py needs the real SDK. A MagicMock
# registered under "sagemaker" makes `from sagemaker.inputs import ...` fail
# with "'sagemaker' is not a package" in whichever module imports it second.

ARGS = [
    "setup_monitor.py",
    "--endpoint",
    "churn-serverless-dev",
    "--role-arn",
    "arn:aws:iam::123456789012:role/test",
    "--artifacts-bucket",
    "test-artifacts",
    "--curated-bucket",
    "test-curated",
]


def _schedule_kwargs(monitor_cls: mock.Mock) -> dict:
    return monitor_cls.return_value.create_monitoring_schedule.call_args.kwargs


def test_schedule_is_whatever_the_config_says():
    """A non-default cron must reach SageMaker unchanged.

    Do not assert against the real config. Both environments hold
    `cron(0 * ? * * *)`, which is what the removed
    `CronExpressionGenerator.hourly()` produced, so real values pass even when
    the hardcoded call returns. The sentinel below tests the wiring.
    """
    sentinel = "cron(15 3 ? * MON *)"
    config = {**load_config("dev"), "monitor": {"schedule_cron": sentinel}}

    with (
        mock.patch.object(setup_monitor, "DefaultModelMonitor") as monitor_cls,
        mock.patch.object(setup_monitor, "load_config", return_value=config),
        mock.patch.object(sys, "argv", ARGS),
    ):
        setup_monitor.main()

    assert _schedule_kwargs(monitor_cls)["schedule_cron_expression"] == sentinel


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_each_environment_schedule_is_deployable(env_name):
    """Both environments' configured crons flow through for real."""
    with (
        mock.patch.object(setup_monitor, "DefaultModelMonitor") as monitor_cls,
        mock.patch.object(sys, "argv", [*ARGS, "--env", env_name]),
    ):
        setup_monitor.main()

    assert (
        _schedule_kwargs(monitor_cls)["schedule_cron_expression"]
        == (load_config(env_name)["monitor"]["schedule_cron"])
    )


def test_baseline_uses_the_curated_bucket():
    """The baseline must be suggested from curated data, not artifacts."""
    with (
        mock.patch.object(setup_monitor, "DefaultModelMonitor") as monitor_cls,
        mock.patch.object(sys, "argv", ARGS),
    ):
        setup_monitor.main()

    baseline_call = monitor_cls.return_value.suggest_baseline.call_args.kwargs
    assert baseline_call["baseline_dataset"] == "s3://test-curated/telco/"
