"""Limit how often one caller may reach a costly route.

This module holds no AWS call and no framework import, so the limit is
testable without either. The counter lives in one process. A second backend
container keeps its own count, which is the accepted trade while one instance
serves the site.
"""

import time
from collections import defaultdict, deque


class RateLimiter:
    """Count requests per caller inside a sliding window."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record one request for `key`. Return False when it passes the limit."""
        moment = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and moment - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(moment)
        return True


def caller_address(forwarded_for: str | None, peer: str) -> str:
    """Return the caller address for rate limiting.

    CloudFront appends the viewer address to `X-Forwarded-For`, so the first
    entry names the viewer. The security group admits CloudFront only, so no
    other caller sets that header.
    """
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return peer
