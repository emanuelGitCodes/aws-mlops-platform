import pytest

from website.backend.rate_limit import RateLimiter, caller_address


def test_the_limiter_counts_inside_the_window():
    """Allow the configured count, then refuse."""
    limiter = RateLimiter(2, window_seconds=60.0)

    assert limiter.allow("1.2.3.4", now=0.0) is True
    assert limiter.allow("1.2.3.4", now=1.0) is True
    assert limiter.allow("1.2.3.4", now=2.0) is False
    # A second caller keeps its own count.
    assert limiter.allow("5.6.7.8", now=2.0) is True
    # The window moves past the first two requests.
    assert limiter.allow("1.2.3.4", now=61.0) is True


def test_the_limiter_reads_the_clock_by_default():
    """Use the monotonic clock when the caller passes no time."""
    limiter = RateLimiter(1)

    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False


@pytest.mark.parametrize(
    ("forwarded", "expected"),
    [("9.9.9.9, 1.1.1.1", "9.9.9.9"), (None, "10.0.0.1"), ("", "10.0.0.1")],
)
def test_the_caller_address_prefers_the_forwarded_viewer(forwarded, expected):
    """Read the viewer address CloudFront puts first."""
    assert caller_address(forwarded, "10.0.0.1") == expected
