"""CI/CD stack: the OIDC trust boundary and the deploy role's grants."""

import json

import pytest
from aws_cdk.assertions import Template

from infra.app import load_config
from infra.stacks.shared import github_deploy_role_name
from tests.unit.conftest import CONFIG, synth_env

GITHUB_DOMAIN = "token.actions.githubusercontent.com"


def _trust(template):
    role = next(
        resource["Properties"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::IAM::Role"
    )
    return role["AssumeRolePolicyDocument"]["Statement"][0]


def test_the_trust_names_one_github_environment(stacks):
    """The `sub` claim is the whole boundary.

    A `repo:<repo>:*` subject lets any branch or pull request in the repository
    assume this role. A ref-scoped subject ignores the GitHub environment, and
    with it any protection rule the environment carries.
    """
    statement = _trust(stacks["cicd"])
    conditions = statement["Condition"]["StringEquals"]

    assert statement["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert conditions[f"{GITHUB_DOMAIN}:aud"] == "sts.amazonaws.com"
    assert conditions[f"{GITHUB_DOMAIN}:sub"] == (
        f"repo:{CONFIG['cicd']['github_repository']}:environment:{CONFIG['env_name']}"
    )
    # A StringLike on the subject matches more than one value.
    assert "StringLike" not in statement["Condition"]


def test_only_the_deploy_workflow_on_main_can_assume_the_role(stacks):
    """The subject admits any workflow that names the environment, and write
    access is enough to add one. These three claims narrow it to one file."""
    conditions = _trust(stacks["cicd"])["Condition"]["StringEquals"]
    repository = CONFIG["cicd"]["github_repository"]

    assert conditions[f"{GITHUB_DOMAIN}:job_workflow_ref"] == (
        f"{repository}/.github/workflows/deploy.yml@refs/heads/main"
    )
    assert conditions[f"{GITHUB_DOMAIN}:repository_owner"] == repository.split("/", 1)[0]
    # A self-hosted runner executes on hardware this account does not control.
    assert conditions[f"{GITHUB_DOMAIN}:runner_environment"] == "github-hosted"


def test_the_trust_carries_no_wildcard(stacks):
    rendered = json.dumps(_trust(stacks["cicd"]))

    assert "*" not in rendered


def test_the_deploy_role_grants_no_service_access_of_its_own(stacks):
    """The role assumes the CDK bootstrap roles. Its own inline grants are the
    two `make smoke` needs, and nothing else."""
    resources = stacks["cicd"].to_json()["Resources"]
    policy = next(
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::IAM::Policy"
    )
    actions = {
        action
        for statement in policy["PolicyDocument"]["Statement"]
        for action in (
            [statement["Action"]] if isinstance(statement["Action"], str) else statement["Action"]
        )
    }

    assert actions == {"cloudformation:DescribeStacks", "execute-api:Invoke"}
    for statement in policy["PolicyDocument"]["Statement"]:
        assert statement["Resource"] != "*"


def test_only_the_owning_environment_creates_the_oidc_provider():
    """The provider is one account-wide resource, like the account budget.

    Two environments that both create it collide on the second deploy.
    """
    assert load_config("prod")["cicd"]["owns_oidc_provider"] is False

    dev = Template.from_stack(synth_env("dev", "Test-Dev-Oidc")["cicd"])
    prod = Template.from_stack(synth_env("prod", "Test-Prod-Oidc")["cicd"])

    dev.resource_count_is("AWS::IAM::OIDCProvider", 1)
    prod.resource_count_is("AWS::IAM::OIDCProvider", 0)
    # Both environments still get their own role, and prod's reads the
    # provider by ARN.
    prod.resource_count_is("AWS::IAM::Role", 1)


def test_the_provider_accepts_only_the_sts_audience(stacks):
    stacks["cicd"].has_resource_properties(
        "AWS::IAM::OIDCProvider",
        {
            "Url": f"https://{GITHUB_DOMAIN}",
            "ClientIdList": ["sts.amazonaws.com"],
        },
    )


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_each_environment_names_its_own_role(env_name):
    template = Template.from_stack(synth_env(env_name, f"Test-{env_name}-Role")["cicd"])

    template.has_resource_properties(
        "AWS::IAM::Role", {"RoleName": github_deploy_role_name(env_name)}
    )
