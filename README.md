# ALS Tiled

A tiled-based data management system for the Advanced Light Source (ALS).

## Overview

This project provides a specialized Tiled server configuration for managing scientific data at the Advanced Light Source. It builds on the [Tiled](https://github.com/bluesky/tiled) framework to provide efficient data access and management capabilities.

## Features

- Built on the robust Tiled framework
- Docker containerization for easy deployment
- Support for Python 3.11 and 3.12
- Comprehensive CI/CD pipeline with GitHub Actions
- Pre-configured development environment

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
git clone https://github.com/als-lbl/splash_tiled.git
cd splash_tiled

# Install in development mode
pip install -e .[dev]

# Run the application
als-tiled
```

## Installation

### Requirements

- Python 3.11 or 3.12
- Docker (for containerized deployment)

### From Source

```bash
pip install -e .
```

### Development Installation

```bash
pip install -e .[dev]
```

This installs additional development dependencies including:
- pytest for testing
- black for code formatting
- isort for import sorting
- flake8 for linting
- mypy for type checking
- pre-commit for git hooks

## Development


### Using Pixi for Development

This project supports [Pixi](https://pixi.sh/) for reproducible Python environments. Pixi handles dependency management and environment setup automatically.

#### Setting up with Pixi

1. Install Pixi (if you don't have it):
   ```bash
   curl -sSf https://pixi.sh/install.sh | bash
   # Or see https://pixi.sh/docs/install/ for other methods
   ```
2. Create and activate the development environment:
   ```bash
   pixi install
   pixi shell
   ```
3. (Optional) To update dependencies:
   ```bash
   pixi update
   ```

#### Running Tests with Pixi

```bash
pixi run test
```

#### Running Code Quality Checks with Pixi

```bash
pixi run lint      # Run all linters
pixi run format    # Format code with black and isort
pixi run typecheck # Run mypy type checks
```

You can also run any tool in the environment with `pixi run <tool>` (e.g., `pixi run pytest`).

For more, see the [Pixi documentation](https://pixi.sh/docs/).

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=splash_tiled

# Run specific test file
pytest tests/test_main.py
```

### Code Quality

The project uses several tools to maintain code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking

Run all quality checks:
```bash
black src tests
isort src tests
flake8 src tests
mypy src
```

## Docker

### Building the Image

```bash
docker build -t splash_tiled -f .Containerfile .
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

## CI/CD

The project includes a comprehensive GitHub Actions workflow that:

1. **Linting**: Runs code quality checks (black, isort, flake8, mypy)
2. **Testing**: Executes the test suite across Python 3.11 and 3.12
3. **Building**: Creates Docker images for multiple architectures
4. **Publishing**: Pushes images to GitHub Container Registry

### Workflow Triggers

- Push to `main` or `develop` branches
- Pull requests to `main`
- Release publications

### Container Registry

Docker images are automatically published to:
```
ghcr.io/als-computing/splash_tiled
```

## Configuration

The application can be configured through environment variables:

- `TILED_SERVER_ENABLE_ORIGINS`: Configure CORS origins
- `PYTHONPATH`: Python module search path

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
