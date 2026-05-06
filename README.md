# ALS Tiled

A tiled-based data management system for the Advanced Light Source (ALS).

## Overview

This project provides a specialized Tiled server configuration for managing scientific data at the Advanced Light Source. It builds on the [Tiled](https://github.com/bluesky/tiled) framework to provide efficient data access and management capabilities.

## Features

- Built on the robust Tiled framework
- Docker containerization for easy deployment
- Support for Python 3.13
- Comprehensive CI/CD pipeline with GitHub Actions
- Reproducible development environment managed with [Pixi](https://pixi.sh/)

## Quick Start

### Using Docker

```bash
# Build the Docker image
docker build -t splash_tiled -f Containerfile .

# Run the container
docker run -p 8000:8000 splash_tiled
```

### Local Development

```bash
# Clone the repository
git clone https://github.com/als-computing/splash_tiled.git
cd splash_tiled

# Install and activate the environment
pixi install
pixi shell

# Run tests
pixi run test
```

## Installation

### Requirements

- [Pixi](https://pixi.sh/) (recommended)
- Python 3.13
- Docker (for containerized deployment)

### With Pixi (recommended)

```bash
# Install Pixi if needed
curl -sSf https://pixi.sh/install.sh | bash

# Install all dependencies
pixi install
```

Pixi manages all dependencies (including Python 3.13) and installs the package in editable mode automatically.

## Development

This project uses [Pixi](https://pixi.sh/) for reproducible environments.

### Setup

```bash
# Install Pixi if you don't have it
curl -sSf https://pixi.sh/install.sh | bash

# Install the environment
pixi install

# Start a shell in the environment
pixi shell
```

To update dependencies:
```bash
pixi update
```

### Running Tests

```bash
# Run all tests with coverage
pixi run test

# Or run pytest directly inside a pixi shell
pytest tests/test_specific.py
```

### Code Quality

The project uses Black, isort, flake8, and mypy for code quality.

```bash
pixi run lint      # Check formatting, imports, style, and types
pixi run format    # Auto-format code with black and isort
```

For more, see the [Pixi documentation](https://pixi.sh/docs/).

## Docker

### Building the Image

```bash
docker build -t splash_tiled -f Containerfile .
```

### Running the Container

```bash
# Basic run
docker run -p 8000:8000 splash_tiled

# With environment variables
docker run -p 8000:8000 -e TILED_SERVER_ENABLE_ORIGINS=* splash_tiled

# With volume mounting for data
docker run -p 8000:8000 -v /path/to/data:/data splash_tiled
```

### Developer Compose Stack

For access-control testing, use the compose stack in
`docker-compose.dev.yaml`. It starts:

- `tiled`: Tiled server from the project `Containerfile`
- `sync-worker`: ESAF + staff sync loop from the same image, running on an interval
- `seed-data`: one-shot service that creates a `beamlines` container with
   beamline containers, ESAF containers, and array nodes with different
   `access_blob.tags`

Start server + sync worker:

```bash
docker compose -f docker-compose.dev.yaml up --build -d tiled sync-worker
```

Seed the catalog data:

```bash
docker compose -f docker-compose.dev.yaml run --rm seed-data
```

Adjust sync cadence and target beamlines via environment variables in
`docker-compose.dev.yaml`:

- `SYNC_CRON` (for example: `*/5 * * * *`)
- `BEAMLINES` (comma-separated list or `all`)

Stop everything:

```bash
docker compose -f docker-compose.dev.yaml down
```

## CI/CD

The project includes a comprehensive GitHub Actions workflow that:

1. **Linting**: Runs code quality checks (black, isort, flake8, mypy)
2. **Testing**: Executes the test suite with Python 3.13
3. **Building**: Creates Docker images for multiple architectures
4. **Publishing**: Pushes images to GitHub Container Registry

### Workflow Triggers

- Push to `main` or `develop` branches
- Pull requests to `main`
- Release publications

### Container Registry

Docker images are automatically published to:
```
ghcr.io/als-lbl/splash_tiled
```

## Configuration

The application can be configured through environment variables:

- `TILED_SERVER_ENABLE_ORIGINS`: Configure CORS origins
- `PYTHONPATH`: Python module search path

## ESAF Sync Script

The repository includes a small CLI for loading ESAFs into SQLite.

```bash
als-esaf-sync \
   --beamline 7.0.2 \
   --beamline 12.3.2 \
   --db-path ./esafs.db
```

The script stores data in four tables:

- `beamline` for sync metadata per beamline
- `user` for PI, experimental lead, and participant identities
- `esaf` for the ESAF record itself
- `esaf_user` for user-to-ESAF roles

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run the test suite
5. Submit a pull request

### Code Style

This project follows:
- PEP 8 style guidelines
- Black code formatting
- Import sorting with isort
- Type hints where appropriate

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Support

For support and questions, please open an issue on the GitHub repository or contact the ALS team at contact@als.lbl.gov.

## Related Projects

- [Tiled](https://github.com/bluesky/tiled) - The underlying framework
- [Bluesky](https://github.com/bluesky/bluesky) - Data acquisition and analysis framework# splash_tiled
