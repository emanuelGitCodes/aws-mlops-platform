"""Raw S3 ObjectCreated -> EventBridge -> SQS (+DLQ) -> validation Lambda -> curated."""

from typing import Any

from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda_event_sources as event_sources
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from infra.stacks.shared import (
    PlatformConfig,
    handler_error_alarm,
    platform_lambda,
    queue_backlog_alarm,
)


class IngestionStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        raw_bucket: s3.IBucket,
        curated_bucket: s3.IBucket,
        ops_topic: sns.ITopic,
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        dlq = sqs.Queue(
            self,
            "IngestDlq",
            retention_period=Duration.days(14),
            enforce_ssl=True,
        )
        queue = sqs.Queue(
            self,
            "IngestQueue",
            visibility_timeout=Duration.minutes(5),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=dlq),
            enforce_ssl=True,
        )

        events.Rule(
            self,
            "RawObjectCreated",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={"bucket": {"name": [raw_bucket.bucket_name]}},
            ),
            targets=[targets.SqsQueue(queue)],
        )

        validate_fn = platform_lambda(
            self,
            "ValidateFn",
            config=config,
            handler="src.ingestion.validate_handler.handler",
            timeout=Duration.minutes(4),
            memory_size=512,
            environment={"CURATED_BUCKET": curated_bucket.bucket_name},
        )
        validate_fn.add_event_source(event_sources.SqsEventSource(queue, batch_size=1))

        raw_bucket.grant_read(validate_fn)
        validate_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[
                    curated_bucket.arn_for_objects("telco/*"),
                    curated_bucket.arn_for_objects("quarantine/*"),
                ],
            )
        )
        validate_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:DeleteObject"],
                resources=[
                    curated_bucket.arn_for_objects("telco/*"),
                    curated_bucket.arn_for_objects("quarantine/*"),
                ],
            )
        )

        # A message reaches the dead-letter queue after three failed receives.
        queue_backlog_alarm(
            self,
            "IngestDlqBacklog",
            queue=dlq,
            slug="ingest-dlq",
            config=config,
            topic=ops_topic,
        )
        handler_error_alarm(
            self,
            "ValidateErrors",
            handler=validate_fn,
            slug="ingest",
            config=config,
            topic=ops_topic,
        )
