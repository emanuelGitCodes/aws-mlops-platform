"""Emit structured stdout events from Lambdas and pipeline steps."""

import json

__all__ = ["log_event"]


def log_event(event: str, **fields: object) -> None:
    """Emit one structured JSON event line to stdout (CloudWatch Logs)."""
    print(json.dumps({"event": event, **fields}))
