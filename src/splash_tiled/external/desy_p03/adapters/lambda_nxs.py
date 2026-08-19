import builtins
import collections
import logging
import re
import warnings
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple, Union

import h5py
import numpy as np
from ndindex import ndindex
from numpy._typing import NDArray
from tiled.adapters.sequence import force_reshape
from tiled.adapters.utils import init_adapter_from_catalog
from tiled.catalog.orm import Node
from tiled.client.register import create_node_or_drop_collision, dict_or_none
from tiled.ndslice import NDSlice
from tiled.structures.array import ArrayStructure, BuiltinDtype
from tiled.structures.core import Spec, StructureFamily
from tiled.structures.data_source import Asset, DataSource, Management
from tiled.type_aliases import JSON
from tiled.utils import ensure_uri, path_from_uri

logger = logging.getLogger("tiled.adapters.lambda_nxs")

# Groups: scan_name (stem), optional scan index digits (may be empty), module digits
# Supports:
#   sample_00001_m01.nxs
#   sample_m01.nxs
#   sample__m01.nxs
#   sample___00001_m01.nxs
LAMBDA_DETECTOR_NEXUS_MODULE_STEM_PATTERN = re.compile(
    r"^(.*?)(?:_+(\d*))?_m(\d{2})\.nxs$"
)

LAMBDA_DETECTOR_NEXUS_MIMETYPE = "multipart/related;type=application/x-hdf5"
LAMBDA_DETECTOR_NEXUS_DATASET_PATH = "entry/instrument/detector/data"
LAMBDA_DETECTOR_NEXUS_DESCRIPTION_PATH = "/entry/instrument/detector/description"

# Total (assembled_dim0, assembled_dim1) for the two physically distinct P03
# Lambda units -- read directly off this adapter's own output for a real,
# complete (all-modules-present) scan of each unit, not derived from any
# per-module offset table.
#
# When a physical module is switched off mid-acquisition, the detector writes
# no file for it at all, and the files that ARE written get renumbered
# sequentially (m01, m02, ... in write order) -- so a written file's *name*
# says nothing about which physical module it is, and nothing on disk reveals
# whether a missing module was the one defining the detector's full extent.
# Pass the matching size here as `pad_to_detector_size` (by name, or as an
# explicit (dim0, dim1)) to guarantee the assembled shape always covers the
# true full detector, with any missing module's region left as a fill_value
# gap -- instead of the array silently coming out smaller when the missing
# module happened to sit at the largest offset.
LAMBDA_KNOWN_DETECTOR_SIZES = {
    "2M": (1813, 1555),
    "9M": (3142, 4727),
}


