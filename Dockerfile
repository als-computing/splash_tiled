FROM ghcr.io/bluesky/tiled:0.1.6 AS base

USER root

### PAM Radius Authentication
# add the following lines to your docker-compose.yml
    # volumes:
    #   # Mount RADIUS and PAM configuration from host
    #   - /etc/pam.d:/etc/pam.d:ro
    #   - /etc/raddb:/etc/raddb:ro
    #   - /etc/pam_radius_auth.conf:/etc/pam_radius_auth.conf:ro

# libpam0g-dev is required for pamela (PAM authentication)
RUN apt-get update && apt-get install -y libpam0g-dev libpam-radius-auth && rm -rf /var/lib/apt/lists/*

USER app

COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app src/ ./src/
RUN python -m ensurepip
RUN python -m pip install --upgrade --no-cache-dir .[pam]
