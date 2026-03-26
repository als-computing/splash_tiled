import numpy as np
import pytest
import pytest_asyncio
from tiled.client import Context, from_context
from tiled.client.register import register
from tiled.server.app import build_app_from_config

from als_tiled.bl733.adapters.metadata import parse_txt_accompanying_edf

EDF_ADAPTER = "als_tiled.bl733.adapters.edf:EDFAdapter"
EDF_MIMETYPE = "application/x-edf"


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
                    "adapters_by_mimetype": {EDF_MIMETYPE: EDF_ADAPTER},
                },
            }
        ],
        "file_extensions": {"edf": EDF_MIMETYPE},
    }


@pytest_asyncio.fixture
async def edf_client(tmp_path, bl733_edf_path):
    with Context.from_app(build_app_from_config(_tiled_config(tmp_path))) as context:
        client = from_context(context)
        await register(
            client,
            tmp_path,
            adapters_by_mimetype={EDF_MIMETYPE: EDF_ADAPTER},
            mimetypes_by_file_ext={".edf": EDF_MIMETYPE},
        )
        yield client


@pytest.mark.asyncio
async def test_edf_reads_array(edf_client):
    """Array returned by the tiled client matches the data written to disk."""
    expected = np.arange(1475 * 1679, dtype=np.int32).reshape(1679, 1475)
    result = edf_client["scan_name_2m"].read()
    np.testing.assert_array_equal(result, expected)


@pytest.mark.asyncio
async def test_edf_metadata_includes_header_fields(edf_client):
    """EDF header fields appear in the tiled entry metadata."""
    metadata = edf_client["scan_name_2m"].metadata
    assert metadata["count_time"] == "10.000000000"
    assert metadata["ByteOrder"] == "LowByteFirst"
    assert metadata["Dim_1"] == "1475"
    assert metadata["Dim_2"] == "1679"


@pytest.mark.asyncio
async def test_edf_metadata_includes_txt_fields(edf_client):
    """Companion .txt fields appear in the tiled entry metadata."""
    metadata = edf_client["scan_name_2m"].metadata
    assert metadata["Exposure time s"] == "10.000"
    assert metadata["Normalize by"] == "Diode"
    assert metadata["PI"] == "PILastname"
    keyless = [v for k, v in metadata.items() if k.startswith("unnamed_")]
    assert "401.000" in keyless
    assert "10440.000" in keyless
    assert "235561.000" in keyless


def test_parse_txt_missing_file(tmp_path):
    """Returns an empty dict when the .txt file does not exist."""
    assert parse_txt_accompanying_edf(tmp_path / "nonexistent.edf") == {}