async def walk(catalog, path, files, directories, settings):
    """
    Group Lambda NeXus module files into datasets and register one Tiled node per dataset.

    Unlike the per-file bl733 adapters, this walker must be registered explicitly
    with `tiled register`, e.g. (with MODULE = splash_tiled.external.desy_p03.adapters.lambda_nxs):
        tiled register <path> \\
            --adapter "multipart/related;type=application/x-hdf5=MODULE:LambdaDetectorNexusAdapter" \\
            --walker "MODULE:walk"
    `tiled serve config` only needs the adapter listed under `adapters_by_mimetype`
    to read already-registered nodes; it has no `walkers` slot of its own.

    A "dataset" here means: all module files that share (scan_name, scan_idx).
    Each dataset is expected to contain exactly 3 or 11 module files.

    Filenames may omit the scan index, have multiple and/or include extra underscores , e.g.
      sample_00001_m01.nxs
      sample_m01.nxs
      sample__m01.nxs
    """
    unhandled_directories = directories
    unhandled_files = []

    # key: (scan_name, scan_idx_or_none) -> list[(module_idx, Path)]
    moduled_per_scan = collections.defaultdict(list)

    for file in files:
        if not file.is_file():
            unhandled_files.append(file)
            continue

        match = LAMBDA_DETECTOR_NEXUS_MODULE_STEM_PATTERN.match(file.name)
        if not match:
            unhandled_files.append(file)
            continue

        scan_name_raw, scan_idx_raw, module_idx_raw = match.groups()

        scan_name = scan_name_raw.rstrip("_")  # sample__ -> sample
        scan_idx = scan_idx_raw or None  # "" -> None
        module_idx = int(module_idx_raw)  # "01" -> 1

        moduled_per_scan[(scan_name, scan_idx)].append((module_idx, file))

    # Iterate over grouped dataset sorted by (scan_name, scan_idx)
    for (scan_name, scan_idx), modules_with_index in sorted(
        moduled_per_scan.items(), key=lambda group: (group[0][0], group[0][1] or "")
    ):
        # Sort by stored module index (m01, m02, ...)
        modules_with_index.sort(key=lambda t: t[0])
        module_files = [p for _, p in modules_with_index]

        scan_name_full = (
            f"{scan_name}_{scan_idx}" if scan_idx is not None else scan_name
        )

        # Sanity check: ensure there is data in the first module
        # and that there is an indication we are working with Lambda detector
        try:
            with h5py.File(str(module_files[0]), "r") as h5file:
                data_set = h5file.get(LAMBDA_DETECTOR_NEXUS_DATASET_PATH)
                has_data = (data_set is not None) and (data_set.size > 0)
                # Description is a scalar
                detector_description = h5file.get(
                    LAMBDA_DETECTOR_NEXUS_DESCRIPTION_PATH
                ).asstr()[()]
        except Exception:
            logger.exception(
                "    SKIPPED: Could not open/inspect first module for '%s'",
                scan_name_full,
            )
            unhandled_files.extend(module_files)
            continue

        if "Lambda" not in detector_description:
            logger.info(
                "    SKIPPED: Did not group %d NeXus files into '%s' since "
                "adapter only applies to Lambda detectors, but %s"
                "(%s) does not match a Lambda detector name",
                len(module_files),
                scan_name_full,
                LAMBDA_DETECTOR_NEXUS_DESCRIPTION_PATH,
                detector_description,
            )
            unhandled_files.extend(module_files)
            continue

        if not has_data:
            logger.info(
                "    SKIPPED: Did not group %d NeXus files into '%s' since "
                "they do not contain any data at %s.",
                len(module_files),
                scan_name_full,
                LAMBDA_DETECTOR_NEXUS_DATASET_PATH,
            )
            unhandled_files.extend(module_files)
            continue

        key = settings.key_from_filename(scan_name_full)

        logger.info(
            "    Grouped %d NeXus files into Lambda dataset node '%s'",
            len(module_files),
            scan_name_full,
        )

        adapter_class = settings.adapters_by_mimetype[LAMBDA_DETECTOR_NEXUS_MIMETYPE]
        data_uris = [ensure_uri(str(p.absolute())) for p in module_files]

        try:
            adapter = adapter_class.from_uris(*data_uris)
        except Exception:
            logger.exception(
                "    SKIPPED: Error constructing adapter for '%s'", scan_name_full
            )
            unhandled_files.extend(module_files)
            continue

        await create_node_or_drop_collision(
            catalog,
            key=key,
            structure_family=adapter.structure_family,
            metadata=dict(adapter.metadata()),
            specs=adapter.specs,
            data_sources=[
                DataSource(
                    mimetype=LAMBDA_DETECTOR_NEXUS_MIMETYPE,
                    structure=dict_or_none(adapter.structure()),
                    structure_family=adapter.structure_family,
                    parameters={},
                    management=Management.external,
                    assets=[
                        Asset(
                            data_uri=str(data_uri),
                            is_directory=False,
                            parameter="data_uris",
                            num=i,
                        )
                        for i, data_uri in enumerate(data_uris)
                    ],
                )
            ],
        )

    return unhandled_files, unhandled_directories


@dataclass(frozen=True)
class _ModuleInfo:
    filepath: str
    offset_dim0: int
    offset_dim1: int


