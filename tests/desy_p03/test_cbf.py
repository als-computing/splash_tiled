import numpy as np
import pytest
import pytest_asyncio
from tiled.client import Context, from_context
from tiled.client.register import register
from tiled.server.app import build_app_from_config

CBF_ADAPTER = "splash_tiled.external.desy_p03.adapters.cbf:CBFAdapter"
CBF_MIMETYPE = "application/x-cbf"


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
                    "adapters_by_mimetype": {CBF_MIMETYPE: CBF_ADAPTER},
                },
            }
        ],
        "file_extensions": {"cbf": CBF_MIMETYPE},
    }


@pytest_asyncio.fixture
async def cbf_client(tmp_path, desy_p03_cbf_path):
    with Context.from_app(build_app_from_config(_tiled_config(tmp_path))) as context:
        client = from_context(context)
        await register(
            client,
            tmp_path,
            adapters_by_mimetype={CBF_MIMETYPE: CBF_ADAPTER},
            mimetypes_by_file_ext={".cbf": CBF_MIMETYPE},
        )
        yield client


@pytest.mark.asyncio
async def test_cbf_reads_array(cbf_client):
    """Array returned by the tiled client matches the data written to disk."""
    expected = np.arange(100 * 120, dtype=np.int32).reshape(100, 120)
    result = cbf_client["scan_name"].read()
    np.testing.assert_array_equal(result, expected)


@pytest.mark.asyncio
async def test_cbf_metadata_includes_header_fields(cbf_client):
    """CBF header fields appear in the tiled entry metadata."""
    metadata = cbf_client["scan_name"].metadata
    assert metadata["X-Binary-Element-Type"] == "signed 32-bit integer"
    assert (
        "Detector PILATUS 2M, S/N 24-0104, EMBL"
        in metadata["_array_data.header_contents"]
    )
