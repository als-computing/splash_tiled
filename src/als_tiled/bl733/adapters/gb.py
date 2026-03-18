import logging
import os
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

from als_tiled.bl733.adapters.edf import parse_txt_accompanying_edf

logger = logging.getLogger(__name__)

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
        """Adapter for a detector image saved as .gb produced at ALS beamline 7.3.3"""
        filepath = path_from_uri(data_uri)
        data = np.fromfile(filepath, dtype="<f4")
        expected_size = PILATUS_2M_PIXELS_X * PILATUS_2M_PIXELS_Y
        if data.size != expected_size:
            raise ValueError(
                f"Data size ({data.size}) does not match expected size "
                f"({expected_size})."
            )
        array = data.reshape((PILATUS_2M_PIXELS_Y, PILATUS_2M_PIXELS_X))

        additional_edf_metadata = parse_edf_accompanying_gb(filepath)

        # Combine the metadata dictionaries - the following method combines the
        # metadata dictionaries but there is a potential to overwrrite the values
        # for the same keys. If same keys are present in both dictionaries, then
        # an alternate method should be used to combine the dictionaries, similar to
        # the one used in the combine_edf_metadata_for_gb method.
        metadata = (
            {**metadata, **additional_edf_metadata}
            if metadata
            else additional_edf_metadata
        )

        super().__init__(
            array=array,
            structure=structure or ArrayStructure.from_array(array),
            metadata=metadata,
            specs=(specs or []) + [Spec("als-bl733-gb", version="1.0")],
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


def combine_edf_metadata_for_gb(hi_dict, lo_dict):
    """Combine two dictionaries into one.

    Take the metadata from both and if the same key is present in both,
    keep the values of both but index it with hi and lo

    Parameters
    ----------
    hi_dict: dict
        Dictionary containing metadata from the hi .edf file.
    lo_dict: dict
        Dictionary containing metadata from the lo .edf file
    """
    combined_dict = dict()

    # get all the unique keys from both dictionaries
    combined_keys = set(hi_dict.keys()).union(set(lo_dict.keys()))

    # check if the values match for the same key in both dictionaries
    for key in combined_keys:
        hi_val = hi_dict.get(key)
        lo_val = lo_dict.get(key)

        if hi_val == lo_val:
            # If values are the same, keep one entry
            combined_dict[key] = hi_val
        else:
            # If values are different, add both with distinct keys
            if hi_val is not None:
                combined_dict[f"{key}_hi"] = hi_val
            if lo_val is not None:
                combined_dict[f"{key}_lo"] = lo_val

    return combined_dict


def parse_edf_accompanying_gb(file_path):
    """Parse a .edf file produced at ALS beamline 7.3.3 into a dictionary.

    Parameters
    ----------
    file_path: str or pathlib.Path
        Filepath of the .edf file.
    """

    # Generate the hi edf file path
    edf_hi_filepath = None
    if isinstance(file_path, str):
        edf_hi_filepath = file_path.replace("sfloat_2m.gb", "hi_2m.edf")
    if isinstance(file_path, pathlib.Path):
        edf_hi_filepath = file_path.with_suffix(".edf")
        edf_hi_filepath = pathlib.Path(str(edf_hi_filepath).replace("sfloat", "hi"))

    edf_hi_metadata_dict = parse_txt_accompanying_edf(edf_hi_filepath)

    # If the .txt file exists, the metadata is extracted from it
    # In case the .txt file does not exist:
    #  - set the date as None,
    #  - An empty metadata dictionary is initilized (returned from
    #                                   parse_txt_accompanying_edf())
    if not os.path.isfile(edf_hi_filepath):
        hi_date = None
    else:
        hi_file = fabio.open(edf_hi_filepath)
        hi_header = hi_file.header
        hi_date_str = hi_header.get("Date")
        # Parse the string to convert to datetime object
        hi_date = datetime.strptime(hi_date_str, "%a %b %d %H:%M:%S %Y")
        #  Combine the metadata dictionaries - from header and .txt file
        edf_hi_metadata_dict = {**edf_hi_metadata_dict, **hi_header}

    edf_lo_filepath = None
    if isinstance(file_path, str):
        edf_lo_filepath = file_path.replace("sfloat_2m.gb", "lo_2m.edf")
    if isinstance(file_path, pathlib.Path):
        edf_lo_filepath = file_path.with_suffix(".edf")
        edf_lo_filepath = pathlib.Path(str(edf_lo_filepath).replace("sfloat", "lo"))

    edf_lo_metadata_dict = parse_txt_accompanying_edf(edf_lo_filepath)

    # If the .txt file exists, the metadata is extracted from it
    # In case the .txt file does not exist:
    #  - set the date as None,
    #  - An empty metadata dictionary is initilized (returned from
    #                                   parse_txt_accompanying_edf())
    if not os.path.isfile(edf_lo_filepath):
        lo_date = None
    else:
        lo_file = fabio.open(edf_lo_filepath)
        lo_header = lo_file.header
        lo_date_str = lo_header.get("Date")
        # Parse the string to convert to datetime object
        lo_date = datetime.strptime(lo_date_str, "%a %b %d %H:%M:%S %Y")
        #  Combine the metadata dictionaries - from header and .txt file
        edf_lo_metadata_dict = {**edf_lo_metadata_dict, **lo_header}

    # Combine the metadata dictionaries
    gb_dictionary = combine_edf_metadata_for_gb(
        edf_hi_metadata_dict, edf_lo_metadata_dict
    )

    # Compare two dates and select the later one,
    # but the string version for better readability
    if hi_date is not None and lo_date is not None:
        gb_dictionary["Date"] = hi_date if hi_date > lo_date else lo_date
    else:
        gb_dictionary["Date"] = hi_date if hi_date is not None else lo_date

    return gb_dictionary
