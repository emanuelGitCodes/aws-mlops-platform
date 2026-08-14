import json

import pytest
from aws_cdk.assertions import Match

from infra.app import load_config
from infra.stacks.website_stack import CONTAINER_PORT, UNBUILT_IMAGE_URI
from tests.unit.conftest import CONFIG, synth_env


@pytest.fixture(scope="module")
def website(stacks):
    return stacks["website"]


def _statements(template):
    """Return every statement across the instance-role policies."""
    statements = []
    for resource in template.to_json()["Resources"].values():
        if resource["Type"] == "AWS::IAM::Policy":
            statements.extend(resource["Properties"]["PolicyDocument"]["Statement"])
    return statements


def test_the_website_builds_only_where_the_flag_is_set():
    """Build no website stack for an environment that disables it."""
    assert CONFIG["website"]["enabled"] is True
    assert load_config("prod")["website"]["enabled"] is False

    prod = synth_env("prod", "TestProd")
    assert "website" not in prod
    assert not any(stack.stack_name.endswith("-Website") for stack in prod.values())


def test_the_instance_type_comes_from_the_config(website):
    """Read the instance size from the environment config."""
    website.has_resource_properties(
        "AWS::EC2::Instance", {"InstanceType": CONFIG["website"]["instance_type"]}
    )


def test_the_instance_opens_no_shell_port(website):
    """Keep SSH closed; Session Manager is the only shell path."""
    instance = website.find_resources("AWS::EC2::Instance")
    properties = next(iter(instance.values()))["Properties"]
    assert "KeyName" not in properties
    website.resource_count_is("AWS::EC2::KeyPair", 0)

    for rule in website.find_resources("AWS::EC2::SecurityGroupIngress").values():
        assert rule["Properties"]["FromPort"] != 22


def test_only_cloudfront_reaches_the_instance(website):
    """Admit the CloudFront prefix list and no other source."""
    rules = [
        resource["Properties"]
        for resource in website.find_resources("AWS::EC2::SecurityGroupIngress").values()
    ]
    groups = website.find_resources("AWS::EC2::SecurityGroup")
    # The group itself declares no inline rule.
    assert "SecurityGroupIngress" not in next(iter(groups.values()))["Properties"]

    assert len(rules) == 1
    assert rules[0]["SourcePrefixListId"] == CONFIG["website"]["cloudfront_prefix_list_id"]
    assert (rules[0]["FromPort"], rules[0]["ToPort"]) == (80, 80)
    assert "CidrIp" not in rules[0]


def test_the_instance_volume_is_encrypted(website):
    """Encrypt the root volume."""
    website.has_resource_properties(
        "AWS::EC2::Instance",
        {
            "BlockDeviceMappings": Match.array_with(
                [Match.object_like({"Ebs": Match.object_like({"Encrypted": True})})]
            )
        },
    )


def test_the_instance_requires_imdsv2(website):
    """Require session tokens for the instance metadata service."""
    website.has_resource_properties("AWS::EC2::LaunchTemplate", Match.object_like({}))
    templates = website.find_resources("AWS::EC2::LaunchTemplate")
    data = next(iter(templates.values()))["Properties"]["LaunchTemplateData"]
    assert data["MetadataOptions"]["HttpTokens"] == "required"


def test_the_vpc_costs_nothing_to_run(website):
    """Build public subnets only. A NAT gateway costs more than the instance."""
    website.resource_count_is("AWS::EC2::NatGateway", 0)
    for subnet in website.find_resources("AWS::EC2::Subnet").values():
        assert subnet["Properties"]["MapPublicIpOnLaunch"] is True


def test_the_vpc_records_refused_connections(website):
    """Keep a flow log for the refused traffic."""
    website.has_resource_properties("AWS::EC2::FlowLog", {"TrafficType": "REJECT"})


def test_the_mailing_list_table_is_recoverable(website):
    """Key the table by address and keep point-in-time recovery."""
    website.has_resource_properties(
        "AWS::DynamoDB::GlobalTable",
        Match.object_like(
            {
                "TableName": f"mlops-{CONFIG['env_name']}-website-mailing-list",
                "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                "BillingMode": "PAY_PER_REQUEST",
                "Replicas": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "PointInTimeRecoverySpecification": {
                                    "PointInTimeRecoveryEnabled": True
                                }
                            }
                        )
                    ]
                ),
            }
        ),
    )


