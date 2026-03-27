import logging
from datetime import datetime
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

from als_tiled.bl733.adapters.metadata import parse_txt_accompanying_edf

logger = logging.getLogger(__name__)


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
        logger.debug("Loading EDF file produced by ALS beamline 7.3.3: %s", filepath)

        with fabio.open(filepath) as edf_file:
            array = edf_file.data
            metadata_edf = edf_file.header

        if "Date" in metadata_edf:
            date = datetime.strptime(metadata_edf["Date"], "%a %b %d %H:%M:%S %Y")
            metadata_edf["Date"] = date.isoformat()

        metadata = {
            **(metadata or {}),
            **metadata_edf,
            **parse_txt_accompanying_edf(filepath),
        }

        edf_spec = Spec("als-bl733-edf", version="1.0")
        specs = list(specs or [])
        if edf_spec not in specs:
            specs.append(edf_spec)
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
    ) -> "EDFAdapter":
        return init_adapter_from_catalog(cls, data_source, node, **kwargs)

    @classmethod
    def from_uris(
        cls,
        data_uri: str,
        **kwargs: Optional[Any],
    ) -> "EDFAdapter":
        return cls(data_uri, **kwargs)
