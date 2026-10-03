import numpy as np
import pytest
import pytest_asyncio
from tiled.client import Context, from_context
from tiled.client.register import register
from tiled.server.app import build_app_from_config
from tiled.utils import safe_json_dump

from splash_tiled.bl11012.adapters.fits import MAX_TABLE_ROWS, FITSAdapter
from tests.bl11012.samples import SAMPLE_FITS_DATA, base_primary_header, fits, make_fits

FITS_ADAPTER = "splash_tiled.bl11012.adapters.fits:FITSAdapter"
FITS_MIMETYPE = "application/fits"


def _read(path):
    return FITSAdapter(f"file://{path}")


# --- Direct adapter behaviour -------------------------------------------------


def test_fits_returns_array_with_frame_shape(tmp_path):
    adapter = _read(make_fits(tmp_path))
    assert adapter.structure_family == "array"
    assert adapter.structure().shape == (3, 3)


def test_fits_preserves_values_and_native_byte_order(tmp_path):
    adapter = _read(make_fits(tmp_path))
    arr = adapter.read()
    assert arr.dtype.byteorder in ("=", "|")
    np.testing.assert_array_equal(arr, SAMPLE_FITS_DATA)


def test_fits_metadata_is_json_safe_and_preserves_cards(tmp_path):
    metadata = _read(make_fits(tmp_path)).metadata()

    safe_json_dump(metadata)  # must not raise

    assert metadata["EPU Polarization"] == 100.0
    assert metadata["COMMENT"] == ["first comment", "second comment"]
    assert metadata["UNDEF"] is None
    assert metadata["FLAG"] is True
    # The image HDU's cards are nested, not merged over the primary header.
    assert metadata["image_hdu"]["EXTNAME"] == "Images"
    assert "EXTNAME" not in metadata


def test_fits_izeros_table_is_captured_into_extensions(tmp_path):
    metadata = _read(make_fits(tmp_path)).metadata()
    izeros = metadata["extensions"]["Izeros"]
    assert izeros["rows"] == 4
    np.testing.assert_allclose(izeros["data"]["0"], [1.1, 2.2, 3.3, 4.4], rtol=1e-5)


def test_fits_large_table_records_only_summary(tmp_path):
    values = np.arange(MAX_TABLE_ROWS + 1, dtype=np.float32)
    izeros = _read(make_fits(tmp_path, izeros_values=values)).metadata()["extensions"][
        "Izeros"
    ]
    assert izeros["rows"] == MAX_TABLE_ROWS + 1
    assert "data" not in izeros


def test_fits_images_extname_wins_over_decoy(tmp_path):
    adapter = _read(make_fits(tmp_path, include_decoy=True))
    assert adapter.metadata()["image_hdu"]["EXTNAME"] == "Images"
    assert adapter.structure().shape == (3, 3)  # not the decoy's (4, 4)


def test_fits_falls_back_to_first_2d_image_without_images_extname(tmp_path):
    adapter = _read(make_fits(tmp_path, include_decoy=True, image_extname="Frame"))
    # The decoy precedes the renamed frame, so it wins the fallback.
    assert adapter.structure().shape == (4, 4)


def test_fits_falls_back_to_primary_hdu_with_data(tmp_path):
    primary = fits.PrimaryHDU(data=np.ones((5, 5), dtype=np.uint16))
    primary.header.update(base_primary_header())
    path = tmp_path / "primary_only.fits"
    fits.HDUList([primary]).writeto(path, overwrite=True)

    assert _read(path).structure().shape == (5, 5)


def test_fits_raises_when_no_image_data(tmp_path):
    primary = fits.PrimaryHDU()
    primary.header.update(base_primary_header())
    path = tmp_path / "no_image.fits"
    fits.HDUList([primary]).writeto(path, overwrite=True)

    with pytest.raises(ValueError, match="No image HDU"):
        _read(path)


def test_fits_caller_metadata_overrides_file_cards(tmp_path):
    adapter = FITSAdapter(
        f"file://{make_fits(tmp_path)}", metadata={"FLAG": False, "extra": 1}
    )
    metadata = adapter.metadata()
    assert metadata["FLAG"] is False
    assert metadata["extra"] == 1


# --- Round trip through a Tiled server ----------------------------------------


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
                    "adapters_by_mimetype": {FITS_MIMETYPE: FITS_ADAPTER},
                },
            }
        ],
        "file_extensions": {"fits": FITS_MIMETYPE},
    }


@pytest_asyncio.fixture
async def fits_client(tmp_path, bl11012_fits_path):
    with Context.from_app(build_app_from_config(_tiled_config(tmp_path))) as context:
        client = from_context(context)
        await register(
            client,
            tmp_path,
            adapters_by_mimetype={FITS_MIMETYPE: FITS_ADAPTER},
            mimetypes_by_file_ext={".fits": FITS_MIMETYPE},
        )
        yield client


@pytest.mark.asyncio
async def test_fits_server_reads_array(fits_client):
    """Array returned by the tiled client matches the frame written to disk."""
    result = fits_client["scan_name"].read()
    np.testing.assert_array_equal(result, SAMPLE_FITS_DATA)


@pytest.mark.asyncio
async def test_fits_server_metadata_includes_header_fields(fits_client):
    """Primary-header cards and the nested image header survive registration."""
    metadata = fits_client["scan_name"].metadata
    assert metadata["EPU Polarization"] == 100.0
    assert metadata["image_hdu"]["EXTNAME"] == "Images"
    assert metadata["extensions"]["Izeros"]["rows"] == 4


@pytest.mark.asyncio
async def test_fits_server_node_carries_spec(fits_client):
    specs = fits_client["scan_name"].specs
    assert any(spec.name == "als-bl11012-fits" for spec in specs)
