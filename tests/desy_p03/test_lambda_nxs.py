import numpy as np
import pytest
from tiled.client import Context, from_context
from tiled.client.register import register
from tiled.server.app import build_app_from_config

from tests.desy_p03.conftest import (
    LAMBDA_2M_NUM_COLUMNS,
    LAMBDA_2M_NUM_MODULES,
    LAMBDA_9M_NUM_COLUMNS,
    LAMBDA_9M_NUM_MODULES,
    LAMBDA_MODULE_DIM0,
    LAMBDA_MODULE_DIM1,
    lambda_assembled_shape,
)

LAMBDA_ADAPTER = (
    "splash_tiled.external.desy_p03.adapters.lambda_nxs:LambdaDetectorNexusAdapter"
)
LAMBDA_WALKER = "splash_tiled.external.desy_p03.adapters.lambda_nxs:walk"
LAMBDA_MIMETYPE = "multipart/related;type=application/x-hdf5"

SCAN_KEY = "scan_name_00001"
FILL_VALUE = -1.0


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
                    "adapters_by_mimetype": {LAMBDA_MIMETYPE: LAMBDA_ADAPTER},
                },
            }
        ],
    }


def _tiled_context(tmp_path):
    return Context.from_app(build_app_from_config(_tiled_config(tmp_path)))


def _expected_frame(module_arrays, offsets, frame_index, flatfields=None):
    """Build the expected assembled frame by placing each module's data at
    its translated offset over a fill_value-filled canvas -- the same
    placement the adapter itself performs, so this checks that real
    per-module offsets (read from HDF5) drive correct stitching, including
    unfilled gaps between/around modules in an irregular grid.

    If `flatfields` is given (one 2D array per module, matching what the
    adapter is expected to read and multiply in), each module's frame is
    corrected before placement -- for testing the not-yet-applied-flatfield
    path.
    """
    assembled_dim0, assembled_dim1 = lambda_assembled_shape(offsets)
    expected = np.full((assembled_dim0, assembled_dim1), FILL_VALUE, dtype=np.float32)
    for module_index, ((offset_dim0, offset_dim1), module_array) in enumerate(
        zip(offsets, module_arrays)
    ):
        module_frame = module_array[frame_index].astype(np.float32)
        if flatfields is not None:
            module_frame = module_frame * flatfields[module_index]
        expected[
            offset_dim0 : offset_dim0 + module_frame.shape[0],  # noqa: E203
            offset_dim1 : offset_dim1 + module_frame.shape[1],  # noqa: E203
        ] = module_frame
    return expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "num_modules, num_columns",
    [
        (LAMBDA_9M_NUM_MODULES, LAMBDA_9M_NUM_COLUMNS),
        (LAMBDA_2M_NUM_MODULES, LAMBDA_2M_NUM_COLUMNS),
    ],
    ids=["lambda_9m", "lambda_2m"],
)
async def test_lambda_scan_registers_and_reads(
    tmp_path, make_desy_p03_lambda_scan, num_modules, num_columns
):
    """A scan with either real detector's module/grid layout (11 modules in
    a 3-column grid for Lambda 9M, 3 modules in a single column for Lambda
    2M) collapses into one node with correct metadata and stitching."""
    num_frames = 2
    scan_dir, module_arrays, offsets = make_desy_p03_lambda_scan(
        num_modules=num_modules, num_columns=num_columns, num_frames=num_frames
    )

    with _tiled_context(tmp_path) as context:
        client = from_context(context)
        await register(
            client,
            scan_dir,
            adapters_by_mimetype={LAMBDA_MIMETYPE: LAMBDA_ADAPTER},
            walkers=[LAMBDA_WALKER],
        )

        assert list(client) == [SCAN_KEY]

        metadata = client[SCAN_KEY].metadata
        assert metadata["num_modules"] == num_modules
        assert metadata["num_frames"] == num_frames
        assert tuple(metadata["assembled_shape"]) == lambda_assembled_shape(offsets)

        for frame_index in range(num_frames):
            frame = client[SCAN_KEY].read(frame_index)
            np.testing.assert_array_equal(
                frame, _expected_frame(module_arrays, offsets, frame_index)
            )


