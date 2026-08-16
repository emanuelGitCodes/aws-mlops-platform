# The build context is the repository root, because this image needs two
# directories: `website/backend/` and `src/common/`. The backend MUST import
# the feature and schema contract from `src.common`, never restate it.
#
# `.dockerignore` at the root keeps the context small. Add any new large
# directory there rather than letting it reach the daemon.
FROM python:3.12-slim

WORKDIR /app

COPY website/backend/requirements.txt ./backend-requirements.txt
RUN pip install --no-cache-dir -r backend-requirements.txt

# `src/common` holds the shared contract. Nothing else from `src/` ships.
COPY src/__init__.py ./src/__init__.py
COPY src/common/ ./src/common/
COPY website/__init__.py ./website/__init__.py
COPY website/backend/ ./website/backend/

# The canonical request payloads seed the prediction form. The backend reads
# these files rather than restating one record.
COPY sample.json sample-high-risk.json ./

# A user without privileges cannot bind a port below 1024. The container
# listens on 8080 and the host publishes it as port 80.
RUN useradd --create-home --uid 10001 website
USER website
ENV PORT=8080
EXPOSE 8080

# `--proxy-headers` makes uvicorn read `X-Forwarded-For`, which the rate
# limiter uses to tell one viewer from another behind CloudFront.
CMD ["sh", "-c", "uvicorn website.backend.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
