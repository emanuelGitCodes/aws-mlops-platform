"""SageMaker Pipeline definition: preprocess -> train -> evaluate -> gate -> register.

The champion AUC is resolved from the Model Registry when an execution starts
(via the `ChampionAuc` pipeline parameter default, refreshed by `get_champion_auc`
each time the pipeline is upserted/started by the EventBridge->Pipeline trigger
or CI). A challenger is only registered if its test AUC beats the champion.
"""

import argparse

import boto3
import sagemaker
from sagemaker.inputs import TrainingInput
from sagemaker.model import Model
from sagemaker.model_metrics import MetricsSource, ModelMetrics
from sagemaker.processing import ProcessingInput, ProcessingOutput
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThan
from sagemaker.workflow.functions import JsonGet
from sagemaker.workflow.model_step import ModelStep
from sagemaker.workflow.parameters import ParameterFloat, ParameterString
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.steps import CacheConfig, ProcessingStep, TrainingStep


def get_champion_auc(model_package_group: str, region: str) -> float:
    """AUC of the latest Approved model package; 0.5 (coin flip) if none exists."""
    sm = boto3.client("sagemaker", region_name=region)
    packages = sm.list_model_packages(
        ModelPackageGroupName=model_package_group,
        ModelApprovalStatus="Approved",
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )["ModelPackageSummaryList"]
    if not packages:
        return 0.5
    desc = sm.describe_model_package(ModelPackageName=packages[0]["ModelPackageArn"])
    return float(
        desc["CustomerMetadataProperties"].get("test_auc", 0.5)
        if "CustomerMetadataProperties" in desc
        else 0.5
    )


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
    cache = CacheConfig(enable_caching=True, expire_after="P30D")

    input_data = ParameterString(name="InputDataUri", default_value=f"s3://{curated_bucket}/telco/")
    champion_auc = ParameterFloat(
        name="ChampionAuc", default_value=get_champion_auc(model_package_group, region)
    )

    sklearn = SKLearnProcessor(
        framework_version="1.2-1",
        role=role_arn,
        instance_type="ml.m5.large",
        instance_count=1,
        sagemaker_session=session,
    )

    preprocess = ProcessingStep(
        name="Preprocess",
        processor=sklearn,
        inputs=[ProcessingInput(source=input_data, destination="/opt/ml/processing/input")],
        outputs=[
            ProcessingOutput(output_name=n, source=f"/opt/ml/processing/{n}")
            for n in ("train", "validation", "test")
        ],
        code="src/pipeline/preprocess.py",
        cache_config=cache,
    )

    image_uri = sagemaker.image_uris.retrieve("xgboost", region, version="1.7-1")
    estimator = sagemaker.estimator.Estimator(
        image_uri=image_uri,
        role=role_arn,
        instance_count=1,
        instance_type="ml.m5.large",
        output_path=f"s3://{artifacts_bucket}/training",
        sagemaker_session=session,
        hyperparameters={
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "num_round": 200,
            "max_depth": 5,
            "eta": 0.2,
            "early_stopping_rounds": 20,
        },
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
        cache_config=cache,
    )

    evaluation_report = PropertyFile(
        name="EvaluationReport", output_name="evaluation", path="evaluation.json"
    )
    evaluate = ProcessingStep(
        name="Evaluate",
        processor=sklearn,
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
            ProcessingOutput(output_name="evaluation", source="/opt/ml/processing/evaluation")
        ],
        code="src/pipeline/evaluate.py",
        property_files=[evaluation_report],
    )

    challenger_auc = JsonGet(
        step_name=evaluate.name,
        property_file=evaluation_report,
        json_path="binary_classification_metrics.auc.value",
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
            inference_instances=["ml.m5.large"],
            model_package_group_name=model_package_group,
            approval_status=approval_status,
            model_metrics=ModelMetrics(
                model_statistics=MetricsSource(
                    s3_uri=evaluate.properties.ProcessingOutputConfig.Outputs[
                        "evaluation"
                    ].S3Output.S3Uri.to_string()
                    + "/evaluation.json",
                    content_type="application/json",
                )
            ),
            customer_metadata_properties={"test_auc": challenger_auc.to_string()},
        ),
    )

    gate = ConditionStep(
        name="BeatsChampion",
        conditions=[ConditionGreaterThan(left=challenger_auc, right=champion_auc)],
        if_steps=[register],
        else_steps=[],
    )

    return Pipeline(
        name=pipeline_name,
        parameters=[input_data, champion_auc],
        steps=[preprocess, train, evaluate, gate],
        sagemaker_session=session,
    )


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
        execution = pipeline.start()
        print(f"started execution {execution.arn}")
