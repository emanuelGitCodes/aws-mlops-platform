---
type: architecture
title: Deployment and pipeline troubleshooting checkpoint
created: "2026-07-11"
updated: "2026-08-10"
sources: ["../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md", "../../raw/evaluation-report-rollout-july-11-2026.md", "../../raw/aws-security-hardening-phase-0-baseline-july-12-2026.md", "../../../infra/stacks/lambda_code.py", "../../../pyproject.toml", "../../../src/common/features.py", "../../../src/pipeline/preprocess.py", "../../../src/pipeline/evaluate.py", "../../../src/pipeline/pipeline.py", "../../../src/pipeline/evaluation_runtime/requirements.txt", "../../../scripts/evaluate_api.py", "../../../src/serving/deploy_handler.py", "../../../src/serving/proxy_handler.py"]
summary: "The runtime pipeline and API work, but the Data stack is UPDATE_ROLLBACK_COMPLETE because its synthesized export removal conflicts with Serving."
---
# Deployment and pipeline troubleshooting checkpoint

## Confirmed

### July 12 Phase 0 status update

The current runtime remains healthy, but the stack status is no longer six
successful terminal states. `Mlops-Dev-Data` is
`UPDATE_ROLLBACK_COMPLETE` after an update attempted to delete the
artifacts-bucket export still imported by `Mlops-Dev-Serving`. Its buckets and
policies remain `CREATE_COMPLETE`, and ingestion, the successful pipeline,
endpoint, and API were reverified read-only.

The current source diff would repeat that export removal and also update Lambda
assets in Ingestion and Serving. Do not run `cdk deploy --all` until the export
relationship has a reviewed remediation. See the
[Phase 0 security baseline](security-phase-0-baseline.md) for exact fingerprints,
commands, and rollback surfaces.

### Infrastructure deployment

The July 10 deployment originally created six CDK stacks in `us-east-1`, account
`${AWS_ACCOUNT_ID}`:

- `Mlops-Dev-Data`
- `Mlops-Dev-Registry`
- `Mlops-Dev-Monitoring`
- `Mlops-Dev-Training`
- `Mlops-Dev-Ingestion`
- `Mlops-Dev-Serving`

The normal deployment identity remains `${MLOPS_DEPLOYER_USER_NAME}`; `${AWS_ADMIN_USER_NAME}` is reserved for administrative inspection and recovery. CloudFormation applies the separate `MLOpsCloudFormationExecutionPolicy` through the CDK execution role.

The deployment exposed missing CloudFormation permissions in sequence:

| Policy version | Missing action | Failure boundary | Result |
|---|---|---|---|
| v1 | `s3:PutEncryptionConfiguration` | KMS default encryption on Data buckets | Added in v2 |
| v2 | `iam:GetRolePolicy` | CDK S3 notification helper | Added in v3 |
| v3 | `lambda:InvokeFunction` | S3 notification custom resource | Added in v4 |
| v4 | `sagemaker:GetModelPackageGroupPolicy` | SageMaker model package group | Added in v5 |

Retained S3 buckets from failed Data stack attempts were checked for object versions and delete markers before cleanup. This was a targeted cleanup of confirmed-empty resources.

### Lambda runtime compatibility

The local CDK environment used Python 3.14 while the deployed Lambda runtime used Python 3.12. The dependency bundler initially installed a Python 3.14 `pydantic_core` native wheel, causing Lambda import failure. `infra/stacks/lambda_code.py` now directs pip to install CPython 3.12, manylinux-compatible, x86_64 binary wheels. Synthesis confirmed the asset contains the `cpython-312` extension.

### API and data-path verification

The serving API is:

```text
https://${API_GATEWAY_ID}.execute-api.us-east-1.amazonaws.com/dev/predict
```

The API key is active and associated with the `dev` usage-plan stage. Early test failures were local request problems: the payload file was missing, the shell variable was empty, the Bash `read -rsp` syntax was incompatible with zsh, and one hostname was mistyped. After loading the correct key and using `sample.json`, API Gateway forwarded the request to the proxy Lambda. The resulting `502` was caused by the absent SageMaker endpoint, which was the expected downstream state before a model had been deployed.

The Telco CSV was uploaded to the raw bucket and appeared under the curated prefix after ingestion:

```text
s3://${RAW_BUCKET}/telco.csv
s3://${CURATED_BUCKET}/telco/telco.csv
```

