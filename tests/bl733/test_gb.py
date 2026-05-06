import numpy as np
import pytest
import pytest_asyncio
from tiled.client import Context, from_context
from tiled.client.register import register
from tiled.server.app import build_app_from_config

from splash_tiled.bl733.adapters.gb import (
    PILATUS_2M_PIXELS_X,
    PILATUS_2M_PIXELS_Y,
    GeneralBinaryPilatus2MAdapter,
)

GB_ADAPTER = "splash_tiled.bl733.adapters.gb:GeneralBinaryPilatus2MAdapter"
GB_MIMETYPE = "application/x-gb"


def _tiled_config(tmp_path):
    return {
        "trees": [
            {
                "tree": "catalog",
                "path": "/",
                "args": {
                    "uri": str(tmp_path / "catalog.db"),
                    "readable_storage": [str(tmp_path)],
                    "init_if_not_exists": True,
                    "adapters_by_mimetype": {GB_MIMETYPE: GB_ADAPTER},
                },
            }
        ],
        "file_extensions": {"gb": GB_MIMETYPE},
    }


@pytest_asyncio.fixture
async def gb_client(tmp_path, bl733_gb_path):
    with Context.from_app(build_app_from_config(_tiled_config(tmp_path))) as context:
        client = from_context(context)
        await register(
            client,
            tmp_path,
            adapters_by_mimetype={GB_MIMETYPE: GB_ADAPTER},
            mimetypes_by_file_ext={".gb": GB_MIMETYPE},
        )
        yield client


@pytest.mark.asyncio
async def test_gb_reads_array(gb_client):
    """Array returned by the tiled client matches the data written to disk."""
    expected = np.arange(
        PILATUS_2M_PIXELS_X * PILATUS_2M_PIXELS_Y, dtype="<f4"
    ).reshape(PILATUS_2M_PIXELS_Y, PILATUS_2M_PIXELS_X)
    result = gb_client["scan_name_sfloat_2m"].read()
    np.testing.assert_array_equal(result, expected)


@pytest.mark.asyncio
async def test_gb_metadata_includes_edf_fields(gb_client):
    """EDF header fields from the hi/lo companions appear
    in the tiled entry metadata."""
    metadata = gb_client["scan_name_sfloat_2m"].metadata
    assert metadata["count_time"] == "0.100000001"
    assert metadata["ByteOrder"] == "LowByteFirst"
    assert metadata["Dim_1"] == "1475"
    assert metadata["Dim_2"] == "1679"
    # hi is acquired after lo; the later date is selected
    assert metadata["Date"] == "2025-10-29T20:15:23"


@pytest.mark.asyncio
async def test_gb_metadata_includes_txt_fields(gb_client):
    """Companion .txt fields from the hi/lo EDF companions appear
    in the tiled entry metadata."""
    metadata = gb_client["scan_name_sfloat_2m"].metadata
    assert metadata["Exposure time s"] == "0.100"
    assert metadata["Normalize by"] == "Diode"
    assert metadata["PI"] == "PILastname"


@pytest.mark.asyncio
async def test_gb_missing_edf(tmp_path):
    """GB file registers successfully when its companion EDF files are absent."""
    gb_file = tmp_path / "scan_name_sfloat_2m.gb"
    np.arange(PILATUS_2M_PIXELS_X * PILATUS_2M_PIXELS_Y, dtype="<f4").tofile(gb_file)

    with Context.from_app(build_app_from_config(_tiled_config(tmp_path))) as context:
        client = from_context(context)
        await register(
            client,
            tmp_path,
            adapters_by_mimetype={GB_MIMETYPE: GB_ADAPTER},
            mimetypes_by_file_ext={".gb": GB_MIMETYPE},
        )
        result = client["scan_name_sfloat_2m"].read()
        assert result.shape == (PILATUS_2M_PIXELS_Y, PILATUS_2M_PIXELS_X)
        assert client["scan_name_sfloat_2m"].metadata.get("Date") is None


def test_gb_wrong_size(tmp_path):
    """Adapter raises ValueError when the file has the wrong number of pixels."""
    bad_path = tmp_path / "bad_sfloat_2m.gb"
    np.array([1.0, 2.0], dtype="<f4").tofile(bad_path)
    with pytest.raises(ValueError, match="does not match expected size"):
        GeneralBinaryPilatus2MAdapter.from_uris(bad_path.as_uri())


def test_combine_matching_values():
    """Keys with identical values in both dicts are kept as-is."""
    result = GeneralBinaryPilatus2MAdapter._combine_metadata(
        {"a": 1, "b": 2}, {"a": 1, "b": 2}
    )
    assert result == {"a": 1, "b": 2}


def test_combine_differing_values():
    """Keys with different values are split into _hi and _lo variants."""
    result = GeneralBinaryPilatus2MAdapter._combine_metadata(
        {"key": "hi_val"}, {"key": "lo_val"}
    )
    assert result == {"key_hi": "hi_val", "key_lo": "lo_val"}


def test_combine_unique_keys():
    """Keys present in only one dict get a _hi or _lo suffix (None != value)."""
    result = GeneralBinaryPilatus2MAdapter._combine_metadata(
        {"only_hi": 1}, {"only_lo": 2}
    )
    assert result["only_hi_hi"] == 1
    assert result["only_lo_lo"] == 2


def test_combine_mixed():
    """Mixed case: some keys match, some differ, some are unique."""
    hi = {"shared_same": "x", "shared_diff": "a", "only_hi": 1}
    lo = {"shared_same": "x", "shared_diff": "b", "only_lo": 2}
    result = GeneralBinaryPilatus2MAdapter._combine_metadata(hi, lo)
    assert result["shared_same"] == "x"
    assert result["shared_diff_hi"] == "a"
    assert result["shared_diff_lo"] == "b"
    assert result["only_hi_hi"] == 1
    assert result["only_lo_lo"] == 2
