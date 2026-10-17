# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS builder
WORKDIR /build
COPY backend/requirements-linux-arm64.lock ./requirements.lock
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock
COPY backend/pyproject.toml ./
COPY backend/clearance_gap ./clearance_gap
RUN /opt/venv/bin/pip install --no-cache-dir --no-deps .

FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH" SCENARIOS_PATH=/app/scenarios
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app && chown app:app /tmp && chmod 0700 /tmp
COPY --from=builder /opt/venv /opt/venv
COPY scenarios /app/scenarios
WORKDIR /app
RUN find / -xdev -type f -perm /6000 -exec chmod a-s {} +
USER 10001:10001
VOLUME ["/tmp"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD ["uvicorn", "clearance_gap.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
