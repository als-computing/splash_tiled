import fabio
import h5py
import numpy as np
import pytest

CBF_SHAPE = (100, 120)

# fabio's generic CBF writer/reader keeps free-text "# key value" lines bundled
# as one raw string under "_array_data.header_contents" rather than exploding
# them into separate dict keys (that only happens for headers matching a
# convention fabio recognizes, e.g. genuine Dectris Pilatus/Eiger output).
SAMPLE_CBF_HEADER = {
    "Detector": "PILATUS 2M, S/N 24-0104, EMBL",
    "Pixel_size": "172e-6 m x 172e-6 m",
    "Exposure_time": "1.000000 s",
}

SAMPLE_CBF_DATA = np.arange(CBF_SHAPE[0] * CBF_SHAPE[1], dtype=np.int32).reshape(
    CBF_SHAPE
)


@pytest.fixture
def desy_p03_cbf_path(tmp_path, scan_name="scan_name"):
    """Write a minimal CBF file (with SAMPLE_CBF_HEADER and SAMPLE_CBF_DATA)
    to tmp_path. Returns the path to the .cbf file."""
    cbf_file = tmp_path / f"{scan_name}.cbf"
    img = fabio.cbfimage.CbfImage(data=SAMPLE_CBF_DATA, header=SAMPLE_CBF_HEADER)
    img.write(str(cbf_file))
    return cbf_file


# Modeled on the real HDF5 layout produced by Lambda detectors at DESY
# beamline P03: entry/instrument/detector/{data,description,translation/distance,
# flatfield_applied,pixel_mask_applied}, data shaped (num_frames, module_dim0,
# module_dim1). Real P03 data (surveyed across ~2500 scans) only ever has this
# 3D shape -- even single-frame calibration scans store shape (1, dim0, dim1),
# never a bare 2D array -- so that's the only shape modeled here.
#
# Two real detector configurations were found in that survey, and real
# translation/distance vectors were read back from one scan of each to get
# real module geometry (not guessed):
#   - Lambda 2M: 3 modules, GaAs sensor, stacked in a single column (only
#     offset_dim0 varies between modules). Real y-gap between modules was
#     ~131-134 px (module height 516 px) -- i.e. the gap is roughly a
#     quarter of a module, not a token 1px seam.
#   - Lambda 9M: 11 modules, Si sensor, arranged in a 3-column grid (mostly
#     4 rows, with one corner module physically absent). Real gaps are
#     anisotropic: ~27-32 px between columns (module width 1556 px) but
#     ~137-145 px between rows (module height 516 px) -- rows are spaced
#     much further apart than columns.
# Module dims here are shrunk for fast tests; ROW_GAP is kept larger than
# COL_GAP to preserve that real anisotropy, proportionally scaled down.
LAMBDA_MODULE_DIM0 = 3  # module height (rows)
LAMBDA_MODULE_DIM1 = 4  # module width (columns)
LAMBDA_ROW_GAP = 2  # between vertically stacked modules (large, like real ~140px)
LAMBDA_COL_GAP = 1  # between side-by-side modules (small, like real ~30px)

LAMBDA_9M_NUM_MODULES = 11
LAMBDA_9M_NUM_COLUMNS = 3
LAMBDA_2M_NUM_MODULES = 3
LAMBDA_2M_NUM_COLUMNS = 1  # single column: a vertical stack, like the real detector


def lambda_grid_offsets(num_modules, num_columns):
    """(offset_dim0, offset_dim1) for `num_modules` laid out row-major in a
    grid of `num_columns` columns (the last row may be partially filled),
    each row separated by LAMBDA_ROW_GAP and each column by LAMBDA_COL_GAP."""
    return [
        (
            (i // num_columns) * (LAMBDA_MODULE_DIM0 + LAMBDA_ROW_GAP),
            (i % num_columns) * (LAMBDA_MODULE_DIM1 + LAMBDA_COL_GAP),
        )
        for i in range(num_modules)
    ]


def lambda_assembled_shape(offsets):
    assembled_dim0 = max(offset_dim0 for offset_dim0, _ in offsets) + LAMBDA_MODULE_DIM0
    assembled_dim1 = max(offset_dim1 for _, offset_dim1 in offsets) + LAMBDA_MODULE_DIM1
    return assembled_dim0, assembled_dim1


def _write_lambda_module(
    path,
    *,
    offset_dim0,
    offset_dim1,
    data_offset,
    num_frames,
    flatfield_applied=1,
    flatfield=None,
):
    """Write one synthetic Lambda module NeXus file. Returns its (frames, dim0, dim1) array.

    Real Lambda module files (surveyed across ~54k files on disk) always
    have a `flatfield` dataset (shape (1, dim0, dim1)) regardless of
    flatfield_applied -- so this always writes one; pass `flatfield` (a 2D
    (dim0, dim1) array) to control its values, e.g. for a test where
    flatfield_applied=0 and the adapter is expected to read and apply it.
    """
    data = (
        np.arange(
            num_frames * LAMBDA_MODULE_DIM0 * LAMBDA_MODULE_DIM1,
            dtype=np.int32,
        ).reshape(num_frames, LAMBDA_MODULE_DIM0, LAMBDA_MODULE_DIM1)
        + data_offset
    )
    if flatfield is None:
        flatfield = np.ones((LAMBDA_MODULE_DIM0, LAMBDA_MODULE_DIM1), dtype=np.float32)
    with h5py.File(path, "w") as h5file:
        detector = h5file.create_group("entry/instrument/detector")
        detector.create_dataset("data", data=data)
        detector.create_dataset("description", data="Lambda")
        # translation/distance is [x, y, z]; the adapter swaps these into
        # (offset_dim1, offset_dim0) -- see lambda_nxs.py's _inspect_files.
        detector.create_dataset(
            "translation/distance", data=[offset_dim1, offset_dim0, 0]
        )
        detector.create_dataset("flatfield_applied", data=flatfield_applied)
        detector.create_dataset("pixel_mask_applied", data=1)
        detector.create_dataset("flatfield", data=flatfield[np.newaxis, :, :])
    return data


@pytest.fixture
def make_desy_p03_lambda_scan(tmp_path):
    """Factory fixture: write a synthetic multi-module Lambda scan to tmp_path.

    Returns (dir, module_arrays, offsets). Use num_frames=0 to model a real
    edge case found at P03: a calibration scan whose modules recorded no
    frames at all -- the walker is expected to skip registering it.
    """

    def _make(
        *,
        num_modules,
        num_columns,
        num_frames,
        scan_name="scan_name",
        scan_idx="00001",
        flatfield_applied=1,
        flatfield_factory=None,
        num_frames_factory=None,
    ):
        offsets = lambda_grid_offsets(num_modules, num_columns)
        module_arrays = [
            _write_lambda_module(
                tmp_path / f"{scan_name}_{scan_idx}_m{module_index + 1:02d}.nxs",
                offset_dim0=offset_dim0,
                offset_dim1=offset_dim1,
                # Not real data -- an arbitrary per-module additive offset so
                # each module's pixel values fall in a distinct numeric range.
                # If the adapter ever placed a module at the wrong offset,
                # comparing exact values (not just shape) would catch it.
                data_offset=module_index * 1000,
                num_frames=(
                    num_frames_factory(module_index)
                    if num_frames_factory
                    else num_frames
                ),
                flatfield_applied=flatfield_applied,
                flatfield=(
                    flatfield_factory(module_index) if flatfield_factory else None
                ),
            )
            for module_index, (offset_dim0, offset_dim1) in enumerate(offsets)
        ]
        return tmp_path, module_arrays, offsets

    return _make
