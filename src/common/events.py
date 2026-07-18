"""Structured stdout event logging shared by Lambdas and pipeline steps.

New module because neither ``schema.py`` (data contract) nor ``features.py``
(feature contract) is a home for runtime helpers; this is the single place
for the one-JSON-line-per-event convention used across the platform.
"""

import json

__all__ = ["log_event"]


def log_event(event: str, **fields: object) -> None:
    """Emit one structured JSON event line to stdout (CloudWatch Logs)."""
    print(json.dumps({"event": event, **fields}))
