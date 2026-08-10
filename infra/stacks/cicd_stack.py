"""Define the GitHub Actions deployment identity.

`.github/workflows/deploy.yml` assumes this role through OIDC federation.
CI uses no long-lived AWS key. Each role trust names one GitHub environment.
GitHub environment settings own deployment protection and reviews.
"""

from typing import Any

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

from infra.stacks.shared import PlatformConfig, github_deploy_role_name

GITHUB_OIDC_DOMAIN = "token.actions.githubusercontent.com"
GITHUB_OIDC_URL = f"https://{GITHUB_OIDC_DOMAIN}"
# `aws-actions/configure-aws-credentials` requests this audience.
# The OIDC provider requires this client id.
STS_AUDIENCE = "sts.amazonaws.com"
# The deploy role trust names this workflow and branch.
# GitHub derives `job_workflow_ref` from the workflow file that owns the job.
DEPLOY_WORKFLOW_PATH = ".github/workflows/deploy.yml"
DEPLOY_WORKFLOW_REF = "refs/heads/main"


class CicdStack(Stack):
    """One OIDC provider for the account, and one deploy role per environment."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: PlatformConfig,
        predict_execute_api_arn: str,
        serving_stack_arn: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env_name = config["env_name"]
        cicd_config = config["cicd"]
        repository = cicd_config["github_repository"]

        provider_arn = self.format_arn(
            service="iam",
            region="",
            resource="oidc-provider",
            resource_name=GITHUB_OIDC_DOMAIN,
        )
        if cicd_config["owns_oidc_provider"]:
            # AWS validates the provider certificate against its trusted CAs.
            # AWS maintains the stored thumbprint. Do not pin a thumbprint here.
            iam.CfnOIDCProvider(
                self,
                "GitHubOidcProvider",
                url=GITHUB_OIDC_URL,
                client_id_list=[STS_AUDIENCE],
            )

        deploy_role = iam.Role(
            self,
            "GitHubDeployRole",
            role_name=github_deploy_role_name(env_name),
            description=f"GitHub Actions deploys {env_name} through OIDC federation",
            assumed_by=iam.FederatedPrincipal(
                provider_arn,
                assume_role_action="sts:AssumeRoleWithWebIdentity",
                conditions={
                    "StringEquals": {
                        f"{GITHUB_OIDC_DOMAIN}:aud": STS_AUDIENCE,
                        # Require the named GitHub environment in the subject.
                        f"{GITHUB_OIDC_DOMAIN}:sub": (f"repo:{repository}:environment:{env_name}"),
                        # Require the workflow file and branch in `job_workflow_ref`.
                        f"{GITHUB_OIDC_DOMAIN}:job_workflow_ref": (
                            f"{repository}/{DEPLOY_WORKFLOW_PATH}@{DEPLOY_WORKFLOW_REF}"
                        ),
                        # Require the repository owner claim.
                        f"{GITHUB_OIDC_DOMAIN}:repository_owner": repository.split("/", 1)[0],
                        # Require a GitHub-hosted runner.
                        f"{GITHUB_OIDC_DOMAIN}:runner_environment": "github-hosted",
                    }
                },
            ),
        )

        # This policy permits assumption of the CDK bootstrap roles.
        # The bootstrap roles hold the deployment permissions.
        deploy_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_name(
                self, "CdkDeploymentPolicy", "MLOpsCdkDeploymentPolicy"
            )
        )

        # `make smoke` reads the API URL from the Serving stack outputs.
        # The signed request requires `execute-api:Invoke`.
        #
        # A stack ARN ends in a generated id.
        # A REST API ARN contains a generated API id.
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                sid="ReadServingStackOutputs",
                actions=["cloudformation:DescribeStacks"],
                resources=[serving_stack_arn],
            )
        )
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeThePredictMethod",
                actions=["execute-api:Invoke"],
                resources=[predict_execute_api_arn],
            )
        )

        CfnOutput(self, "GitHubDeployRoleArn", value=deploy_role.role_arn)
