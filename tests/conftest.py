"""
Test configuration and fixtures for als_tiled.
"""

import pytest


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return {"test": "data"}
