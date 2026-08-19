import logging
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
LOADING_MESSAGE = "Loading CBF file produced at DESY beamline P03: %s"


class CBFAdapter(ArrayAdapter):
    structure_family = StructureFamily.array

    def __init__(
        self,
        data_uri: str,
        structure: Optional[ArrayStructure] = None,
        metadata: Optional[JSON] = None,
        specs: Optional[list[Spec]] = None,
        **kwargs: Optional[Any],
    ) -> None:
        """Adapter for `.cbf` detector image files (e.g. Dectris Eiger/Pilatus) at DESY beamline P03."""
        filepath = path_from_uri(data_uri)
        logger.debug(LOADING_MESSAGE, filepath)

        with fabio.open(filepath) as cbf_file:
            array = cbf_file.data
            metadata_cbf = dict(cbf_file.header)

        metadata = {
            **(metadata or {}),
            **metadata_cbf,
        }

        cbf_spec = Spec("desy-p03-cbf", version="1.0")
        specs = list(specs or [])
        if cbf_spec not in specs:
            specs.append(cbf_spec)
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
    ) -> "CBFAdapter":
        return init_adapter_from_catalog(cls, data_source, node, **kwargs)

    @classmethod
    def from_uris(
        cls,
        data_uri: str,
        **kwargs: Optional[Any],
    ) -> "CBFAdapter":
        return cls(data_uri, **kwargs)