@pytest.mark.asyncio
async def test_lambda_single_frame_scan(tmp_path, make_desy_p03_lambda_scan):
    """A single-frame scan (e.g. a calibration shot) is still a 3D dataset
    with num_frames=1, matching every real P03 file surveyed -- never a bare
    2D array -- and reads back correctly."""
    scan_dir, module_arrays, offsets = make_desy_p03_lambda_scan(
        num_modules=LAMBDA_2M_NUM_MODULES,
        num_columns=LAMBDA_2M_NUM_COLUMNS,
        num_frames=1,
    )

    with _tiled_context(tmp_path) as context:
        client = from_context(context)
        await register(
            client,
            scan_dir,
            adapters_by_mimetype={LAMBDA_MIMETYPE: LAMBDA_ADAPTER},
            walkers=[LAMBDA_WALKER],
        )

        metadata = client[SCAN_KEY].metadata
        assert metadata["num_frames"] == 1

        frame = client[SCAN_KEY].read(0)
        np.testing.assert_array_equal(
            frame, _expected_frame(module_arrays, offsets, frame_index=0)
        )


@pytest.mark.asyncio
async def test_lambda_flatfield_applied_when_not_yet_applied(
    tmp_path, make_desy_p03_lambda_scan
):
    """When a module reports flatfield_applied=0 (not yet corrected upstream)
    and apply_flatfield=True (the adapter's default), the adapter must read
    that module's `flatfield` dataset and multiply it in itself. Every other
    test here uses flatfield_applied=1, where that branch is a no-op -- this
    is the only test that exercises the actual correction math."""
    num_frames = 2
    flatfields = {}

    def flatfield_factory(module_index):
        # Per-pixel-varying (not a uniform scalar) and distinct per module,
        # so a broadcasting mistake or a module mix-up would still fail the
        # comparison -- not just a uniform-scale test that could pass by luck.
        values = 1.0 + 0.5 * (
            np.arange(
                LAMBDA_MODULE_DIM0 * LAMBDA_MODULE_DIM1, dtype=np.float32
            ).reshape(LAMBDA_MODULE_DIM0, LAMBDA_MODULE_DIM1)
            + module_index
        )
        flatfields[module_index] = values
        return values

    scan_dir, module_arrays, offsets = make_desy_p03_lambda_scan(
        num_modules=LAMBDA_2M_NUM_MODULES,
        num_columns=LAMBDA_2M_NUM_COLUMNS,
        num_frames=num_frames,
        flatfield_applied=0,
        flatfield_factory=flatfield_factory,
    )

    with _tiled_context(tmp_path) as context:
        client = from_context(context)
        await register(
            client,
            scan_dir,
            adapters_by_mimetype={LAMBDA_MIMETYPE: LAMBDA_ADAPTER},
            walkers=[LAMBDA_WALKER],
        )

        for frame_index in range(num_frames):
            frame = client[SCAN_KEY].read(frame_index)
            np.testing.assert_array_equal(
                frame,
                _expected_frame(
                    module_arrays, offsets, frame_index, flatfields=flatfields
                ),
            )


@pytest.mark.asyncio
async def test_lambda_zero_frame_scan_is_not_grouped(
    tmp_path, make_desy_p03_lambda_scan
):
    """A real edge case at P03: a calibration scan whose modules recorded
    zero frames (data shape (0, dim0, dim1) -- still 3D, just empty). The
    walker's has_data check must decline to group it into a Lambda dataset
    node -- leaving the module files as unhandled, which tiled's default
    walker then registers individually as plain (empty) HDF5 files instead.
    """
    scan_dir, _, _ = make_desy_p03_lambda_scan(
        num_modules=LAMBDA_2M_NUM_MODULES,
        num_columns=LAMBDA_2M_NUM_COLUMNS,
        num_frames=0,
    )

    with _tiled_context(tmp_path) as context:
        client = from_context(context)
        await register(
            client,
            scan_dir,
            adapters_by_mimetype={LAMBDA_MIMETYPE: LAMBDA_ADAPTER},
            walkers=[LAMBDA_WALKER],
        )

        assert SCAN_KEY not in list(client)
