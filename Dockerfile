FROM ghcr.io/bluesky/tiled:0.1.6 AS base

USER root

# git is used only for the pip install git+https:// below and can be
# removed once that is no longer used.
RUN apt-get update && apt-get install -y postgresql-client git && rm -rf /var/lib/apt/lists/*

USER app

COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app src/ ./src/
RUN python -m ensurepip
RUN python -m pip install --upgrade --no-cache-dir .
