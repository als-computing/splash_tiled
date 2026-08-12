FROM ghcr.io/bluesky/tiled:0.2.15 AS base

# Rebuild tiled to include inherited access control changes, which are needed for the ALS Computing Hub. Won't be needed once those changes are merged into the main tiled branch and included in a release.

FROM base AS build-tiled

USER root
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN git clone --branch inherited_access_control https://github.com/als-computing/tiled.git /tmp/tiled
WORKDIR /tmp/tiled
RUN pip wheel --no-deps -w /tmp/wheels .

FROM base

# uv is a statically-linked Rust binary — no shared-library mprotect call,
# so it works under rootless Podman where `pip` (glibc RELRO) fails.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy tiled wheel from build stage and install as root (will override base image's tiled)
USER root
COPY --from=build-tiled /tmp/wheels/*.whl /tmp/
RUN uv pip install --python /app/bin/python --no-cache /tmp/*.whl

USER app
ENV PATH=/app/bin:$PATH
ENV PYTHONPATH=/app/src:/tiled_deploy/config

COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app src/ ./src/
RUN uv pip install --python /app/bin/python --no-cache ".[bl733]"
COPY --chown=app:app scripts/ ./scripts/