The validation Lambda logged:

```json
{"key":"telco.csv","valid":7043,"rejected":0}
```

This confirms the training-data path independently of the API inference path. The `sample.json` file is an inference request, not a training-data upload.

### Pipeline environment and execution

The pipeline environment uses `.venv-cdk/bin/python`. The pipeline extra was constrained to SageMaker 2.x and supplied `pytz` after the initial environment failed to import SageMaker modules. The pipeline evaluation S3 path was changed from Python string concatenation to SageMaker's `Join` expression because pipeline variables cannot be concatenated as ordinary strings.

The first pipeline execution, `<pipeline-execution-id>`, failed in `Preprocess` before
`Train` because the Processing job uploaded `preprocess.py` but not the
repository package containing `src.common.schema`:

```text
from src.common.schema import FEATURE_COLUMNS, LABEL_COLUMN
ModuleNotFoundError: No module named 'src'
```

This was resolved by using `FrameworkProcessor` for preprocessing so the
Processing job bundles the `src` package. That exposed a second boundary:
`schema.py` imports Pydantic, which the stock sklearn Processing image does not
include. The ordered model columns were therefore moved into dependency-free
`src.common.features`, allowing preprocessing to share the same contract without
loading the Pydantic model.

The first successful end-to-end pipeline execution was:

```text
arn:aws:sagemaker:us-east-1:${AWS_ACCOUNT_ID}:pipeline/churn-training-pipeline-dev/execution/<pipeline-execution-id>
```

Its `Preprocess` step wrote 4,930 training rows, 1,056 validation rows, and
1,057 test rows. Its XGBoost `Train` step completed and logged a 4,930 × 19
training matrix, with validation AUC reaching `0.80610` during training.

The initial `Evaluate` step then failed because the sklearn Processing image
does not include `xgboost`. Evaluation now uses a separate `FrameworkProcessor`
source bundle with `xgboost==1.7.6` in `requirements.txt`. CloudWatch confirmed
the dependency installed successfully and reported `test AUC: 0.8398`.

Execution `<pipeline-execution-id>` succeeded and registered approved model package:

```text
arn:aws:sagemaker:us-east-1:${AWS_ACCOUNT_ID}:model-package/churn-model-group/1
```

The relevant successful CloudWatch streams are:

```text
Processing: pipelines-<pipeline-execution-id>-Preprocess-sttnjQpjS0/algo-1-1783772646
Training:   pipelines-<pipeline-execution-id>-Train-beG0CsQiXC/algo-1-1783772939
Evaluate:   pipelines-<pipeline-execution-id>-Evaluate-kij0xE0MAF/algo-1-1783773129
```

### Held-out evaluation reports

The `Evaluate` step now retains its `evaluation.json` AUC property file for the
champion gate and also emits a complete test-set report to the same
execution-scoped artifacts prefix. `Preprocess` emits `api_test.jsonl` with
only API-accepted raw feature fields, a binary label, and a stable row ID; this
permits post-deployment API checks without attempting to reverse the lossy
categorical encoding.

The report's threshold is the serving contract: `score >= 0.50` means churn.
New executions place the evaluation bundle at
`evaluations/<UTC-start-timestamp>/<execution-id>/` in the artifacts bucket,
so operators can locate a run by date while retaining SageMaker's unique
lineage identifier. Its artifacts are `metrics.json`, `predictions.csv`, `confusion_matrix.png`,
`roc_curve.png`, `precision_recall_curve.png`, `calibration_curve.png`, and
`score_distribution.png`.

The first report execution, `<pipeline-execution-id>`, reached `Evaluate` but failed only
after it wrote JSON/CSV output. CloudWatch showed that the Python 3.9
Processing image does not support `zip(..., strict=True)`. The chart loops were
rewritten with index-based access, the pipeline was upserted again, and retry
execution `<pipeline-execution-id>` produced the complete bundle:

```text
s3://${ARTIFACTS_BUCKET}/churn-training-pipeline-dev/<pipeline-execution-id>/Evaluate/output/evaluation/
```

Its 1,057 held-out records contained 270 churners and 787 non-churners. At the
shared 0.50 threshold the metrics were AUC `0.8398`, accuracy `0.8023`,
precision `0.6332`, recall `0.5370`, F1 `0.5812`, and specificity `0.8933`.
The confusion matrix was 703 true negatives, 84 false positives, 125 false
negatives, and 145 true positives. The model ranks examples well, but the
current neutral threshold deliberately misses about half of actual churners;
changing it is a separate retention-cost decision and must be applied to both
reports and the API.

