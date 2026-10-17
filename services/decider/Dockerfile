# syntax=docker/dockerfile:1.7
# Build with --platform linux/arm64 and the isolated decider_models context.
FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS builder
RUN apt-get update && apt-get install --no-install-recommends -y git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY services/decider/requirements-linux-arm64.lock ./requirements.lock
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock

FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/models/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
    DECIDER_CHECKPOINT=/models/decider-2b DECIDER_DEVICE=cpu DECIDER_HOST=0.0.0.0 \
    OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app && chown app:app /tmp && chmod 0700 /tmp
COPY --from=builder /opt/venv /opt/venv
COPY --from=decider_models / /models/
COPY services/decider/model.json services/decider/serve.py /app/services/decider/
COPY LICENSE THIRD_PARTY_NOTICES.md /app/notices/
WORKDIR /app
RUN find / -xdev -type f -perm /6000 -exec chmod a-s {} +
USER 10001:10001
VOLUME ["/tmp"]
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=4)"]
CMD ["python", "/app/services/decider/serve.py"]
