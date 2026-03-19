"""
Test configuration and fixtures for als_tiled.
"""

import pytest


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return {"test": "data"}
