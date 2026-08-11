"""Structural tests for the SageMaker pipeline definition.

These tests build the real pipeline object with the boto3 session mocked. They
assert on the definition JSON SageMaker receives, like the CDK assertion tests
do on a synthesized template. They cover preprocessing, training, the promotion
gate, and registration.
"""

import json
from unittest import mock

import pytest

ROLE = "arn:aws:iam::123456789012:role/pipeline"
GROUP = "churn-model-group"
CHAMPION_ARN = f"arn:aws:sagemaker:us-east-1:123456789012:model-package/{GROUP}/7"


def _build(approval_status: str = "Approved", champion: dict | None = None) -> dict:
    """Build the pipeline and return its definition, with no AWS calls."""
    from src.pipeline.pipeline import build_pipeline

    packages = {"ModelPackageSummaryList": []}
    if champion is not None:
        packages = {"ModelPackageSummaryList": [{"ModelPackageArn": CHAMPION_ARN}]}

    with mock.patch("boto3.Session") as session_cls, mock.patch("boto3.client") as client:
        session = session_cls.return_value
        session.region_name = "us-east-1"
        for stub in (session.client.return_value, client.return_value):
            stub.list_model_packages.return_value = packages
            stub.describe_model_package.return_value = champion or {}
        pipeline = build_pipeline(
            "churn-training-pipeline-dev",
            ROLE,
            "curated-bucket",
            "artifacts-bucket",
            GROUP,
            approval_status,
            "us-east-1",
        )
        # Keep this inside the patch. definition() resolves step arguments
        # lazily, and that reaches S3 for the source bundles.
        definition: dict = json.loads(pipeline.definition())
    return definition


@pytest.fixture(scope="module")
def definition() -> dict:
    return _build()


def _step(definition: dict, name: str) -> dict:
    return next(step for step in definition["Steps"] if step["Name"] == name)


def test_steps_are_the_four_stage_drift_loop(definition):
    assert [step["Name"] for step in definition["Steps"]] == [
        "Preprocess",
        "Train",
        "Evaluate",
        "BeatsChampion",
    ]


def test_pipeline_parameters_are_the_champion_contract(definition):
    parameters = {p["Name"]: p for p in definition["Parameters"]}
    assert set(parameters) == {"InputDataUri", "ChampionAuc", "ChampionModelPackageArn"}
    # Use the 0.5 baseline when the registry has no approved package.
    assert parameters["ChampionAuc"]["DefaultValue"] == 0.5
    assert parameters["ChampionModelPackageArn"]["DefaultValue"] == "none"
    assert parameters["InputDataUri"]["DefaultValue"] == "s3://curated-bucket/telco/"


def test_gate_compares_challenger_auc_against_the_champion(definition):
    """The promotion rule. Register only when the test AUC beats the
    champion."""
    gate = _step(definition, "BeatsChampion")
    condition = gate["Arguments"]["Conditions"][0]

    assert condition["Type"] == "GreaterThan"
    left = condition["LeftValue"]["Std:JsonGet"]
    assert left["Path"] == "binary_classification_metrics.auc.value"
    assert left["PropertyFile"]["Get"].startswith("Steps.Evaluate")
    assert condition["RightValue"] == {"Get": "Parameters.ChampionAuc"}


def test_registration_only_happens_behind_the_gate(definition):
    """A challenger that loses must not reach the registry."""
    gate = _step(definition, "BeatsChampion")
    assert gate["Arguments"]["ElseSteps"] == []

    if_steps = gate["Arguments"]["IfSteps"]
    assert [step["Name"] for step in if_steps] == ["RegisterChallenger-RegisterModel"]
    # Registration is reachable only from inside the gate.
    assert not any(step["Name"].startswith("RegisterChallenger") for step in definition["Steps"])


