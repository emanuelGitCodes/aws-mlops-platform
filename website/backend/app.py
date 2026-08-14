"""Serve the website API with FastAPI.

This module holds routing, validation, and status codes. `services.py` holds
every AWS call. The React frontend calls these routes; it is a separate
container in `local/compose.yaml` and a separate build in the deployed shape.

The request model comes from `src.common.schema`, so the API rejects exactly
what the pipeline and the inference proxy reject.
"""

from typing import Annotated, Any

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

from src.common.events import log_event
from src.common.schema import CustomerRecord, format_validation_error
from website.backend import services
from website.backend.rate_limit import RateLimiter, caller_address
from website.backend.settings import Settings, load_settings

settings: Settings = load_settings()
limiter = RateLimiter(settings.rate_limit_per_minute)
results_cache = services.ResultsCache(settings.results_cache_seconds)

app = FastAPI(
    title="Churn model demo",
    summary="Read the model contract, the newest evaluation, and one prediction.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


class Subscription(BaseModel):
    """One mailing-list signup.

    The pattern accepts one address shape and needs no `email-validator`
    dependency. The list confirms nothing by mail, so a stricter grammar buys
    nothing here.
    """

    email: str = Field(pattern=r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")

    @field_validator("email", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> object:
        """Trim and lower the address before the pattern reads it.

        A reader types a trailing space and an initial capital. Both are the
        same subscriber, so the key MUST be one string.
        """
        return value.strip().lower() if isinstance(value, str) else value


@app.exception_handler(services.ServiceError)
async def _service_error(request: Request, error: services.ServiceError) -> JSONResponse:
    """Answer a failed backing service with 502 rather than a stack trace."""
    return JSONResponse(status_code=502, content={"error": str(error)})


@app.exception_handler(Exception)
async def _unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Answer every request. An unhandled error would otherwise close the socket."""
    log_event("website_request_failed", reason=type(error).__name__)
    return JSONResponse(status_code=500, content={"error": "the website failed to answer"})


@app.get("/api/health")
async def health() -> dict[str, bool]:
    """Report that the process serves requests."""
    return {"ok": True}


@app.get("/api/schema")
async def schema() -> dict[str, Any]:
    """Return the model input contract."""
    return services.schema_payload()


@app.get("/api/results")
async def results() -> dict[str, Any]:
    """Return the newest evaluation report."""
    return services.latest_results(settings, results_cache)


@app.post("/api/predict")
async def predict(request: Request, record: Annotated[dict[str, Any], Body()]) -> Any:
    """Validate one record, then forward it to the signed prediction API."""
    caller = caller_address(
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else "unknown",
    )
    if not limiter.allow(caller):
        return JSONResponse(
            status_code=429, content={"error": "too many predictions; wait one minute"}
        )
    try:
        validated = CustomerRecord(**record)
    except ValidationError as error:
        return JSONResponse(status_code=400, content={"error": format_validation_error(error)})
    return services.predict(settings, validated.model_dump(exclude_none=True))


@app.post("/api/subscribe")
async def subscribe(body: Annotated[dict[str, Any], Body()]) -> Any:
    """Store one address and answer with the time it first arrived.

    Both write routes validate here rather than in the signature, so a bad
    request gets one status code and one error shape across the API.
    """
    try:
        subscription = Subscription(**body)
    except ValidationError as error:
        return JSONResponse(status_code=400, content={"error": format_validation_error(error)})
    created_at = services.subscribe(settings, subscription.email)
    return {"subscribed": True, "created_at": created_at}
