#!/usr/bin/env python3
"""Report what a CloudFormation deployment actually changed.

This module exists because nothing else in the repo queries CloudFormation. The
other scripts call SageMaker, S3, or the API.

Stack status does not answer "what changed". A stack reaches
``UPDATE_COMPLETE`` even when CloudFormation resolved the new template to a
no-op and updated no resource. That happened on 2026-07-24: a partition-agnostic
ARN rewrite produced a diff, but CloudFormation skipped both IAM policies,
because the resolved documents were identical. Only resource-level events
answer the question.

The console holds the same trap. The stack list's default **Created time**
column never changes on update, so it cannot tell you whether a stack was
deployed today. **Updated time** and the Events tab can.

Run this with a profile that can enumerate stacks. ``describe_stacks`` with no
``StackName`` is authorized as ``cloudformation:ListStacks``. The deploy
identity ``mlops-deployer`` does not have it: that identity can create the
change set that updates a stack, but it cannot list stacks afterwards, so it
fails here with AccessDenied. Use ``mlops-security-auditor``, the read-only
identity for this. ``aws-admin`` also works.

Prefer ``AWS_PROFILE=mlops-security-auditor make verify-deploy
SINCE=<YYYY-MM-DD>``. The commands below are the same call with the ``dev``
extra that supplies boto3:

    uv run --locked --extra dev python scripts/verify_deployment.py --prefix Mlops-Dev
    uv run --locked --extra dev python scripts/verify_deployment.py --since 2026-07-24
"""

import argparse
import datetime as dt
import sys
from typing import Any

import boto3

# These are not real resources. They are the stack's own lifecycle events and
# the metadata resource CDK rewrites on nearly every deployment.
_STACK_LEVEL_STATUSES = ("REVIEW_IN_PROGRESS",)
CDK_METADATA = "CDKMetadata"


def select_changed_resources(
    events: list[dict[str, Any]],
    stack_name: str,
    since: dt.datetime,
    include_metadata: bool = False,
) -> list[tuple[str, str]]:
    """Return the resources with a terminal event at or after ``since``.

    This drops the stack's own lifecycle events. It keeps only completed and
    failed states, so in-progress events do not double-count. It also drops
    ``CDKMetadata`` unless the caller asks for it, because that resource
    changes on nearly every deploy.
    """
    seen: dict[str, str] = {}
    for event in events:
        timestamp = event.get("Timestamp")
        if timestamp is None or timestamp < since:
            continue
        logical_id = event.get("LogicalResourceId", "")
        status = event.get("ResourceStatus", "")
        if logical_id == stack_name or status in _STACK_LEVEL_STATUSES:
            continue
        if logical_id == CDK_METADATA and not include_metadata:
            continue
        if not (status.endswith("_COMPLETE") or status.endswith("_FAILED")):
            continue
        # Events arrive newest-first. Keep the newest terminal status.
        seen.setdefault(logical_id, status)
    return sorted(seen.items())


def format_report(rows: list[dict[str, Any]]) -> str:
    """Render one block per stack. Each block gives the update time and the
    resources that changed."""
    if not rows:
        return "No stacks matched."
    lines: list[str] = []
    for row in rows:
        updated = row["last_updated"]
        stamp = updated.isoformat() if updated else "never updated"
        lines.append(f"{row['name']}  [{row['status']}]")
        lines.append(f"  last updated: {stamp}")
        changed = row["changed"]
        if changed:
            for logical_id, status in changed:
                lines.append(f"    {status:<24} {logical_id}")
        else:
            lines.append("    (no resources changed -- metadata-only or no-op update)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _stack_events(client: Any, stack_name: str) -> list[dict[str, Any]]:
    paginator = client.get_paginator("describe_stack_events")
    events: list[dict[str, Any]] = []
    for page in paginator.paginate(StackName=stack_name):
        events.extend(page["StackEvents"])
    return events


def collect(
    prefix: str,
    region: str | None = None,
    since: dt.datetime | None = None,
    include_metadata: bool = False,
) -> list[dict[str, Any]]:
    """Describe the matching stacks and the resources each last update
    touched."""
    client = boto3.client("cloudformation", region_name=region)
    rows: list[dict[str, Any]] = []
    for page in client.get_paginator("describe_stacks").paginate():
        for stack in page["Stacks"]:
            name = stack["StackName"]
            if not name.startswith(prefix):
                continue
            last_updated = stack.get("LastUpdatedTime") or stack["CreationTime"]
            if since is not None and last_updated < since:
                continue
            rows.append(
                {
                    "name": name,
                    "status": stack["StackStatus"],
                    "last_updated": last_updated,
                    "changed": select_changed_resources(
                        _stack_events(client, name),
                        name,
                        last_updated,
                        include_metadata,
                    ),
                }
            )
    rows.sort(key=lambda r: r["last_updated"], reverse=True)
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        default="Mlops-",
        help="only report stacks whose name starts with this (default: Mlops-)",
    )
    parser.add_argument("--region", default=None, help="AWS region")
    parser.add_argument(
        "--since",
        default=None,
        metavar="YYYY-MM-DD",
        help="only report stacks last updated on or after this date (UTC)",
    )
    parser.add_argument(
        "--include-metadata",
        action="store_true",
        help="also list CDKMetadata, which changes on nearly every deploy",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    since = None
    if args.since:
        since = dt.datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    rows = collect(args.prefix, args.region, since, args.include_metadata)
    sys.stdout.write(format_report(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
