"""Security stack: the audit foundation and its CIS detections."""

import json

from aws_cdk.assertions import Match


def test_security_audit_foundation(stacks):
    template = stacks["security"]
    document = template.to_json()

    assert document["Parameters"]["SecurityAlertEmail"] == {
        "Type": "String",
        "Description": "Email endpoint for dev security and budget alerts",
    }
    assert set(document["Outputs"]) >= {
        "TrailName",
        "AuditBucketName",
        "AccessLogBucketName",
        "AuditLogGroupName",
        "SecurityAlertsTopicArn",
        "AuditKeyAlias",
    }

    template.resource_count_is("AWS::KMS::Key", 1)
    template.has_resource_properties(
        "AWS::KMS::Key",
        {
            "EnableKeyRotation": True,
            "KeyPolicy": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Sid": "AllowCloudTrailAuditEncryption",
                                    "Principal": {"Service": "cloudtrail.amazonaws.com"},
                                    "Action": ["kms:GenerateDataKey*", "kms:DescribeKey"],
                                    "Condition": Match.object_like(
                                        {
                                            "StringEquals": Match.object_like(
                                                {"aws:SourceArn": Match.any_value()}
                                            ),
                                            "StringLike": Match.object_like(
                                                {
                                                    "kms:EncryptionContext:aws:cloudtrail:arn": (
                                                        Match.any_value()
                                                    )
                                                }
                                            ),
                                        }
                                    ),
                                }
                            ),
                            Match.object_like(
                                {
                                    "Sid": "AllowRegionalCloudWatchLogsEncryption",
                                    "Principal": {"Service": Match.any_value()},
                                }
                            ),
                            Match.object_like({"Sid": "AllowCloudWatchEncryptedAlerts"}),
                            Match.object_like({"Sid": "AllowBudgetsEncryptedAlerts"}),
                        ]
                    )
                }
            ),
        },
    )
    template.has_resource_properties("AWS::KMS::Alias", {"AliasName": "alias/mlops-dev-audit"})

    template.resource_count_is("AWS::S3::Bucket", 2)
    template.all_resources_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": Match.object_like(
                {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True,
                }
            ),
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
            "VersioningConfiguration": {"Status": "Enabled"},
        },
    )
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            }
        },
    )
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": Match.object_like(
                {
                    "ServerSideEncryptionConfiguration": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "BucketKeyEnabled": True,
                                    "ServerSideEncryptionByDefault": Match.object_like(
                                        {"SSEAlgorithm": "aws:kms"}
                                    ),
                                }
                            )
                        ]
                    )
                }
            ),
            "LoggingConfiguration": Match.object_like({"LogFilePrefix": "cloudtrail/"}),
        },
    )

    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {
            "KmsKeyId": Match.any_value(),
            "LogGroupName": "/aws/cloudtrail/mlops-dev-audit",
            "RetentionInDays": 90,
        },
    )
    template.has_resource_properties(
        "AWS::CloudTrail::Trail",
        {
            "EnableLogFileValidation": True,
            "EventSelectors": [{"IncludeManagementEvents": True, "ReadWriteType": "All"}],
            "IncludeGlobalServiceEvents": True,
            "IsLogging": True,
            "IsMultiRegionTrail": True,
            "IsOrganizationTrail": False,
            "KMSKeyId": Match.any_value(),
            "TrailName": "mlops-dev-audit",
        },
    )

    template.has_resource_properties(
        "AWS::SNS::Topic",
        {
            "KmsMasterKeyId": Match.any_value(),
            "TopicName": "mlops-dev-security-alerts",
        },
    )
    template.has_resource_properties(
        "AWS::SNS::Subscription",
        {
            "Endpoint": {"Ref": "SecurityAlertEmail"},
            "Protocol": "email",
        },
    )
    template.has_resource_properties(
        "AWS::SNS::TopicPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like({"Sid": "AllowCloudWatchAlarmPublish"}),
                            Match.object_like({"Sid": "AllowBudgetsPublish"}),
                        ]
                    )
                }
            )
        },
    )
    template.resource_count_is("AWS::Logs::MetricFilter", 6)
    template.resource_count_is("AWS::CloudWatch::Alarm", 6)

    resources = document["Resources"]
    retained_types = {"AWS::KMS::Key", "AWS::S3::Bucket", "AWS::Logs::LogGroup"}
    for resource in resources.values():
        if resource["Type"] in retained_types:
            assert resource["DeletionPolicy"] == "Retain"
            assert resource["UpdateReplacePolicy"] == "Retain"

    trail_properties = next(
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::CloudTrail::Trail"
    )
    event_selector = trail_properties["EventSelectors"][0]
    assert "DataResources" not in event_selector
    assert "InsightSelectors" not in trail_properties
    assert ":log-group:/aws/cloudtrail/mlops-dev-audit:*" in json.dumps(
        trail_properties["CloudWatchLogsLogGroupArn"]
    )

    role_policy = next(
        resource["Properties"]["PolicyDocument"]
        for resource in resources.values()
        if resource["Type"] == "AWS::IAM::Policy"
    )
    assert ":log-group:/aws/cloudtrail/mlops-dev-audit:log-stream:*" in json.dumps(role_policy)

    key_policy = next(
        resource["Properties"]["KeyPolicy"]
        for resource in resources.values()
        if resource["Type"] == "AWS::KMS::Key"
    )
    service_sids = {
        statement["Sid"]
        for statement in key_policy["Statement"]
        if "Service" in statement.get("Principal", {})
    }
    assert service_sids == {
        "AllowCloudTrailAuditEncryption",
        "AllowRegionalCloudWatchLogsEncryption",
        "AllowCloudWatchEncryptedAlerts",
        "AllowBudgetsEncryptedAlerts",
        # Config writes snapshots into the KMS-encrypted audit bucket. An
        # ungranted write fails on the key, not the bucket.
        "AllowConfigSnapshotEncryption",
        # The alert topic is encrypted, so a routed finding fails on the key
        # before it reaches a subscriber.
        "AllowEventBridgeEncryptedAlerts",
    }

    topic_policy = next(
        resource["Properties"]["PolicyDocument"]
        for resource in resources.values()
        if resource["Type"] == "AWS::SNS::TopicPolicy"
    )
    service_statements = {
        statement["Sid"]: statement
        for statement in topic_policy["Statement"]
        if statement["Sid"]
        in {
            "AllowCloudWatchAlarmPublish",
            "AllowBudgetsPublish",
            "AllowEventBridgePublish",
        }
    }
    assert set(service_statements) == {
        "AllowCloudWatchAlarmPublish",
        "AllowBudgetsPublish",
        "AllowEventBridgePublish",
    }
    for statement in service_statements.values():
        assert "aws:SourceAccount" in statement["Condition"]["StringEquals"]
        assert "aws:SourceArn" in statement["Condition"]["ArnLike"]

    # Both EventBridge grants name the rule prefix. A wildcard here lets any
    # rule in the account publish to the alert topic.
    for document, sid in (
        (topic_policy, "AllowEventBridgePublish"),
        (key_policy, "AllowEventBridgeEncryptedAlerts"),
    ):
        statement = next(s for s in document["Statement"] if s.get("Sid") == sid)
        source_arn = json.dumps(statement["Condition"]["ArnLike"]["aws:SourceArn"])
        assert ":rule/mlops-dev-security-*" in source_arn

    access_log_policy = next(
        resource["Properties"]["PolicyDocument"]
        for logical_id, resource in resources.items()
        if logical_id.startswith("AccessLogBucketPolicy")
    )
    data_log_statement = next(
        statement
        for statement in access_log_policy["Statement"]
        if statement.get("Sid") == "AllowDataBucketAccessLogs"
    )
    assert data_log_statement["Principal"] == {"Service": "logging.s3.amazonaws.com"}
    assert data_log_statement["Action"] == "s3:PutObject"
    assert len(data_log_statement["Resource"]) == 3
    assert set(data_log_statement["Condition"]) == {"ArnLike", "StringEquals"}
    assert data_log_statement["Condition"]["StringEquals"] == {
        "aws:SourceAccount": {"Ref": "AWS::AccountId"}
    }
    assert "mlops-dev-data-*" in json.dumps(
        data_log_statement["Condition"]["ArnLike"]["aws:SourceArn"]
    )

    # TLS only. Every bucket policy denies insecure transport.
    template.all_resources_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Effect": "Deny",
                                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                                }
                            )
                        ]
                    )
                }
            )
        },
    )


