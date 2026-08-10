"""Unit tests for the deployment verification CLI.

The AWS calls are thin wrappers. These tests cover the event filtering, which
separates a real resource change from a stack that only reached
UPDATE_COMPLETE.
"""

import datetime as dt
from unittest import mock

import scripts.verify_deployment as verify_deployment
from scripts.verify_deployment import (
    build_parser,
    collect,
    format_report,
    select_changed_resources,
)

STACK = "Mlops-Dev-Monitoring"
UPDATED = dt.datetime(2026, 7, 24, 20, 47, 14, tzinfo=dt.UTC)


def _event(logical_id, status, minute=48):
    return {
        "LogicalResourceId": logical_id,
        "ResourceStatus": status,
        "Timestamp": dt.datetime(2026, 7, 24, 20, minute, tzinfo=dt.UTC),
    }


def test_metadata_only_update_reports_no_resource_change():
    """Report no resource change for a metadata-only stack update."""
    events = [
        _event(STACK, "UPDATE_COMPLETE"),
        _event(STACK, "UPDATE_IN_PROGRESS"),
        _event("CDKMetadata", "UPDATE_COMPLETE"),
        _event("CDKMetadata", "UPDATE_IN_PROGRESS"),
    ]
    assert select_changed_resources(events, STACK, UPDATED) == []


def test_real_resource_change_is_reported():
    events = [
        _event(STACK, "UPDATE_COMPLETE"),
        _event("ProxyFn0105D3E4", "UPDATE_COMPLETE"),
        _event("DeployFn0FE820C6", "UPDATE_COMPLETE"),
        _event("CDKMetadata", "UPDATE_COMPLETE"),
    ]
    assert select_changed_resources(events, STACK, UPDATED) == [
        ("DeployFn0FE820C6", "UPDATE_COMPLETE"),
        ("ProxyFn0105D3E4", "UPDATE_COMPLETE"),
    ]


def test_events_before_the_last_update_are_excluded():
    """Exclude resource events before the latest stack update."""
    stale = {
        "LogicalResourceId": "OldFn",
        "ResourceStatus": "UPDATE_COMPLETE",
        "Timestamp": dt.datetime(2026, 7, 10, 21, 45, tzinfo=dt.UTC),
    }
    events = [_event("ProxyFn0105D3E4", "UPDATE_COMPLETE"), stale]
    assert select_changed_resources(events, STACK, UPDATED) == [
        ("ProxyFn0105D3E4", "UPDATE_COMPLETE")
    ]


def test_in_progress_events_do_not_count_as_changes():
    events = [_event("ProxyFn0105D3E4", "UPDATE_IN_PROGRESS")]
    assert select_changed_resources(events, STACK, UPDATED) == []


def test_failures_are_reported_not_silently_dropped():
    """A rolled-back resource is a change the operator must see."""
    events = [_event("FoundationalDetector", "CREATE_FAILED")]
    assert select_changed_resources(events, STACK, UPDATED) == [
        ("FoundationalDetector", "CREATE_FAILED")
    ]


def test_metadata_included_on_request():
    events = [_event("CDKMetadata", "UPDATE_COMPLETE")]
    assert select_changed_resources(events, STACK, UPDATED, include_metadata=True) == [
        ("CDKMetadata", "UPDATE_COMPLETE")
    ]


def test_report_calls_out_a_no_op_update_explicitly():
    text = format_report(
        [
            {
                "name": STACK,
                "status": "UPDATE_COMPLETE",
                "last_updated": UPDATED,
                "changed": [],
            }
        ]
    )
    assert "no resources changed" in text
    assert "UPDATE_COMPLETE" in text


def test_report_lists_changed_resources():
    text = format_report(
        [
            {
                "name": "Mlops-Dev-Serving",
                "status": "UPDATE_COMPLETE",
                "last_updated": UPDATED,
                "changed": [("ProxyFn0105D3E4", "UPDATE_COMPLETE")],
            }
        ]
    )
    assert "ProxyFn0105D3E4" in text
    assert "no resources changed" not in text


def test_report_handles_no_matches():
    assert format_report([]) == "No stacks matched."


def test_parser_defaults_to_the_project_stack_prefix():
    args = build_parser().parse_args([])
    assert args.prefix == "Mlops-"
    assert args.include_metadata is False


def _stack(name, updated, created=None, status="UPDATE_COMPLETE"):
    stack = {"StackName": name, "StackStatus": status, "CreationTime": created or updated}
    if updated is not None:
        stack["LastUpdatedTime"] = updated
    return stack


def _cfn_client(stacks, events_by_stack):
    """A CloudFormation client stubbed for both paginated calls collect makes."""
    client = mock.Mock()

    def get_paginator(operation):
        paginator = mock.Mock()
        if operation == "describe_stacks":
            paginator.paginate.return_value = [{"Stacks": stacks}]
        else:
            paginator.paginate.side_effect = lambda StackName: [
                {"StackEvents": events_by_stack.get(StackName, [])}
            ]
        return paginator

    client.get_paginator.side_effect = get_paginator
    return client


def test_collect_filters_by_prefix_and_since_and_sorts_newest_first():
    older = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
    newer = dt.datetime(2026, 7, 24, 21, tzinfo=dt.UTC)
    stacks = [
        _stack("Mlops-Dev-Serving", UPDATED),
        _stack("Mlops-Dev-Monitoring", newer),
        _stack("Mlops-Dev-Ancient", older),  # excluded by --since
        _stack("Unrelated-Stack", newer),  # excluded by --prefix
    ]
    events = {
        "Mlops-Dev-Serving": [_event("ProxyFn0105D3E4", "UPDATE_COMPLETE")],
        "Mlops-Dev-Monitoring": [_event("CDKMetadata", "UPDATE_COMPLETE", minute=59)],
    }
    client = _cfn_client(stacks, events)
    with mock.patch.object(verify_deployment.boto3, "client", return_value=client):
        rows = collect("Mlops-Dev", since=dt.datetime(2026, 7, 20, tzinfo=dt.UTC))

    assert [row["name"] for row in rows] == ["Mlops-Dev-Monitoring", "Mlops-Dev-Serving"]
    # The report lists a metadata-only stack, with nothing changed.
    assert rows[0]["changed"] == []
    assert rows[1]["changed"] == [("ProxyFn0105D3E4", "UPDATE_COMPLETE")]


def test_collect_falls_back_to_creation_time_for_a_never_updated_stack():
    created = dt.datetime(2026, 7, 24, 20, tzinfo=dt.UTC)
    stacks = [_stack("Mlops-Dev-New", None, created=created, status="CREATE_COMPLETE")]
    with mock.patch.object(verify_deployment.boto3, "client", return_value=_cfn_client(stacks, {})):
        rows = collect("Mlops-Dev")

    assert rows[0]["last_updated"] == created
