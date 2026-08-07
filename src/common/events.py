"""Structured stdout event logging shared by Lambdas and pipeline steps.

This module exists because ``schema.py`` holds the data contract and
``features.py`` holds the feature contract. Neither is a home for a runtime
helper. This is the one place for the one-JSON-line-per-event convention.
"""

import json

__all__ = ["log_event"]


def log_event(event: str, **fields: object) -> None:
    """Emit one structured JSON event line to stdout (CloudWatch Logs)."""
    print(json.dumps({"event": event, **fields}))
