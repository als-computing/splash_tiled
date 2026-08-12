FROM ghcr.io/bluesky/tiled:0.2.15 AS base

# uv is a statically-linked Rust binary — no shared-library mprotect call,
# so it works under rootless Podman where `pip` (glibc RELRO) fails.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

USER app
ENV PATH=/app/bin:$PATH
ENV PYTHONPATH=/app/src:/tiled_deploy/config

COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app src/ ./src/
RUN uv pip install --python /app/bin/python --no-cache ".[bl733]"
COPY --chown=app:app scripts/ ./scripts/
