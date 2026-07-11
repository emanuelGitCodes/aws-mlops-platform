---
type: "source"
title: "MLOps deployment and pipeline troubleshooting summary — July 10, 2026"
created: "2026-07-11"
updated: "2026-07-11"
sources: ["../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md"]
summary: "Evidence from the July 10 deployment, API, ingestion, and SageMaker pipeline troubleshooting session."
---
# MLOps deployment and pipeline troubleshooting summary — July 10, 2026

## Key claims

- The six CDK application stacks eventually reached `CREATE_COMPLETE` after the CloudFormation execution policy was expanded one denied action at a time.
- Lambda packaging initially installed Python 3.14 native wheels for a Python 3.12 Lambda runtime; targeting CPython 3.12 fixed the `pydantic_core` import failure.
- API Gateway authentication worked after the correct API key was loaded and the inference payload file was created. The later `502` came from a missing SageMaker endpoint, not from API Gateway authentication.
- The Telco CSV reached curated S3 and ingestion validated 7,043 rows with zero rejected rows.
- The SageMaker pipeline was created and started, but the inspected execution failed in `Preprocess` before training because `src.common.schema` was not packaged into the Processing job.

## Entities and concepts

- CDK bootstrap roles and the `MLOpsCloudFormationExecutionPolicy` execution boundary.
- Data, Ingestion, Registry, Training, Serving, and Monitoring stacks.
- API Gateway API key and the `dev/predict` route.
- Raw and curated S3 data zones, EventBridge, SQS, and validation Lambda.
- SageMaker Processing, Training, Model Registry, pipeline execution, and endpoint deployment.
- The distinction between training data in S3 and inference payloads sent through API Gateway.

See the maintained [deployment and pipeline troubleshooting](../architecture/deployment-and-pipeline-troubleshooting.md) page for the synthesized workflow and current checkpoint.

## Tensions or open questions

- The Processing job currently uploads `preprocess.py` without the repository package that provides `src.common.schema`. The packaging fix should preserve one shared schema rather than silently duplicating it.
- Training logs will not exist until `Preprocess` succeeds and the `Train` step starts.
