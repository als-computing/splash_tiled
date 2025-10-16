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
docker build -t als_tiled -f Containerfile .

# Run the container
docker run -p 8000:8000 als_tiled
```

### Local Development

```bash
# Clone the repository
git clone https://github.com/als-lbl/als_tiled.git
cd als_tiled

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

### Setting up the Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/als-lbl/als_tiled.git
   cd als_tiled
   ```

2. Install development dependencies:
   ```bash
   pip install -e .[dev]
   ```

3. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=als_tiled

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
docker build -t als_tiled -f .Containerfile .
```

### Running the Container

```bash
# Basic run
docker run -p 8000:8000 als_tiled

# With environment variables
docker run -p 8000:8000 -e TILED_SERVER_ENABLE_ORIGINS=* als_tiled

# With volume mounting for data
docker run -p 8000:8000 -v /path/to/data:/data als_tiled
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
ghcr.io/als-lbl/als_tiled
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
- [Bluesky](https://github.com/bluesky/bluesky) - Data acquisition and analysis framework# als_tiled