def test_security_detection_patterns_and_alarms_are_exact(stacks):
    document = stacks["security"].to_json()
    resources = document["Resources"]
    expected_patterns = {
        '{$.userIdentity.type="Root" && $.userIdentity.invokedBy NOT EXISTS && '
        '$.eventType !="AwsServiceEvent"}',
        '{($.errorCode="*UnauthorizedOperation") || ($.errorCode="AccessDenied*")}',
        "{($.eventSource=iam.amazonaws.com) && "
        "(($.eventName=DeleteGroupPolicy) || ($.eventName=DeleteRolePolicy) || "
        "($.eventName=DeleteUserPolicy) || ($.eventName=PutGroupPolicy) || "
        "($.eventName=PutRolePolicy) || ($.eventName=PutUserPolicy) || "
        "($.eventName=CreatePolicy) || ($.eventName=DeletePolicy) || "
        "($.eventName=CreatePolicyVersion) || ($.eventName=DeletePolicyVersion) || "
        "($.eventName=AttachRolePolicy) || ($.eventName=DetachRolePolicy) || "
        "($.eventName=AttachUserPolicy) || ($.eventName=DetachUserPolicy) || "
        "($.eventName=AttachGroupPolicy) || ($.eventName=DetachGroupPolicy))}",
        "{($.eventName=CreateTrail) || ($.eventName=UpdateTrail) || "
        "($.eventName=DeleteTrail) || ($.eventName=StartLogging) || "
        "($.eventName=StopLogging)}",
        "{($.eventSource=kms.amazonaws.com) && (($.eventName=DisableKey) || "
        "($.eventName=ScheduleKeyDeletion))}",
        "{($.eventSource=s3.amazonaws.com) && (($.eventName=PutBucketAcl) || "
        "($.eventName=PutBucketPolicy) || ($.eventName=PutBucketCors) || "
        "($.eventName=PutBucketLifecycle) || ($.eventName=PutBucketReplication) || "
        "($.eventName=DeleteBucketPolicy) || ($.eventName=DeleteBucketCors) || "
        "($.eventName=DeleteBucketLifecycle) || ($.eventName=DeleteBucketReplication))}",
    }

    metric_filters = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::Logs::MetricFilter"
    ]
    assert {metric_filter["FilterPattern"] for metric_filter in metric_filters} == (
        expected_patterns
    )
    for metric_filter in metric_filters:
        assert metric_filter["LogGroupName"] == {"Ref": "AuditLogGroup6D13791A"}
        assert metric_filter["MetricTransformations"] == [
            {
                "DefaultValue": 0,
                "MetricName": metric_filter["MetricTransformations"][0]["MetricName"],
                "MetricNamespace": "MLOps/Security",
                "MetricValue": "1",
            }
        ]

    alarms = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
    ]
    topic_ref = {"Ref": "SecurityAlertsTopic1CE4D100"}
    assert len(alarms) == 6
    # Only unauthorized-api-calls needs a sustained burst, which is 3 of 3
    # five-minute datapoints. The other five page on the first event and must
    # render no DatapointsToAlarm property.
    expected_evaluation = {
        "root-user-activity": (1, None),
        "unauthorized-api-calls": (3, 3),
        "iam-policy-changes": (1, None),
        "cloudtrail-configuration-changes": (1, None),
        "kms-key-disable-or-deletion": (1, None),
        "s3-bucket-policy-changes": (1, None),
    }
    for alarm in alarms:
        slug = alarm["AlarmName"].split("-security-", 1)[1]
        periods, datapoints = expected_evaluation[slug]
        assert alarm["ActionsEnabled"] is True
        assert alarm["AlarmActions"] == [topic_ref]
        assert alarm["ComparisonOperator"] == "GreaterThanOrEqualToThreshold"
        assert alarm["EvaluationPeriods"] == periods
        assert alarm.get("DatapointsToAlarm") == datapoints
        assert alarm["Threshold"] == 1
        assert alarm["TreatMissingData"] == "notBreaching"
        if slug == "unauthorized-api-calls":
            # A filled alarm carries a Metrics array. The plain properties
            # below move inside its MetricStat.
            continue
        assert alarm["Namespace"] == "MLOps/Security"
        assert alarm["Period"] == 300
        assert alarm["Statistic"] == "Sum"
        assert "Metrics" not in alarm
    assert {alarm["AlarmName"].split("-security-", 1)[1] for alarm in alarms} == set(
        expected_evaluation
    )


def test_only_unauthorized_api_calls_fills_its_gaps(stacks):
    """A gap lets alarm evaluation reach back past it, so three datapoints can
    span more than three consecutive periods. FILL closes the gaps."""
    alarms = [
        resource["Properties"]
        for resource in stacks["security"].to_json()["Resources"].values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
    ]
    filled = [alarm for alarm in alarms if "Metrics" in alarm]
    assert len(filled) == 1
    assert filled[0]["AlarmName"].endswith("-security-unauthorized-api-calls")

    metrics = filled[0]["Metrics"]
    expression = next(entry for entry in metrics if "Expression" in entry)
    stat = next(entry for entry in metrics if "MetricStat" in entry)
    assert expression["Expression"] == "FILL(m1, 0)"
    assert expression["Id"] == "expr_1"
    assert stat["Id"] == "m1"
    assert stat["ReturnData"] is False
    assert stat["MetricStat"]["Metric"] == {
        "MetricName": "UnauthorizedApiCalls",
        "Namespace": "MLOps/Security",
    }
    assert stat["MetricStat"]["Period"] == 300
    assert stat["MetricStat"]["Stat"] == "Sum"
