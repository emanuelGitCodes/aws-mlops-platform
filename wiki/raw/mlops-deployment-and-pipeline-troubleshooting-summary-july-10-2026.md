# MLOps Work Summary — July 10, 2026

This is a detailed summary of the AWS MLOps work completed on July 10, 2026. Some AWS log timestamps appear on July 11 because CloudWatch reports them in UTC; the work was performed during July 10 in the local Eastern time zone.

## Environment

- AWS account: `${AWS_ACCOUNT_ID}`
- AWS region: `us-east-1`
- AWS profile used: `${AWS_ADMIN_USER_NAME}`
- Repository: `aws-mlops-platform`
- Main API endpoint:

  `https://${API_GATEWAY_ID}.execute-api.us-east-1.amazonaws.com/dev/predict`

No API key or other secret is included in this document.

## Overall result

The infrastructure was deployed successfully, the API Gateway authentication path was configured, the ingestion flow processed the Telco churn data, and the SageMaker pipeline was created and started.

The final remaining blocker was inside the SageMaker Processing step. The pipeline failed before training began because the processing container could not import the repository's shared `src` package:

```text
ModuleNotFoundError: No module named 'src'
```

Therefore, the training job did not start yet, and there are no Training Job logs for this execution. The next required step is to package or otherwise make `src.common.schema` available to the SageMaker Processing job, rerun the pipeline, and then inspect the training and registration steps.

## Work completed

### 1. Deployed the CDK infrastructure

The following six stacks ultimately reached `CREATE_COMPLETE`:

- `Mlops-Dev-Data`
- `Mlops-Dev-Registry`
- `Mlops-Dev-Monitoring`
- `Mlops-Dev-Training`
- `Mlops-Dev-Ingestion`
- `Mlops-Dev-Serving`

The deployed system includes the S3 data zones, SageMaker model registry and pipeline resources, ingestion and monitoring Lambdas, API Gateway, the serving Lambda functions, and CloudWatch monitoring resources.

#### CloudFormation/IAM deployment issues

The deployment role was intentionally restricted. CloudFormation, rather than the local deployer identity, performs most of the resource creation through the CDK CloudFormation execution role. Several missing permissions were found incrementally:

1. The Data stack initially failed because the CloudFormation execution policy did not allow `s3:PutEncryptionConfiguration`.
2. The next deployment reached the S3 notification helper but failed because `iam:GetRolePolicy` was missing.
3. The notification helper then needed `lambda:InvokeFunction`.
4. The Registry stack failed because creating the SageMaker model package group required `sagemaker:GetModelPackageGroupPolicy`.

The customer-managed `MLOpsCloudFormationExecutionPolicy` was updated through successive versions, ending at version 5. After that, the stacks deployed successfully without granting broad administrator permissions.

Some failed Data stack attempts left retained S3 buckets. Those buckets were checked and confirmed empty before cleanup, so the cleanup was limited to empty retained resources.

### 2. Fixed Lambda dependency packaging

The first Lambda deployment appeared to succeed, but invocation failed with an import error involving Pydantic:

```text
Runtime.ImportModuleError: Unable to import module ...
No module named 'pydantic_core._pydantic_core'
```

The local CDK environment used Python 3.14, while the deployed Lambda runtime was Python 3.12. The dependency bundler had therefore installed a Python 3.14 native wheel, such as:

```text
pydantic_core.cpython-314-...
```

That binary could not be imported by Python 3.12 in Lambda.

`infra/stacks/lambda_code.py` was updated so pip targets the Lambda runtime explicitly:

```text
--implementation cp
--python-version 3.12
--platform manylinux2014_x86_64
--only-binary=:all:
```

`cdk synth` was then used to confirm that the generated asset contained the Python 3.12 native extension:

```text
pydantic_core/_pydantic_core.cpython-312-x86_64-linux-gnu.so
```

The serving Lambdas were redeployed. After that fix, the proxy Lambda was able to run and reach the SageMaker invocation code. Its next error was no longer a packaging error; it correctly reported that the expected SageMaker endpoint did not exist yet.

