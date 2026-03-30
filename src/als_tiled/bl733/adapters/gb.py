import logging
import pathlib
from datetime import datetime
from typing import Any, Optional

import fabio
import numpy as np
from tiled.adapters.array import ArrayAdapter
from tiled.adapters.utils import init_adapter_from_catalog
from tiled.catalog.orm import Node
from tiled.structures.array import ArrayStructure
from tiled.structures.core import Spec, StructureFamily
from tiled.structures.data_source import DataSource
from tiled.type_aliases import JSON
from tiled.utils import path_from_uri

from als_tiled.bl733.adapters.metadata import parse_txt_accompanying_edf

logger = logging.getLogger(__name__)
LOADING_MESSAGE = "Loading GB file produced by ALS beamline 7.3.3: %s"

# Pixel dimensions for the PILATUS 2M detector at ALS beamline 7.3.3
PILATUS_2M_PIXELS_X = 1475
PILATUS_2M_PIXELS_Y = 1679


class GeneralBinaryPilatus2MAdapter(ArrayAdapter):
    structure_family = StructureFamily.array

    def __init__(
        self,
        data_uri: str,
        structure: Optional[ArrayStructure] = None,
        metadata: Optional[JSON] = None,
        specs: Optional[list[Spec]] = None,
        **kwargs: Optional[Any],
    ) -> None:
        """Adapter for a stitched detector image .gb produced at ALS beamline 7.3.3."""
        filepath_gb = path_from_uri(data_uri)
        logger.debug(LOADING_MESSAGE, filepath_gb)
        data = np.fromfile(filepath_gb, dtype="<f4")
        expected_size = PILATUS_2M_PIXELS_X * PILATUS_2M_PIXELS_Y
        if data.size != expected_size:
            raise ValueError(
                f"Data size ({data.size}) does not match expected size "
                f"({expected_size})."
            )
        array = data.reshape((PILATUS_2M_PIXELS_Y, PILATUS_2M_PIXELS_X))

        metadata = {
            **(metadata or {}),
            **GeneralBinaryPilatus2MAdapter._parse_accompanying_metadata(filepath_gb),
        }

        gb_spec = Spec("als-bl733-gb", version="1.0")
        specs = list(specs or [])
        if gb_spec not in specs:
            specs.append(gb_spec)
        super().__init__(
            array=array,
            structure=structure or ArrayStructure.from_array(array),
            metadata=metadata,
            specs=specs,
            **kwargs,
        )

    @classmethod
    def from_catalog(
        cls,
        data_source: DataSource,
        node: Node,
        /,
        **kwargs: Optional[Any],
    ) -> "GeneralBinaryPilatus2MAdapter":
        return init_adapter_from_catalog(cls, data_source, node, **kwargs)

    @classmethod
    def from_uris(
        cls,
        data_uri: str,
        **kwargs: Optional[Any],
    ) -> "GeneralBinaryPilatus2MAdapter":
        return cls(data_uri, **kwargs)

    @staticmethod
    def _read_edf(filepath_edf: pathlib.Path) -> tuple[dict[str, Any], datetime | None]:
        """Read one EDF file and its companion .txt, returning (metadata, date)."""
        metadata_txt = parse_txt_accompanying_edf(filepath_edf)
        if not filepath_edf.is_file():
            logger.warning(
                f"GeneralBinary file is missing accompanying EDF file {filepath_edf}."
            )
            return metadata_txt, None
        header = fabio.openheader(filepath_edf).header
        date = datetime.strptime(header["Date"], "%a %b %d %H:%M:%S %Y")
        return {**metadata_txt, **header}, date

    @staticmethod
    def _parse_accompanying_metadata(filepath_gb: pathlib.Path) -> dict[str, Any]:
        """Read the hi and lo EDF companions for a .gb file and merge their metadata."""
        filepath_edf_hi = pathlib.Path(
            str(filepath_gb.with_suffix(".edf")).replace("sfloat", "hi")
        )
        filepath_edf_lo = pathlib.Path(
            str(filepath_gb.with_suffix(".edf")).replace("sfloat", "lo")
        )

        metadata_hi, date_hi = GeneralBinaryPilatus2MAdapter._read_edf(filepath_edf_hi)
        metadata_lo, date_lo = GeneralBinaryPilatus2MAdapter._read_edf(filepath_edf_lo)

        combined_metadata = GeneralBinaryPilatus2MAdapter._combine_metadata(
            metadata_hi, metadata_lo
        )

        date = None
        if date_hi is not None and date_lo is not None:
            date = date_hi if date_hi > date_lo else date_lo
        elif date_hi is not None:
            date = date_hi
        elif date_lo is not None:
            date = date_lo
        if date is not None:
            combined_metadata["Date"] = date.isoformat()

        return combined_metadata

    @staticmethod
    def _combine_metadata(
        metadata_hi: dict[str, Any], metadata_lo: dict[str, Any]
    ) -> dict[str, Any]:
        """Combine metadata from hi and lo EDF files.

        Keys with identical values are kept once. Keys with different values are
        suffixed with _hi and _lo.
        """
        combined_metadata = {}
        for key in set(metadata_hi) | set(metadata_lo):
            value_hi = metadata_hi.get(key)
            value_lo = metadata_lo.get(key)
            if value_hi == value_lo:
                combined_metadata[key] = value_hi
            else:
                if value_hi is not None:
                    combined_metadata[f"{key}_hi"] = value_hi
                if value_lo is not None:
                    combined_metadata[f"{key}_lo"] = value_lo
        return combined_metadata
