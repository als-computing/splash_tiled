FROM ghcr.io/bluesky/tiled:0.2.8 AS base

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
COPY --chown=app:app src/splash_tiled/bl733/adapters/edf.py /tiled_deploy/config/custom/edf.py
COPY --chown=app:app src/splash_tiled/bl733/adapters/gb.py /tiled_deploy/config/custom/gb.py