### 3. Verified code quality locally

The local checks passed:

```text
32 passed
All checks passed!
```

The checks included the unit tests and Ruff linting. Ruff format validation also passed during the deployment troubleshooting.

The files changed during this work included:

- `infra/stacks/lambda_code.py` — target Python 3.12-compatible Lambda wheels.
- `pyproject.toml` — pipeline dependency constraints.
- `src/pipeline/pipeline.py` — SageMaker pipeline expression fix.
- `sample.json` — local inference request payload.

No Git commit was created as part of this work.

### 4. Configured and tested API Gateway authentication

The API Gateway API key was visible in the API Gateway console, but the actual value was masked. The API key resource had:

- API key ID: `<api-key-id>`
- Status: active
- Usage plan association for API `${API_GATEWAY_ID}`
- Stage: `dev`

The first API tests had several separate problems:

- `curl` could not open `sample.json` because the file did not exist.
- The `$API_KEY` shell variable was empty.
- A Bash-style `read -rsp` command failed in zsh with `read: -p: no coprocess`.
- A manually pasted value had the wrong length.
- One request used a mistyped API Gateway hostname and produced a DNS resolution error.
- A `HEAD` request returned `403 MissingAuthenticationToken`, which was not a valid test of the protected POST route.

The correct zsh prompt syntax was:

```zsh
read -rs "API_KEY?Paste API key: "
printf '\n'
```

The key was then retrieved from API Gateway using the AWS CLI without displaying it:

```zsh
API_KEY="$(aws apigateway get-api-keys \
  --include-values \
  --region us-east-1 \
  --profile ${AWS_ADMIN_USER_NAME} \
  --query 'items[?id==`<api-key-id>`].value' \
  --output text)"
```

Once the correct key and payload were used, API Gateway accepted the request and forwarded it to the serving Lambda. The response became:

```text
HTTP/2 502
{"message": "Internal server error"}
```

CloudWatch showed that this was caused by the expected endpoint not existing yet, rather than by API key authentication or Lambda packaging.

The inference request can be run after the endpoint exists with:

```zsh
curl -i -X POST \
  https://${API_GATEWAY_ID}.execute-api.us-east-1.amazonaws.com/dev/predict \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d @sample.json
```

### 5. Resolved SageMaker pipeline environment problems

The repository did not have `.venv/bin/pip`, so this command failed:

```text
.venv/bin/pip: no such file or directory
```

The working environment was `.venv-cdk`, using its Python interpreter directly:

```zsh
.venv-cdk/bin/python -m pip ...
```

The pipeline dependency installation also encountered two issues:

- Allowing the unconstrained latest SageMaker SDK caused the resolver to select SageMaker 3.x and spend a long time resolving a large dependency tree.
- After installing the older compatible SDK, `pytz` was missing when importing SageMaker pipeline modules.

`pyproject.toml` was updated to constrain the pipeline extra to SageMaker 2.x and include `pytz`. The pipeline environment then installed successfully, including SageMaker `2.257.3`.

The pipeline code next failed while building an evaluation output path:

```text
TypeError: Pipeline variables do not support concatenation
```

The failing expression attempted to use Python string concatenation on a SageMaker pipeline variable. `src/pipeline/pipeline.py` was updated to use SageMaker's `Join` function instead, combining the dynamic S3 URI and `evaluation.json` as a pipeline expression.

After that fix, the pipeline was successfully upserted and started.

### 6. Uploaded and ingested the Telco churn data

The initial pipeline attempt had no input objects under the expected curated S3 prefix. A public Telco churn CSV was downloaded and uploaded to the raw bucket:

```text
s3://${RAW_BUCKET}/telco.csv
```

The ingestion flow produced the curated object:

```text
s3://${CURATED_BUCKET}/telco/telco.csv
```

CloudWatch confirmed successful validation:

```json
{"key":"telco.csv","valid":7043,"rejected":0}
```

