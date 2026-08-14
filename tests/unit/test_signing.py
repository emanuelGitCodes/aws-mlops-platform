import json
from unittest import mock

import pytest

from src.common import signing
from tests.unit.conftest import VALID
from tests.unit.conftest import signing_session as _session


def test_signed_headers_carry_the_credential_scope():
    """Sign the request under the execute-api service and the session region."""
    headers = signing.sign_headers("https://x/predict", b"{}", _session())

    assert "AWS4-HMAC-SHA256" in headers["Authorization"]
    assert "/us-east-1/execute-api/aws4_request" in headers["Authorization"]
    assert headers["Content-Type"] == "application/json"


def test_an_explicit_region_overrides_the_session_region():
    """Prefer the caller's region for the credential scope."""
    headers = signing.sign_headers("https://x/predict", b"{}", _session(), region="eu-west-1")

    assert "/eu-west-1/execute-api/aws4_request" in headers["Authorization"]


def test_a_changed_body_changes_the_signature():
    """Cover the body with the signature."""
    session = _session()
    first = signing.sign_headers("https://x/predict", b"{}", session)
    second = signing.sign_headers("https://x/predict", b'{"a": 1}', session)

    assert first["Authorization"] != second["Authorization"]


def test_signing_without_credentials_names_the_cause():
    """Report missing credentials before SigV4 signing."""
    session = _session()
    session.get_credentials.return_value = None
    with pytest.raises(signing.SigningError, match="credentials"):
        signing.sign_headers("https://x/p", b"{}", session)


def test_signing_without_a_region_names_the_cause():
    """Require a region for the SigV4 credential scope."""
    session = _session()
    session.region_name = None
    with pytest.raises(signing.SigningError, match="region"):
        signing.sign_headers("https://x/p", b"{}", session)


def test_post_prediction_signs_and_parses_the_response():
    """Send the signed body and return the parsed payload."""
    response = mock.MagicMock()
    response.read.return_value = json.dumps({"churn_probability": 0.25, "churn": False}).encode()
    response.__enter__.return_value = response

    with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
        payload = signing.post_prediction("https://x/predict", VALID, _session())

    assert payload == {"churn_probability": 0.25, "churn": False}
    request = urlopen.call_args.args[0]
    assert request.method == "POST"
    assert request.data == json.dumps(VALID).encode()
    assert "Authorization" in {key.title(): value for key, value in request.headers.items()}