def test_evaluate_receives_the_champion_to_compare_against(definition):
    arguments = _step(definition, "Evaluate")["Arguments"]["AppSpecification"]["ContainerArguments"]
    assert "--champion-model-package-arn" in arguments
    assert "--champion-test-auc" in arguments
    assert "--challenger-model-artifact" in arguments


def test_preprocess_and_train_are_cached_but_evaluate_is_not(definition):
    """Cache preprocessing and training. Always run evaluation."""
    for name in ("Preprocess", "Train"):
        assert _step(definition, name)["CacheConfig"]["Enabled"] is True
    assert "CacheConfig" not in _step(definition, "Evaluate")


def test_model_artifacts_land_where_the_model_role_is_allowed_to_read(definition):
    """Write model artifacts under the model-role read prefix."""
    from infra.stacks.shared import MODEL_ARTIFACT_PREFIX

    output = _step(definition, "Train")["Arguments"]["OutputDataConfig"]["S3OutputPath"]
    assert output.endswith(f"/{MODEL_ARTIFACT_PREFIX}")


def test_evaluation_reports_land_where_the_pipeline_role_is_allowed_to_write(definition):
    """Write evaluation reports under the pipeline-role output prefix."""
    from infra.stacks.shared import EVALUATION_REPORT_PREFIX

    destination = _step(definition, "Evaluate")["Arguments"]["ProcessingOutputConfig"]["Outputs"][
        0
    ]["S3Output"]["S3Uri"]
    # The destination joins the bucket, prefix, and execution variables.
    assert EVALUATION_REPORT_PREFIX in json.dumps(destination)


def test_the_baseline_lands_where_the_drift_lambda_reads_it(definition):
    """Write the baseline under the drift Lambda read key."""
    from infra.stacks.shared import BASELINE_KEY, MONITOR_OUTPUT_PREFIX
    from src.pipeline.pipeline import BASELINE_DESTINATION_PREFIX

    assert BASELINE_DESTINATION_PREFIX.startswith(f"{MONITOR_OUTPUT_PREFIX}/")
    assert BASELINE_KEY == f"{BASELINE_DESTINATION_PREFIX}/baseline.json"

    outputs = _step(definition, "Preprocess")["Arguments"]["ProcessingOutputConfig"]["Outputs"]
    baseline = next(o for o in outputs if o["OutputName"] == "baseline")
    # The other outputs are execution-scoped. This one must not be: the drift
    # Lambda reads a fixed key and cannot discover an execution id.
    assert baseline["S3Output"]["S3Uri"].endswith(f"/{BASELINE_DESTINATION_PREFIX}")


def test_training_hyperparameters_reach_the_estimator(definition):
    hyperparameters = _step(definition, "Train")["Arguments"]["HyperParameters"]
    assert hyperparameters["objective"] == "binary:logistic"
    assert hyperparameters["eval_metric"] == "auc"
    # SageMaker stringifies every value. Assert the serialized form.
    assert hyperparameters["num_round"] == "200"


@pytest.mark.parametrize("approval_status", ["Approved", "PendingManualApproval"])
def test_approval_status_is_threaded_through_to_registration(approval_status):
    """dev auto-approves. prod waits for a human."""
    definition = _build(approval_status=approval_status)
    register = _step(definition, "BeatsChampion")["Arguments"]["IfSteps"][0]
    assert register["Arguments"]["ModelApprovalStatus"] == approval_status
    assert register["Arguments"]["ModelPackageGroupName"] == GROUP


def test_existing_champion_becomes_the_bar_to_beat():
    """With an approved package in the registry, its AUC is the gate's default."""
    definition = _build(champion={"CustomerMetadataProperties": {"test_auc": "0.8398"}})
    parameters = {p["Name"]: p for p in definition["Parameters"]}
    assert parameters["ChampionAuc"]["DefaultValue"] == pytest.approx(0.8398)
    assert parameters["ChampionModelPackageArn"]["DefaultValue"] == CHAMPION_ARN
