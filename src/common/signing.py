"""Sign requests to the deployed inference API with SigV4.

The `/predict` method requires SigV4 and `execute-api:Invoke`. Two callers
sign requests: `scripts/evaluate_api.py` from a workstation profile, and
`src/website/server.py` from the instance role.
"""

import json
import urllib.request
from typing import Any

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# API Gateway signs under this service name.
SIGNING_SERVICE = "execute-api"


class SigningError(RuntimeError):
    """Raised when the caller cannot sign a request."""


def sign_headers(
    api_url: str, body: bytes, session: boto3.Session, region: str | None = None
) -> dict[str, str]:
    """Return the SigV4 headers for one POST to the API.

    The signature covers the body. A caller MUST sign the exact bytes it
    sends.
    """
    credentials = session.get_credentials()
    if credentials is None:
        raise SigningError("no AWS credentials found for signing")
    signing_region = region or session.region_name
    if not signing_region:
        raise SigningError("no AWS region found for signing")
    request = AWSRequest(
        method="POST",
        url=api_url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(credentials, SIGNING_SERVICE, signing_region).add_auth(request)
    return dict(request.headers)


def post_prediction(
    api_url: str,
    record: dict[str, Any],
    session: boto3.Session,
    region: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST one record to /predict and return the parsed JSON response."""
    body = json.dumps(record).encode()
    request = urllib.request.Request(
        api_url,
        data=body,
        headers=sign_headers(api_url, body, session, region),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload: dict[str, Any] = json.loads(response.read())
    return payload
