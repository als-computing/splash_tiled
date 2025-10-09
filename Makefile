# Makefile for ALS Tiled project

.PHONY: help install install-dev test lint format clean build docker-build docker-run

help:
	@echo "Available commands:"
	@echo "  install      Install the package"
	@echo "  install-dev  Install the package in development mode with dev dependencies"
	@echo "  test         Run tests"
	@echo "  lint         Run linting checks"
	@echo "  format       Format code with black and isort"
	@echo "  clean        Clean build artifacts"
	@echo "  build        Build the package"
	@echo "  docker-build Build Docker image"
	@echo "  docker-run   Run Docker container"

install:
	pip install -e .

install-dev:
	pip install -e .[dev]
	pre-commit install

test:
	pytest --cov=als_tiled --cov-report=term-missing

lint:
	flake8 src tests
	black --check src tests
	isort --check-only src tests
	mypy src

format:
	black src tests
	isort src tests

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:
	python -m build

docker-build:
	docker build -t als_tiled .

docker-run:
	docker run -p 8000:8000 als_tiled
