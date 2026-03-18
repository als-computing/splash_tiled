import logging
import os
import pathlib
from typing import Any, Optional

import fabio
from tiled.adapters.array import ArrayAdapter
from tiled.adapters.utils import init_adapter_from_catalog
from tiled.catalog.orm import Node
from tiled.structures.array import ArrayStructure
from tiled.structures.core import Spec, StructureFamily
from tiled.structures.data_source import DataSource
from tiled.type_aliases import JSON
from tiled.utils import path_from_uri

logger = logging.getLogger(__name__)


def parse_txt_accompanying_edf(filepath: str | pathlib.Path) -> dict[str, Any]:
    """Parse a .txt file produced at ALS beamline 7.3.3 into a dictionary.

    Parameters
    ----------
    filepath: str or pathlib.Path
        Filepath of the .edf file.
    """
    txt_filepath = None
    if isinstance(filepath, str):
        txt_filepath = filepath.replace(".edf", ".txt")
    if isinstance(filepath, pathlib.Path):
        txt_filepath = filepath.with_suffix(".txt")

    # File does not exist, return empty dictionary
    if not os.path.isfile(txt_filepath):
        logger.warning(f"{filepath} has no corresponding .txt.")
        return dict()

    with open(txt_filepath, "r") as file:
        lines = file.readlines()

    # Some lines have the format
    # key: value
    # others are just values with no key
    keyless_lines = 0
    txt_params = dict()
    for line in lines:
        line_components = list(map(str.strip, line.split(":", maxsplit=1)))
        if len(line_components) >= 2:
            txt_params[line_components[0]] = line_components[1]
        else:
            if line_components[0] != "!0":
                txt_params[f"Keyless Parameter #{keyless_lines}"] = line_components[0]
                keyless_lines += 1
    return txt_params


class EDFAdapter(ArrayAdapter):
    structure_family = StructureFamily.array

    def __init__(
        self,
        data_uri: str,
        structure: Optional[ArrayStructure] = None,
        metadata: Optional[JSON] = None,
        specs: Optional[list[Spec]] = None,
        **kwargs: Optional[Any],
    ) -> None:
        """Adapter for `.edf` files (e.g. PILATUS3 2M) at ALS beamline 7.3.3."""

        filepath = path_from_uri(data_uri)

        metadata = metadata or dict()
        with fabio.open(filepath) as edf_file:
            array = edf_file.data
            edf_metadata = edf_file.header

            # Merge parameters from the header into potentially existing meta data
            metadata = {**metadata, **edf_metadata}

        # If a .txt file with the same name exists
        # extract additional meta data from it
        txt_metadata = parse_txt_accompanying_edf(filepath)
        metadata = {**metadata, **txt_metadata}

        super().__init__(
            array=array,
            structure=structure or ArrayStructure.from_array(array),
            metadata=metadata,
            specs=(specs or []) + [Spec("als-bl733-edf", version="1.0")],
            **kwargs,
        )

    @classmethod
    def from_catalog(
        cls,
        data_source: DataSource,
        node: Node,
        /,
        **kwargs: Optional[Any],
    ) -> "EDFAdapter":
        return init_adapter_from_catalog(cls, data_source, node, **kwargs)

    @classmethod
    def from_uris(
        cls,
        data_uri: str,
        **kwargs: Optional[Any],
    ) -> "EDFAdapter":
        return cls(data_uri, **kwargs)