This Lambda invocation completed in approximately 902 ms, used 124 MB of its 512 MB allocation, and confirmed that all 7,043 rows were accepted.

The important distinction is that this CSV upload is training data. `sample.json` is a separate inference request used to test API Gateway and the serving path; it is not the training input.

## Pipeline execution status at the end of the day

The pipeline was created as:

```text
churn-training-pipeline-dev
```

The execution that was inspected was:

```text
arn:aws:sagemaker:us-east-1:${AWS_ACCOUNT_ID}:pipeline/churn-training-pipeline-dev/execution/<pipeline-execution-id>
```

The execution eventually failed in the `Preprocess` step. The Processing job was:

```text
pipelines-<pipeline-execution-id>-Preprocess-66TI5ctfRx
```

The relevant CloudWatch log group and stream were:

```text
Log group:  /aws/sagemaker/ProcessingJobs
Log stream: pipelines-<pipeline-execution-id>-Preprocess-66TI5ctfRx/algo-1-1783738269
```

The error was:

```text
from src.common.schema import FEATURE_COLUMNS, LABEL_COLUMN
ModuleNotFoundError: No module named 'src'
```

Only the preprocessing script was uploaded as processing code. The container received the data from the curated S3 prefix, but it did not receive the repository package containing `src.common.schema`.

Because `Preprocess` failed:

- The `Train` step did not start.
- There are no SageMaker Training Job logs for this execution.
- No model package was registered from this execution.
- The model approval event did not deploy a new endpoint.
- The API correctly reaches the serving Lambda, but the expected endpoint is still unavailable.

## How to continue

### 1. Fix the Processing code package

Make `src.common.schema` available inside the SageMaker Processing container. The preferred fix is to package the shared source module with the processing code or upload a code bundle that contains the required package structure.

Avoid silently duplicating the schema in `preprocess.py` unless that tradeoff is intentional, because a duplicated schema can drift from the schema used elsewhere in the repository.

### 2. Rerun the pipeline

After deploying the pipeline code fix, rerun or start a new execution and inspect the step statuses. The expected progression is:

```text
Preprocess -> Train -> Evaluate -> Register -> Deploy
```

The dev pipeline uses approval status `Approved`, so a successful registration should be eligible for the EventBridge model-approved deployment flow.

### 3. Check execution status

```zsh
AWS_PROFILE=${AWS_ADMIN_USER_NAME} aws sagemaker describe-pipeline-execution \
  --pipeline-execution-arn arn:aws:sagemaker:us-east-1:${AWS_ACCOUNT_ID}:pipeline/churn-training-pipeline-dev/execution/<pipeline-execution-id> \
  --region us-east-1 \
  --query '{Status:PipelineExecutionStatus,StartTime:PipelineExecutionStartTime,EndTime:PipelineExecutionEndTime,FailureReason:FailureReason}'
```

### 4. Find the logs

Processing logs are in:

```text
/aws/sagemaker/ProcessingJobs
```

Training logs will appear in:

```text
/aws/sagemaker/TrainingJobs
```

Training logs will not exist until the `Train` step starts successfully. The CloudWatch Logs Insights query should include `/aws/sagemaker/TrainingJobs` after a successful preprocessing step.

### 5. Confirm the endpoint before testing the API

```zsh
AWS_PROFILE=${AWS_ADMIN_USER_NAME} aws sagemaker describe-endpoint \
  --endpoint-name churn-serverless-dev \
  --region us-east-1 \
  --query '{Status:EndpointStatus,Variant:ProductionVariants[0].VariantName,Model:ProductionVariants[0].ModelName}'
```

The endpoint must report `InService` before the API request can return a model prediction.

## Final status

The infrastructure and ingestion portions were working. API authentication and Lambda packaging were also working after the fixes. The remaining end-to-end gap was the SageMaker Processing code packaging issue:

```text
Preprocess cannot import src.common.schema
```

Once that import is fixed and the pipeline completes training and registration, the endpoint deployment and final `curl` prediction test can be completed.
