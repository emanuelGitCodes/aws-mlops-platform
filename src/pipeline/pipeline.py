"""Define the preprocess, train, evaluate, gate, and register pipeline.

The evaluation step resolves the supplied champion package and scores it on the
same held-out rows as the challenger. The `ChampionAuc` parameter remains for
execution compatibility. A challenger registers only when its test AUC beats
the current champion.
"""

from __future__ import annotations

import argparse
from typing import Any

import sagemaker
from sagemaker.inputs import TrainingInput
from sagemaker.model import Model
from sagemaker.model_metrics import MetricsSource, ModelMetrics
from sagemaker.processing import FrameworkProcessor, ProcessingInput, ProcessingOutput
from sagemaker.sklearn.estimator import SKLearn
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThan
from sagemaker.workflow.entities import PipelineVariable
from sagemaker.workflow.execution_variables import ExecutionVariables
from sagemaker.workflow.functions import Join, JsonGet
from sagemaker.workflow.model_step import ModelStep
from sagemaker.workflow.parameters import ParameterFloat, ParameterString
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.steps import ProcessingStep, TrainingStep

from src.common.drift import BASELINE_RUN_PREFIX, BASELINE_URI_METADATA_KEY
from src.common.registry import get_champion

# Configure processing, training, and inference instance types separately.
PROCESSING_INSTANCE_TYPE = "ml.m5.large"
TRAINING_INSTANCE_TYPE = "ml.m5.large"
INFERENCE_INSTANCE_TYPES = ["ml.m5.large"]

# SageMaker represents each hyperparameter as a string.
# The SDK type also permits `PipelineVariable` values.
TRAINING_HYPERPARAMETERS: dict[str, str | PipelineVariable] = {
    "objective": "binary:logistic",
    "eval_metric": "auc",
    "num_round": "200",
    "max_depth": "5",
    "eta": "0.2",
    "early_stopping_rounds": "20",
}