class LambdaDetectorNexusAdapter:
    """
    Assemble Lambda module NeXus files into a per-frame detector image sequence.

    Output shape:
      (num_frames, assembled_dim0, assembled_dim1)

    Lambda-specific fixed paths:
      - data:        entry/instrument/detector/data
      - flatfield:   entry/instrument/detector/flatfield (float32)
      - pixel_mask:  entry/instrument/detector/pixel_mask (uint32)
      - translation: entry/instrument/detector/translation/distance (often length 3, third typically 0)
    """

    structure_family = StructureFamily.array

    DATASET_PATH = "entry/instrument/detector/data"
    FLATFIELD_PATH = "entry/instrument/detector/flatfield"
    MASK_PATH = "entry/instrument/detector/pixel_mask"
    TRANSLATION_PATH = "entry/instrument/detector/translation/distance"

    # pixel_mask carries several distinct flags (e.g. bit 31 / 0x80000000 / 2147483648
    # small codes like 4/6/8); old code used this threshold to distinguish
    # masked from non-masked pixels. Meaning of the individual flags is unknown
    MASK_BAD_THRESHOLD = np.uint32(2147483600)

    def __init__(
        self,
        data_uris: List[str],
        *,
        structure: Optional[ArrayStructure] = None,
        metadata: Optional[JSON] = None,
        specs: Optional[List[Spec]] = None,
        apply_flatfield: bool = True,
        apply_mask: bool = False,
        excluded_modules: Optional[List[int]] = None,
        fill_value: float = -1.0,
        pad_to_detector_size: Optional[Union[str, Tuple[int, int]]] = None,
        **kwargs: Optional[Any],
    ) -> None:
        self.specs = specs or []
        self._provided_metadata = metadata or {}

        self._apply_flatfield = apply_flatfield
        self._apply_mask = apply_mask
        self._excluded_module_indices = set(excluded_modules or [])
        self._fill_value = float(fill_value)

        if isinstance(pad_to_detector_size, str):
            try:
                pad_to_detector_size = LAMBDA_KNOWN_DETECTOR_SIZES[pad_to_detector_size]
            except KeyError:
                raise ValueError(
                    f"Unknown pad_to_detector_size {pad_to_detector_size!r}; "
                    f"known sizes are {sorted(LAMBDA_KNOWN_DETECTOR_SIZES)}"
                ) from None
        self._pad_to_detector_size = pad_to_detector_size

        self._filepaths = [path_from_uri(u) for u in data_uris]
        self._num_modules = len(self._filepaths)

        (
            self._module_infos,
            self._num_frames,
            self._flatfield_applied,
            self._mask_applied,
            self._assembled_dim0,
            self._assembled_dim1,
            self._module_dim0,
            self._module_dim1,
            native_dtype,
        ) = self._inspect_files()

        if self._pad_to_detector_size is not None:
            pad_dim0, pad_dim1 = self._pad_to_detector_size
            # max(), not replace: never shrink below what present modules
            # actually require, in case the requested size is stale/wrong.
            self._assembled_dim0 = max(self._assembled_dim0, pad_dim0)
            self._assembled_dim1 = max(self._assembled_dim1, pad_dim1)

        # Decide output dtype:
        # - keep native dtype if no corrections are applied
        # - otherwise use float32 (flatfield is float32; masking uses fill_value)
        if self._apply_flatfield or self._apply_mask:
            self._output_dtype = np.dtype("float32")
        else:
            self._output_dtype = native_dtype

        if structure is None:
            shape = (self._num_frames, self._assembled_dim0, self._assembled_dim1)
            structure = ArrayStructure(
                shape=shape,
                chunks=((1,) * shape[0], (shape[1],), (shape[2],)),
                data_type=BuiltinDtype.from_numpy_dtype(self._output_dtype),
            )

        self._structure = structure

    @classmethod
    def from_catalog(
        cls,
        data_source: DataSource,
        node: Node,
        /,
        **kwargs: Optional[Any],
    ) -> "LambdaDetectorNexusAdapter":
        return init_adapter_from_catalog(cls, data_source, node, **kwargs)

    @classmethod
    def from_uris(
        cls, *data_uris: str, **kwargs: Optional[Any]
    ) -> "LambdaDetectorNexusAdapter":
        return cls(list(data_uris), **kwargs)

    def structure(self) -> ArrayStructure:
        return self._structure

    def metadata(self) -> JSON:
        metadata = dict(self._provided_metadata)
        metadata.update(
            dict(
                num_modules=self._num_modules,
                num_frames=self._num_frames,
                assembled_shape=(self._assembled_dim0, self._assembled_dim1),
                module_shape=(self._module_dim0, self._module_dim1),
                apply_flatfield=self._apply_flatfield,
                apply_mask=self._apply_mask,
                excluded_modules=sorted(self._excluded_module_indices),
                dtype=str(self._output_dtype),
                fill_value=self._fill_value,
                mask_bad_threshold=int(self.MASK_BAD_THRESHOLD),
                pad_to_detector_size=self._pad_to_detector_size,
            )
        )
        return metadata

    def read(self, slice: Optional[NDSlice] = ...) -> NDArray[Any]:
        """
        Supports:
        - read() / read(Ellipsis): return full (num_frames, assembled_dim0, assembled_dim1)
        - read(int): return one frame -> (assembled_dim0, assembled_dim1)
        - read(slice): return (n, assembled_dim0, assembled_dim1)
        - read(tuple): e.g. (frame_sel, dim0_sel, dim1_sel)
        """
        if slice is Ellipsis or slice is None:
            array = self._load_frames(builtins.slice(None))
        elif isinstance(slice, int):
            array = np.squeeze(self._load_frames(slice), axis=0)
        elif isinstance(slice, builtins.slice):
            array = self._load_frames(slice)
        elif isinstance(slice, tuple):
            if len(slice) == 0:
                array = self._load_frames(builtins.slice(None))
            elif len(slice) == 1:
                array = self.read(slice=slice[0])
            else:
                frame_selector, *remaining_selectors = slice

                if isinstance(frame_selector, int):
                    array = np.squeeze(self._load_frames(frame_selector), axis=0)
                elif frame_selector is Ellipsis:
                    array = self._load_frames(builtins.slice(None))
                    remaining_selectors.insert(0, Ellipsis)
                elif isinstance(frame_selector, builtins.slice):
                    array = self._load_frames(frame_selector)
                else:
                    raise RuntimeError(
                        f"Unsupported frame selector type {type(frame_selector)}: {frame_selector}"
                    )

                sliced_shape = ndindex(frame_selector).newshape(self.structure().shape)
                array = force_reshape(array, sliced_shape)
                array = np.atleast_1d(array[tuple(remaining_selectors)])
        else:
            raise RuntimeError(f"Unsupported slice type, {type(slice)} in {slice}")

        sliced_shape = ndindex(slice).newshape(self.structure().shape)
        return force_reshape(array, sliced_shape)

    def read_block(
        self, block: Tuple[int, ...], slice: Optional[NDSlice] = ...
    ) -> NDArray[Any]:
        """
        With chunks set to one-frame, expected block is (frame_index, 0, 0).
        """
        if len(block) != 3 or any(block[1:]):
            raise IndexError(block)

        frame_index = block[0]
        array = self._load_frames(builtins.slice(frame_index, frame_index + 1))
        return array[slice] if slice not in (None, Ellipsis) else array

    def _inspect_files(
        self,
    ) -> Tuple[List[_ModuleInfo], int, int, int, int, int, int, int, np.dtype]:
        """
        Determine:
        - per-module offsets (offset_dim0/offset_dim1) from translation/distance
        - number of frames (supports 2D or 3D datasets) -- the min across all
          modules, since real scans have been observed where one module logs
          one more frame than the others; using any single module's count
          could ask a shorter module for a frame index it doesn't have
        - module shape (from data dataset shape)
        - assembled detector extents (from the modules present in this scan
          only -- pass pad_to_detector_size to __init__ if the assembled shape
          should instead guarantee coverage of a known full detector unit)
        - native dtype of the dataset
        """
        module_infos: List[_ModuleInfo] = []

        with h5py.File(self._filepaths[0], "r") as h5file:
            first_data = h5file[self.DATASET_PATH]
            native_dtype = np.dtype(first_data.dtype)

            if first_data.ndim == 2:
                module_dim0, module_dim1 = map(int, first_data.shape)
            else:
                module_dim0, module_dim1 = map(int, first_data.shape[1:])
            flatfield_applied = h5file[self.FLATFIELD_PATH + "_applied"][()]
            mask_applied = h5file[self.MASK_PATH + "_applied"][()]

        assembled_dim0 = 0
        assembled_dim1 = 0
        num_frames: Optional[int] = None

        for filepath in self._filepaths:
            with h5py.File(filepath, "r") as h5file:
                translation = np.asarray(
                    h5file[self.TRANSLATION_PATH], dtype=int
                ).ravel()
                if translation.size < 2:
                    raise ValueError(
                        f"Unexpected translation shape {translation.shape} in {filepath}"
                    )

                # The translation vector stores detector-plane offsets, typically as (x, y [, 0]).
                # In NumPy, array indexing is (row, column) == (axis0, axis1),
                # which corresponds to (y, x) in detector module coordinates.
                # To place modules correctly on the assembled array we therefore swap:
                #   axis0 start = y offset = translation[1]
                #   axis1 start = x offset = translation[0]
                # treat translation[0] as dim1 offset and translation[1] as dim0 offset.
                offset_dim1 = int(translation[0])
                offset_dim0 = int(translation[1])

                data_set = h5file[self.DATASET_PATH]
                if data_set.ndim == 2:
                    dim0, dim1 = data_set.shape
                    this_num_frames = 1
                else:
                    dim0, dim1 = data_set.shape[1:]
                    this_num_frames = int(data_set.shape[0])

                if (int(dim0), int(dim1)) != (module_dim0, module_dim1):
                    warnings.warn(
                        f"Module shape {(int(dim0), int(dim1))} != first module "
                        f"{(module_dim0, module_dim1)} for {filepath}",
                        category=RuntimeWarning,
                    )

                num_frames = (
                    this_num_frames
                    if num_frames is None
                    else min(num_frames, this_num_frames)
                )

            assembled_dim0 = max(assembled_dim0, offset_dim0 + module_dim0)
            assembled_dim1 = max(assembled_dim1, offset_dim1 + module_dim1)

            module_infos.append(
                _ModuleInfo(
                    filepath=filepath,
                    offset_dim0=offset_dim0,
                    offset_dim1=offset_dim1,
                )
            )

        return (
            module_infos,
            int(num_frames),
            bool(flatfield_applied),
            bool(mask_applied),
            int(assembled_dim0),
            int(assembled_dim1),
            int(module_dim0),
            int(module_dim1),
            native_dtype,
        )

    def _load_frames(self, frame_selection: Union[builtins.slice, int]) -> NDArray[Any]:
        """
        Return stacked assembled frames.

        - if frame_selection is int -> (1, assembled_dim0, assembled_dim1)
        - if frame_selection is slice -> (n, assembled_dim0, assembled_dim1)
        """
        if isinstance(frame_selection, int):
            if frame_selection < 0 or frame_selection >= self._num_frames:
                raise IndexError(frame_selection)
            frame_slice = builtins.slice(frame_selection, frame_selection + 1)
        else:
            frame_slice = frame_selection

        selected_frame_indices = list(range(self._num_frames))[frame_slice]

        assembled_frames = np.empty(
            (len(selected_frame_indices), self._assembled_dim0, self._assembled_dim1),
            dtype=self._output_dtype,
        )
        assembled_frames[:] = self._fill_value

        for output_frame_index, input_frame_index in enumerate(selected_frame_indices):
            assembled_frame = np.empty(
                (self._assembled_dim0, self._assembled_dim1), dtype=self._output_dtype
            )
            assembled_frame[:] = self._fill_value

            for module_index, module_info in enumerate(self._module_infos):
                if module_index in self._excluded_module_indices:
                    continue

                with h5py.File(module_info.filepath, "r") as h5file:
                    data_set = h5file[self.DATASET_PATH]

                    if data_set.ndim == 2:
                        module_data = np.asarray(data_set)
                    else:
                        module_data = np.asarray(data_set[input_frame_index])

                    # Promote for correction math if needed
                    if self._apply_flatfield or self._apply_mask:
                        module_data = module_data.astype(np.float32, copy=False)

                    if self._apply_flatfield and not self._flatfield_applied:
                        flatfield = np.asarray(
                            h5file[self.FLATFIELD_PATH][0], dtype=np.float32
                        )
                        module_data *= flatfield

                    if self._apply_mask and not self._mask_applied:
                        pixel_mask = np.asarray(
                            h5file[self.MASK_PATH][0], dtype=np.uint32
                        )
                        good_pixels = pixel_mask <= self.MASK_BAD_THRESHOLD
                        module_data = np.where(
                            good_pixels, module_data, self._fill_value
                        )

                    if module_data.dtype != self._output_dtype:
                        module_data = module_data.astype(self._output_dtype, copy=False)

                start_dim0 = module_info.offset_dim0
                start_dim1 = module_info.offset_dim1
                assembled_frame[
                    start_dim0 : start_dim0 + self._module_dim0,  # noqa: E203
                    start_dim1 : start_dim1 + self._module_dim1,  # noqa: E203
                ] = module_data

            assembled_frames[output_frame_index] = assembled_frame

        return assembled_frames
