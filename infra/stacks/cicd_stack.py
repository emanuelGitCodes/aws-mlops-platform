"""The GitHub Actions deployment identity.

`.github/workflows/deploy.yml` assumes a role here through OIDC federation.
No long-lived AWS key exists for CI, and none may be created.

The trust is scoped to one GitHub environment per role. The prod environment
carries a manual approval gate, so the prod role is reachable only by a job
that passed it. A branch-scoped trust does not reach that gate.
"""

from typing import Any

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

from infra.stacks.shared import PlatformConfig

GITHUB_OIDC_DOMAIN = "token.actions.githubusercontent.com"
GITHUB_OIDC_URL = f"https://{GITHUB_OIDC_DOMAIN}"
# The audience GitHub requests when `aws-actions/configure-aws-credentials`
# exchanges its token. A provider without this client id rejects every login.
STS_AUDIENCE = "sts.amazonaws.com"


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
            # AWS validates the provider's certificate against its own
            # trusted CAs. A pinned thumbprint becomes a rotation outage the
            # day GitHub changes its chain.
            iam.CfnOIDCProvider(
                self,
                "GitHubOidcProvider",
                url=GITHUB_OIDC_URL,
                client_id_list=[STS_AUDIENCE],
            )

        deploy_role = iam.Role(
            self,
            "GitHubDeployRole",
            role_name=f"mlops-{env_name}-github-deploy",
            description=f"GitHub Actions deploys {env_name} through OIDC federation",
            assumed_by=iam.FederatedPrincipal(
                provider_arn,
                assume_role_action="sts:AssumeRoleWithWebIdentity",
                conditions={
                    "StringEquals": {
                        f"{GITHUB_OIDC_DOMAIN}:aud": STS_AUDIENCE,
                        # A `repo:<repo>:*` subject lets any branch or pull
                        # request in the repository assume this role. A
                        # ref-scoped subject does not reach the approval gate.
                        f"{GITHUB_OIDC_DOMAIN}:sub": (f"repo:{repository}:environment:{env_name}"),
                    }
                },
            ),
        )

        # The same policy the human deployer carries. It grants no service
        # access of its own: it only allows assuming the CDK bootstrap roles,
        # which hold the deployment permissions.
        deploy_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_name(
                self, "CdkDeploymentPolicy", "MLOpsCdkDeploymentPolicy"
            )
        )

        # `make smoke` reads the API URL from the Serving stack outputs, then
        # calls the endpoint. Phase 6 authorizes that call with SigV4, so the
        # caller needs execute-api:Invoke.
        #
        # A stack ARN ends in a generated id, and a REST API ARN embeds a
        # generated api id. An ARN composed here needs a wildcard over both.
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
