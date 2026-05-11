FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEVY_SYNC_CONFIG_DIR=/config

WORKDIR /app

COPY pyproject.toml README.md NOTICE.md ./
COPY hevy_sync ./hevy_sync

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

RUN groupadd --system --gid 10001 hevy-sync \
    && useradd --system --uid 10001 --gid hevy-sync --home-dir /nonexistent --shell /usr/sbin/nologin hevy-sync \
    && mkdir -p /config /tmp/hevy-sync \
    && chown -R hevy-sync:hevy-sync /app /config /tmp/hevy-sync

USER 10001:10001

CMD ["hevy-sync"]