### Low-cost serving and API verification

The registry approval event originally invoked the deploy Lambda but failed
because serverless endpoints reject `DataCaptureConfig`. The deploy handler was
changed to keep the endpoint serverless and omit that unsupported setting. Its
Lambda bundle was also corrected to force CPython 3.12 manylinux x86_64 wheels;
otherwise an Apple-hosted Docker build could package the wrong native
`pydantic_core` binary for the x86_64 Lambda runtime.

The approved package `/1` was replayed through the deployment Lambda. It
created `churn-serverless-dev`, which reached `InService`. The protected
`/dev/predict` API was then called with `sample.json` and returned:

```json
{"churn_probability": 0.3656342029571533, "churn": false}
```

The proxy Lambda now logs a structured, payload-free result for each successful
request:

```json
{"event":"inference_response","endpoint":"churn-serverless-dev","churn_probability":0.3656342029571533,"churn":false}
```

The pipeline definition also now passes the current champion package ARN and
test AUC into `Evaluate`. Future evaluation logs identify the challenger model
artifact, challenger test AUC, champion package and AUC, and whether the
strictly-greater gate will `register` or `reject` the challenger.

The relevant Processing logs are in:

```text
Log group:  /aws/sagemaker/ProcessingJobs
Log stream: pipelines-<pipeline-execution-id>-Preprocess-66TI5ctfRx/algo-1-1783738269
```

## Synthesis

The observed system has four separate checkpoints:

```text
CDK resources -> ingestion data -> SageMaker Preprocess/Train/Evaluate -> endpoint/API
       done             done                         done                 done
```

This explains why each boundary needs its own evidence. An execution can write
partial S3 output before a later chart-rendering error, so pipeline status and
ProcessingJob logs remain authoritative until `Evaluate` reaches `Succeeded`.
The components are independently observable and fail at different boundaries.

The remaining boundary is monitoring, not model training or serving. The
low-cost serverless endpoint can make predictions, but it cannot use SageMaker
`DataCaptureConfig`; the Model Monitor capture-and-retrain path must stay
disabled until the platform adopts another capture mechanism or a provisioned
endpoint.

## Tensions or open questions

- Keep the on-demand serverless endpoint for future demos without a standing
  real-time hosting instance; it has no configured provisioned concurrency.
  Delete it only when a complete teardown is desired. The model package and
  endpoint configuration can remain for future recreation.
- The PSI drift Lambda replaces Model Monitor for this serverless endpoint.
- The training role uses the scoped Phase 5 policy. It does not attach
  `AmazonSageMakerFullAccess`.

## Operational checkpoints

Check the successful pipeline execution:

```zsh
AWS_PROFILE=${AWS_ADMIN_USER_NAME} aws sagemaker describe-pipeline-execution \
  --pipeline-execution-arn arn:aws:sagemaker:us-east-1:${AWS_ACCOUNT_ID}:pipeline/churn-training-pipeline-dev/execution/<pipeline-execution-id> \
  --region us-east-1 \
  --query '{Status:PipelineExecutionStatus,StartTime:PipelineExecutionStartTime,EndTime:PipelineExecutionEndTime,FailureReason:FailureReason}'
```

Check the endpoint before testing the API:

```zsh
AWS_PROFILE=${AWS_ADMIN_USER_NAME} aws sagemaker describe-endpoint \
  --endpoint-name churn-serverless-dev \
  --region us-east-1 \
  --query '{Status:EndpointStatus,Variant:ProductionVariants[0].VariantName,Model:ProductionVariants[0].ModelName}'
```

Once the endpoint is `InService`, run the SigV4 smoke test:

```zsh
AWS_PROFILE=${AWS_ADMIN_USER_NAME} make smoke ENV=dev
```

## Related pages

- [CDK deployment identity and bootstrap boundary](cdk-deployment-iam.md)
- [Data and ingestion path](data-and-ingestion.md)
- [Validation versus preprocessing contracts](../concepts/contracts-and-preprocessing.md)
- [Closed drift-to-retrain loop](../concepts/closed-drift-loop.md)
- [Raw troubleshooting source](../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md)
- [Raw evaluation-report rollout source](../../raw/evaluation-report-rollout-july-11-2026.md)
