FROM python:slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEVY_SYNC_CONFIG_DIR=/config

WORKDIR /app

COPY pyproject.toml README.md ./
COPY hevy_sync ./hevy_sync

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

RUN mkdir -p /config /tmp/hevy-sync

ENTRYPOINT ["hevy-sync"]
