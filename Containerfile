FROM ghcr.io/bluesky/tiled:0.2.8 AS base

USER root

RUN apt-get update && rm -rf /var/lib/apt/lists/*

USER app

COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app src/ ./src/
RUN python -m ensurepip
RUN python -m pip install --upgrade --no-cache-dir .
