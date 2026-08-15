"""Define the public demo website.

One EC2 instance runs the site as a container. CloudFront terminates TLS and
reaches the instance over HTTP. The security group admits the CloudFront
origin-facing prefix list only, so no other caller reaches port 80.

An Application Load Balancer costs more each month than the whole platform
budget, so this stack uses CloudFront and an Elastic IP in its place.

A change to the image changes the user data, and the instance is replaced. The
site returns errors for one to two minutes during that replacement.
"""

import pathlib
from typing import Any

from aws_cdk import Aws, CfnCondition, CfnOutput, Fn, IgnoreMode, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from infra.stacks.shared import (
    EVALUATION_REPORT_PREFIX,
    PlatformConfig,
    log_retention,
)

# The CDK bootstrap stack owns this repository. `DockerImageAsset` pushes the
# image there, and the instance pulls it from there.
BOOTSTRAP_REPOSITORY = "cdk-hnb659fds-container-assets-{account}-{region}"

# The unit-test app disables bundling. Synthesis then produces no image, and
# the user data carries this placeholder in place of the image URI.
UNBUILT_IMAGE_URI = "image-unavailable-without-bundling"

# The container binds this port. A user without privileges cannot bind port 80.
CONTAINER_PORT = 8080

# The CDK CLI runs `app.py` from `infra/`, so the asset needs an absolute path.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Only these paths reach the image build and its asset hash. The list is an
# allowlist: exclude everything, then admit the backend and the shared
# contract. `website/backend/Dockerfile` copies the same two directories.
# The frontend is a separate build and MUST NOT change this asset hash.
_IMAGE_CONTENT = [
    "*",
    "!website",
    "!website/__init__.py",
    "!website/backend",
    "!website/backend/**",
    "!src",
    "!src/__init__.py",
    "!src/common",
    "!src/common/**",
    # The backend reads these to seed the prediction form.
    "!sample.json",
    "!sample-high-risk.json",
    "website/frontend",
    "website/frontend/**",
    "website/local",
    "**/__pycache__",
    "**/__pycache__/**",
]


class WebsiteStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        artifacts_bucket: s3.IBucket,
        predict_execute_api_arn: str,
        predict_url: str,
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env_name = config["env_name"]
        website = config["website"]

        # Public subnets only. A NAT gateway costs more than the instance.
        vpc = ec2.Vpc(
            self,
            "WebsiteVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    map_public_ip_on_launch=True,
                )
            ],
        )
        flow_log_group = logs.LogGroup(
            self,
            "WebsiteFlowLogs",
            retention=log_retention(config),
            removal_policy=RemovalPolicy.DESTROY,
        )
        # Record the refused connections. Accepted traffic is the site itself.
        vpc.add_flow_log(
            "WebsiteRejectFlowLog",
            traffic_type=ec2.FlowLogTrafficType.REJECT,
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(flow_log_group),
        )

        security_group = ec2.SecurityGroup(
            self,
            "WebsiteSecurityGroup",
            vpc=vpc,
            description="Admit HTTP from CloudFront only",
        )
        # This prefix list holds the CloudFront origin-facing ranges. A direct
        # caller reaches no open port.
        security_group.add_ingress_rule(
            peer=ec2.Peer.prefix_list(website["cloudfront_prefix_list_id"]),
            connection=ec2.Port.tcp(80),
            description="CloudFront origin-facing ranges",
        )

        self.table = dynamodb.TableV2(
            self,
            "MailingListTable",
            table_name=f"mlops-{env_name}-website-mailing-list",
            partition_key=dynamodb.Attribute(name="email", type=dynamodb.AttributeType.STRING),
            billing=dynamodb.Billing.on_demand(),
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.instance_role = iam.Role(
            self,
            "WebsiteInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="Website instance; reads evaluations and calls /predict",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
            ],
        )
        # The bootstrap repository ARN is deterministic. Reading it from the
        # image asset would change the template when bundling is disabled.
        repository_arn = self.format_arn(
            service="ecr",
            resource="repository",
            resource_name=BOOTSTRAP_REPOSITORY.format(account=self.account, region=self.region),
        )
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchCheckLayerAvailability",
                ],
                resources=[repository_arn],
            )
        )
        # `ecr:GetAuthorizationToken` accepts no resource other than `*`.
        self.instance_role.add_to_policy(
            iam.PolicyStatement(actions=["ecr:GetAuthorizationToken"], resources=["*"])
        )
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[artifacts_bucket.arn_for_objects(f"{EVALUATION_REPORT_PREFIX}/*")],
            )
        )
        # `ListBucket` uses the bucket ARN. The prefix condition limits the listing.
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[artifacts_bucket.bucket_arn],
                conditions={"StringLike": {"s3:prefix": [f"{EVALUATION_REPORT_PREFIX}/*"]}},
            )
        )
        # `UpdateItem` keeps the first signup time. The site never reads an
        # address back, so the role carries no `GetItem` or `Scan`.
        self.instance_role.add_to_policy(
            iam.PolicyStatement(actions=["dynamodb:UpdateItem"], resources=[self.table.table_arn])
        )
        self.instance_role.add_to_policy(
            iam.PolicyStatement(actions=["execute-api:Invoke"], resources=[predict_execute_api_arn])
        )

        image_uri = UNBUILT_IMAGE_URI
        if self.bundling_required:
            image = ecr_assets.DockerImageAsset(
                self,
                "WebsiteImage",
                directory=str(_REPO_ROOT),
                file="website/backend/Dockerfile",
                platform=ecr_assets.Platform.LINUX_ARM64,
                # The context is the repository root, so this allowlist decides
                # the asset hash. Without it every unrelated file rebuilds the
                # image. `IgnoreMode.GIT` keeps `.git` out; a worktree stores it
                # as a file holding an absolute path.
                exclude=_IMAGE_CONTENT,
                ignore_mode=IgnoreMode.GIT,
            )
            image_uri = image.image_uri

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -eux",
            "dnf install -y docker",
            "systemctl enable --now docker",
            f"REGISTRY=$(echo {image_uri} | cut -d/ -f1)",
            f"aws ecr get-login-password --region {self.region}"
            " | docker login --username AWS --password-stdin $REGISTRY",
            f"docker pull {image_uri}",
            "docker run -d --restart=always"
            f" -p 80:{CONTAINER_PORT}"
            f" -e PORT={CONTAINER_PORT}"
            # botocore reads `AWS_DEFAULT_REGION`. It ignores `AWS_REGION`, and
            # then reads the region from the instance metadata on every client.
            f" -e AWS_DEFAULT_REGION={self.region}"
            f" -e TABLE_NAME={self.table.table_name}"
            f" -e ARTIFACTS_BUCKET={artifacts_bucket.bucket_name}"
            f" -e EVALUATION_PREFIX={EVALUATION_REPORT_PREFIX}"
            f" -e PREDICT_URL={predict_url}"
            f" -e RATE_LIMIT_PER_MINUTE={website['rate_limit_per_minute']}"
            f" {image_uri}",
        )

        instance = ec2.Instance(
            self,
            "WebsiteInstance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType(website["instance_type"]),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64
            ),
            security_group=security_group,
            role=self.instance_role,
            user_data=user_data,
            # A new image changes the user data and replaces the instance.
            user_data_causes_replacement=True,
            require_imdsv2=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        8, encrypted=True, volume_type=ec2.EbsDeviceVolumeType.GP3
                    ),
                )
            ],
        )

        # The address survives an instance replacement, so the distribution
        # keeps one origin for the life of the stack.
        address = ec2.CfnEIP(self, "WebsiteEip", instance_id=instance.instance_id)
        origin_domain = self.public_dns_name(address.ref)

        self.distribution = cloudfront.Distribution(
            self,
            "WebsiteDistribution",
            comment=f"mlops-{env_name}-website",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.HttpOrigin(
                    origin_domain,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                    http_port=80,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                # The API answers each caller. A cached prediction would
                # return one caller's answer to another.
                "/api/*": cloudfront.BehaviorOptions(
                    origin=origins.HttpOrigin(
                        origin_domain,
                        protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                        http_port=80,
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    # The rate limiter reads the viewer address from
                    # `X-Forwarded-For`. An EC2 origin rejects the viewer Host.
                    origin_request_policy=(
                        cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER
                    ),
                ),
            },
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            http_version=cloudfront.HttpVersion.HTTP2,
        )

        CfnOutput(
            self,
            "WebsiteUrl",
            value=f"https://{self.distribution.distribution_domain_name}",
        )
        CfnOutput(self, "MailingListTableName", value=self.table.table_name)

    def public_dns_name(self, address: str) -> str:
        """Return the public DNS name AWS assigns to one Elastic IP.

        CloudFront takes a domain name for an origin and refuses an address.
        AWS builds this name from the address, so this stack needs no lookup.

        The instance attribute `PublicDnsName` resolves before the address
        attaches, and it then names an address AWS has released. Build the
        name from the Elastic IP instead.

        These stacks carry no `env`, so `self.region` is a token and a Python
        comparison cannot read it. The condition resolves at deploy time.
        """
        dashed = Fn.join("-", Fn.split(".", address))
        in_us_east_1 = CfnCondition(
            self,
            "OriginInUsEast1",
            expression=Fn.condition_equals(Aws.REGION, "us-east-1"),
        )
        # us-east-1 uses `compute-1`. Every other region uses its own name.
        domain = Fn.condition_if(
            in_us_east_1.logical_id, "compute-1", f"{Aws.REGION}.compute"
        ).to_string()
        return f"ec2-{dashed}.{domain}.amazonaws.com"
