import pytest

from tests.bl11012.samples import make_fits


@pytest.fixture
def bl11012_fits_path(tmp_path):
    """Write a synthetic BL11.0.1.2 frame to tmp_path/scan_name.fits."""
    return make_fits(tmp_path, filename="scan_name.fits")
