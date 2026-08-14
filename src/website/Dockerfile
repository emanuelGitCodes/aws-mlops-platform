# The build context is `src/`, so this image copies `src/common` next to
# `src/website`. The backend MUST import the feature and schema contract from
# `src.common`, never restate it.
FROM python:3.12-slim

WORKDIR /app

COPY website/requirements.txt ./website-requirements.txt
RUN pip install --no-cache-dir -r website-requirements.txt

COPY __init__.py ./src/__init__.py
COPY common/ ./src/common/
COPY website/ ./src/website/

# A user without privileges cannot bind a port below 1024. The container
# listens on 8080 and the host publishes it as port 80.
RUN useradd --create-home --uid 10001 website
USER website
ENV PORT=8080
EXPOSE 8080

# `--proxy-headers` makes uvicorn read `X-Forwarded-For`, which the rate
# limiter uses to tell one viewer from another behind CloudFront.
CMD ["sh", "-c", "uvicorn src.website.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