def build_pipeline(
    pipeline_name: str,
    role_arn: str,
    curated_bucket: str,
    artifacts_bucket: str,
    model_package_group: str,
    approval_status: str,
    region: str = "us-east-1",
) -> Pipeline:
    session = PipelineSession(default_bucket=artifacts_bucket)

    input_data = ParameterString(name="InputDataUri", default_value=f"s3://{curated_bucket}/telco/")
    champion_model_arn, champion_test_auc = get_champion(model_package_group, region)
    champion_auc = ParameterFloat(name="ChampionAuc", default_value=champion_test_auc)
    champion_model = ParameterString(
        name="ChampionModelPackageArn", default_value=champion_model_arn
    )
    baseline_destination = Join(
        on="/",
        values=[
            f"s3://{artifacts_bucket}",
            BASELINE_RUN_PREFIX,
            ExecutionVariables.PIPELINE_EXECUTION_ID,
        ],
    )
    baseline_uri = Join(on="/", values=[baseline_destination, "baseline.json"])

    # `FrameworkProcessor` bundles `src` with the preprocessing entrypoint.
    preprocess_processor = FrameworkProcessor(
        estimator_cls=SKLearn,
        framework_version="1.2-1",
        role=role_arn,
        instance_type=PROCESSING_INSTANCE_TYPE,
        instance_count=1,
        sagemaker_session=session,
    )
    preprocess_args = preprocess_processor.run(
        code="preprocess.py",
        source_dir="src/pipeline",
        dependencies=["src"],
        inputs=[ProcessingInput(source=input_data, destination="/opt/ml/processing/input")],
        outputs=[
            *(
                ProcessingOutput(output_name=n, source=f"/opt/ml/processing/{n}")
                for n in ("train", "validation", "test", "api_test")
            ),
            ProcessingOutput(
                output_name="baseline",
                source="/opt/ml/processing/baseline",
                destination=baseline_destination,
            ),
        ],
    )
    preprocess = ProcessingStep(
        name="Preprocess",
        step_args=preprocess_args,
    )

    image_uri = sagemaker.image_uris.retrieve("xgboost", region, version="1.7-1")
    estimator = sagemaker.estimator.Estimator(
        image_uri=image_uri,
        role=role_arn,
        instance_count=1,
        instance_type=TRAINING_INSTANCE_TYPE,
        output_path=f"s3://{artifacts_bucket}/training",
        sagemaker_session=session,
        hyperparameters=TRAINING_HYPERPARAMETERS,
    )
    train = TrainingStep(
        name="Train",
        estimator=estimator,
        inputs={
            "train": TrainingInput(
                preprocess.properties.ProcessingOutputConfig.Outputs["train"].S3Output.S3Uri,
                content_type="text/csv",
            ),
            "validation": TrainingInput(
                preprocess.properties.ProcessingOutputConfig.Outputs["validation"].S3Output.S3Uri,
                content_type="text/csv",
            ),
        },
    )

    evaluation_report = PropertyFile(
        name="EvaluationReport", output_name="evaluation", path="evaluation.json"
    )
    # The evaluation source bundle supplies XGBoost to the sklearn image.
    evaluate_processor = FrameworkProcessor(
        estimator_cls=SKLearn,
        framework_version="1.2-1",
        role=role_arn,
        instance_type=PROCESSING_INSTANCE_TYPE,
        instance_count=1,
        sagemaker_session=session,
    )
    evaluation_destination = Join(
        on="/",
        values=[
            f"s3://{artifacts_bucket}",
            "evaluations",
            ExecutionVariables.START_DATETIME,
            ExecutionVariables.PIPELINE_EXECUTION_ID,
        ],
    )
    evaluate_args = evaluate_processor.run(
        code="evaluate_entrypoint.py",
        source_dir="src/pipeline/evaluation_runtime",
        dependencies=["src"],
        inputs=[
            ProcessingInput(
                source=train.properties.ModelArtifacts.S3ModelArtifacts,
                destination="/opt/ml/processing/model",
            ),
            ProcessingInput(
                source=preprocess.properties.ProcessingOutputConfig.Outputs["test"].S3Output.S3Uri,
                destination="/opt/ml/processing/test",
            ),
        ],
        outputs=[
            ProcessingOutput(
                output_name="evaluation",
                source="/opt/ml/processing/evaluation",
                destination=evaluation_destination,
            )
        ],
        arguments=[
            "--champion-model-package-arn",
            champion_model,
            "--model-package-group",
            model_package_group,
            "--champion-test-auc",
            champion_auc.to_string(),
            "--artifacts-bucket",
            artifacts_bucket,
            "--region",
            region,
            "--challenger-model-artifact",
            train.properties.ModelArtifacts.S3ModelArtifacts,
        ],
    )
    evaluate = ProcessingStep(
        name="Evaluate",
        step_args=evaluate_args,
        property_files=[evaluation_report],
    )

    challenger_auc = JsonGet(
        step_name=evaluate.name,
        property_file=evaluation_report,
        json_path="binary_classification_metrics.auc.value",
    )
    current_champion_auc = JsonGet(
        step_name=evaluate.name,
        property_file=evaluation_report,
        json_path="current_champion_auc",
    )

    model = Model(
        image_uri=image_uri,
        model_data=train.properties.ModelArtifacts.S3ModelArtifacts,
        role=role_arn,
        sagemaker_session=session,
    )
    register = ModelStep(
        name="RegisterChallenger",
        step_args=model.register(
            content_types=["text/csv"],
            response_types=["text/csv"],
            inference_instances=INFERENCE_INSTANCE_TYPES,
            model_package_group_name=model_package_group,
            approval_status=approval_status,
            model_metrics=ModelMetrics(
                model_statistics=MetricsSource(
                    s3_uri=Join(
                        on="/",
                        values=[
                            evaluate.properties.ProcessingOutputConfig.Outputs[
                                "evaluation"
                            ].S3Output.S3Uri,
                            "evaluation.json",
                        ],
                    ),
                    content_type="application/json",
                )
            ),
            customer_metadata_properties={
                "test_auc": challenger_auc.to_string(),
                BASELINE_URI_METADATA_KEY: baseline_uri,
            },
        ),
    )

    gate = ConditionStep(
        name="BeatsChampion",
        conditions=[
            # JsonGet is the documented way to gate on a property file, but the
            # SDK `left` hint omits it. Remove the ignore if the SDK adds it.
            ConditionGreaterThan(
                left=challenger_auc,  # type: ignore[arg-type]
                right=current_champion_auc,  # type: ignore[arg-type]
            )
        ],
        if_steps=[register],
        else_steps=[],
    )

    return Pipeline(
        name=pipeline_name,
        parameters=[input_data, champion_auc, champion_model],
        steps=[preprocess, train, evaluate, gate],
        sagemaker_session=session,
    )


def _fresh_champion_parameters(model_package_group: str, region: str) -> dict[str, float | str]:
    """Return current registry values for an explicit pipeline start."""
    champion_arn, champion_auc = get_champion(model_package_group, region)
    return {"ChampionAuc": champion_auc, "ChampionModelPackageArn": champion_arn}


def _start_pipeline(pipeline: Pipeline, model_package_group: str, region: str) -> Any:
    """Start a pipeline with registry values read after the upsert."""
    return pipeline.start(parameters=_fresh_champion_parameters(model_package_group, region))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-name", required=True)
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--curated-bucket", required=True)
    parser.add_argument("--artifacts-bucket", required=True)
    parser.add_argument("--model-package-group", required=True)
    parser.add_argument("--approval-status", default="Approved")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--start", action="store_true", help="start an execution after upsert")
    args = parser.parse_args()

    pipeline = build_pipeline(
        args.pipeline_name,
        args.role_arn,
        args.curated_bucket,
        args.artifacts_bucket,
        args.model_package_group,
        args.approval_status,
        args.region,
    )
    pipeline.upsert(role_arn=args.role_arn)
    print(f"upserted pipeline {args.pipeline_name}")
    if args.start:
        execution = _start_pipeline(pipeline, args.model_package_group, args.region)
        print(f"started execution {execution.arn}")