def test_the_instance_role_trusts_ec2_only(website):
    """Let only EC2 assume the instance role."""
    roles = website.find_resources("AWS::IAM::Role")
    trusts = {
        logical_id: [
            statement["Principal"]
            for statement in role["Properties"]["AssumeRolePolicyDocument"]["Statement"]
        ]
        for logical_id, role in roles.items()
    }
    instance_role = next(key for key in trusts if key.startswith("WebsiteInstanceRole"))

    assert trusts[instance_role] == [{"Service": "ec2.amazonaws.com"}]
    # The flow log delivery role is the only other principal in the stack.
    assert len(trusts) == 2


def test_the_instance_reads_only_the_evaluation_reports(website):
    """Scope the artifact read to the evaluation prefix."""
    reads = [s for s in _statements(website) if s["Action"] == "s3:GetObject"]
    assert len(reads) == 1
    assert "/evaluations/*" in json.dumps(reads[0]["Resource"])

    listings = [s for s in _statements(website) if s["Action"] == "s3:ListBucket"]
    assert listings[0]["Condition"] == {"StringLike": {"s3:prefix": ["evaluations/*"]}}


def test_the_instance_writes_only_the_mailing_list(website):
    """Grant one write action, and no read of the mailing list."""
    writes = [s for s in _statements(website) if "dynamodb" in json.dumps(s["Action"])]

    assert len(writes) == 1
    # `UpdateItem` keeps the first signup time; `PutItem` would replace it.
    assert writes[0]["Action"] == "dynamodb:UpdateItem"


def test_the_instance_calls_the_predict_route(website):
    """Grant the signed prediction call and nothing wider."""
    invokes = [s for s in _statements(website) if s["Action"] == "execute-api:Invoke"]

    assert len(invokes) == 1
    assert invokes[0]["Resource"] != "*"


def test_the_image_pull_is_scoped_to_the_bootstrap_repository(website):
    """Scope the layer read to the bootstrap repository."""
    pulls = [s for s in _statements(website) if "ecr:BatchGetImage" in json.dumps(s["Action"])]
    assert "cdk-hnb659fds-container-assets-" in json.dumps(pulls[0]["Resource"])

    # AWS accepts no resource other than `*` for this action.
    tokens = [s for s in _statements(website) if s["Action"] == "ecr:GetAuthorizationToken"]
    assert tokens[0]["Resource"] == "*"


def test_the_api_behavior_never_caches_a_prediction(website):
    """Serve `/api/*` without a cache and forward the viewer address."""
    distributions = website.find_resources("AWS::CloudFront::Distribution")
    config = next(iter(distributions.values()))["Properties"]["DistributionConfig"]
    api = next(b for b in config["CacheBehaviors"] if b["PathPattern"] == "/api/*")

    # `CACHING_DISABLED` is an AWS managed policy with this fixed id.
    assert api["CachePolicyId"] == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    assert api["ViewerProtocolPolicy"] == "redirect-to-https"
    assert "POST" in api["AllowedMethods"]
    assert "OriginRequestPolicyId" in api

    assert config["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"


def test_the_origin_reaches_the_instance_over_http(website):
    """Point the distribution at the Elastic IP public DNS name."""
    distributions = website.find_resources("AWS::CloudFront::Distribution")
    config = next(iter(distributions.values()))["Properties"]["DistributionConfig"]
    origin = config["Origins"][0]

    assert origin["CustomOriginConfig"]["OriginProtocolPolicy"] == "http-only"
    # The name is built from the address, not read from the instance.
    assert "ec2-" in json.dumps(origin["DomainName"])
    assert "Fn::GetAtt" not in json.dumps(origin["DomainName"])


def test_the_user_data_runs_the_image_on_the_published_port(website):
    """Publish the container port as port 80 and pass the runtime settings."""
    instances = website.find_resources("AWS::EC2::Instance")
    user_data = json.dumps(next(iter(instances.values()))["Properties"]["UserData"])

    assert f"-p 80:{CONTAINER_PORT}" in user_data
    assert "--restart=always" in user_data
    assert f"RATE_LIMIT_PER_MINUTE={CONFIG['website']['rate_limit_per_minute']}" in user_data
    assert "TABLE_NAME=" in user_data
    assert "PREDICT_URL=" in user_data
    # botocore ignores `AWS_REGION`. The wrong name costs an IMDS lookup per client.
    assert "AWS_DEFAULT_REGION=" in user_data
    # The test app disables bundling, so no image is built.
    assert UNBUILT_IMAGE_URI in user_data
