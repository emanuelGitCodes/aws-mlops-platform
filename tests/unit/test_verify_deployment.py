"""Unit tests for the deployment verification CLI.

The AWS calls are deliberately thin wrappers; the logic worth testing is
the event filtering, which is what distinguishes a real resource change
from a stack that merely reached UPDATE_COMPLETE.
"""

import datetime as dt

from scripts.verify_deployment import (
    build_parser,
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
    """The 2026-07-24 Monitoring case: UPDATE_COMPLETE, nothing changed.

    CloudFormation resolved the partition-agnostic ARN rewrite to the same
    policy document and skipped the IAM resource, so the stack succeeded
    while touching nothing. Reporting that as a policy update was the
    original error this tool exists to prevent.
    """
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
    """Only the most recent update counts; older history must not leak in."""
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
