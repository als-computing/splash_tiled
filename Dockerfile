FROM ghcr.io/bluesky/tiled:0.1.6 AS base

USER root

# git is used only for the pip install git+https:// below and can be
# removed once that is no longer used.
# libpam0g-dev is required for pamela (PAM authentication)
RUN apt-get update && apt-get install -y libpam0g-dev && rm -rf /var/lib/apt/lists/*

USER app

COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app src/ ./src/
RUN python -m ensurepip
RUN python -m pip install --upgrade --no-cache-dir .[pam]
