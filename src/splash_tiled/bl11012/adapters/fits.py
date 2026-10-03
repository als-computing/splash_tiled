"""Adapter for ALS CCD FITS files from beamline 11.0.1.2 (RSoXS).

The primary HDU only holds metadata (NAXIS=0, about 120 motor and analog
cards). The detector frame lives in an IMAGE extension named ``Images``, and
small BINTABLE extensions such as ``Izeros`` hold per-frame readbacks. The
same layout is written at 7.3.3. Plain single-image FITS files are handled by
the fallbacks in ``_pick_image_hdu``.
"""

import logging
from typing import Any, Optional

import numpy as np
from astropy.io import fits
from tiled.adapters.array import ArrayAdapter
from tiled.adapters.utils import init_adapter_from_catalog
from tiled.catalog.orm import Node
from tiled.structures.array import ArrayStructure
from tiled.structures.core import Spec, StructureFamily
from tiled.structures.data_source import DataSource
from tiled.type_aliases import JSON
from tiled.utils import path_from_uri

logger = logging.getLogger(__name__)
LOADING_MESSAGE = "Loading FITS file produced by ALS beamline 11.0.1.2: %s"

#: EXTNAME of the image extension these detectors write (matched case-insensitively).
PREFERRED_EXTNAME = "images"

#: Non-image extensions with at most this many rows are copied into metadata.
MAX_TABLE_ROWS = 1024

_COMMENTARY_KEYWORDS = ("COMMENT", "HISTORY")


def _is_2d_image(hdu: Any) -> bool:
    """Return True if ``hdu`` is an image HDU with 2-D data."""
    return (
        bool(getattr(hdu, "is_image", False))
        and len(getattr(hdu, "shape", ()) or ()) == 2
    )


def _pick_image_hdu(hdulist: fits.HDUList) -> tuple[int, Any]:
    """Locate the HDU holding the detector frame.

    Order of preference:
      1. An image HDU whose EXTNAME is ``Images`` (case-insensitive).
      2. The first 2-D image extension.
      3. The primary HDU, if it carries at least 2-D data.

    Args:
        hdulist: An open FITS HDU list.

    Returns:
        The index of the chosen HDU and the HDU itself.

    Raises:
        ValueError: If no HDU contains image data.
    """
    for index, hdu in enumerate(hdulist):
        extname = str(hdu.header.get("EXTNAME", "")).strip().lower()
        if extname == PREFERRED_EXTNAME and _is_2d_image(hdu):
            return index, hdu
    for index, hdu in enumerate(hdulist):
        if index == 0:
            continue
        if _is_2d_image(hdu):
            return index, hdu
    primary = hdulist[0]
    if (
        getattr(primary, "is_image", False)
        and len(getattr(primary, "shape", ()) or ()) >= 2
    ):
        return 0, primary
    extensions = ", ".join(
        f"{i}:{h.header.get('EXTNAME', h.__class__.__name__)}"
        for i, h in enumerate(hdulist)
    )
    raise ValueError(f"No image HDU found in FITS file (extensions: {extensions})")


def _safe_str(value: Any) -> str:
    """Stringify ``value``, replacing lone surrogates that orjson rejects."""
    return str(value).encode("utf-8", "replace").decode("utf-8")


def _card_value(value: Any) -> Any:
    """Convert a FITS card value into a JSON-safe Python value."""
    if isinstance(value, fits.card.Undefined):
        return None
    if isinstance(value, bool):  # must precede int: bool is an int
        return value
    if isinstance(value, str):
        return _safe_str(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, complex):
        return [value.real, value.imag]
    return _safe_str(value)


def _header_to_dict(header: fits.Header) -> dict[str, Any]:
    """Flatten an astropy Header into a JSON-safe dict.

    Iterates over ``header.cards`` rather than ``dict(header)`` so that
    HIERARCH cards keep their full long keyword ("EPU Polarization") and so
    that repeated COMMENT/HISTORY cards collect into a list.

    Args:
        header: The FITS header to convert.

    Returns:
        A mapping of keyword to value.
    """
    out: dict[str, Any] = {}
    commentary: dict[str, list[str]] = {}
    for card in header.cards:
        try:
            keyword, value = card.keyword, card.value
        except Exception:  # unparseable card: skip rather than fail the read
            logger.warning(
                "Skipping unparseable FITS card: %r", getattr(card, "image", card)
            )
            continue
        keyword = str(keyword).strip()
        if not keyword:
            continue
        if keyword in _COMMENTARY_KEYWORDS:
            commentary.setdefault(keyword, []).append(_safe_str(value).strip())
            continue
        out[keyword] = _card_value(value)
    out.update(commentary)
    return out


def _table_to_dict(hdu: Any, index: int) -> dict[str, Any]:
    """Summarise a TABLE/BINTABLE extension, including its data if small.

    Args:
        hdu: The table HDU.
        index: Position of the HDU in the file.

    Returns:
        A summary with ``index``, ``extname``, ``rows`` and ``columns``, plus
        ``data`` (column name to values) when the table has at most
        ``MAX_TABLE_ROWS`` rows.
    """
    columns = [str(n) for n in (hdu.columns.names if hdu.columns else [])]
    rows = int(hdu.header.get("NAXIS2", 0))
    summary: dict[str, Any] = {
        "index": index,
        "extname": str(hdu.header.get("EXTNAME", "")).strip() or None,
        "rows": rows,
        "columns": columns,
    }
    if 0 < rows <= MAX_TABLE_ROWS:
        data = hdu.data
        summary["data"] = {name: np.asarray(data[name]).tolist() for name in columns}
    return summary


class FITSAdapter(ArrayAdapter):
    structure_family = StructureFamily.array

    def __init__(
        self,
        data_uri: str,
        structure: Optional[ArrayStructure] = None,
        metadata: Optional[JSON] = None,
        specs: Optional[list[Spec]] = None,
        **kwargs: Optional[Any],
    ) -> None:
        """Adapter for `.fits` CCD frames (e.g. RSoXS) at ALS beamline 11.0.1.2."""
        filepath = path_from_uri(data_uri)
        logger.debug(LOADING_MESSAGE, filepath)

        # memmap=False is required: astropy refuses to memory-map an image HDU
        # that carries BZERO/BSCALE, and these frames set BZERO=32768 to store
        # unsigned counts in a signed int16 HDU.
        with fits.open(filepath, memmap=False, lazy_load_hdus=False) as hdulist:
            index, image_hdu = _pick_image_hdu(hdulist)
            array = np.asarray(image_hdu.data)

            file_metadata = _header_to_dict(hdulist[0].header)
            image_header: dict[str, Any] = _header_to_dict(image_hdu.header)
            image_header["index"] = index
            extensions: dict[str, Any] = {}
            for other_index, hdu in enumerate(hdulist):
                if other_index == index or getattr(hdu, "is_image", False):
                    continue
                if getattr(hdu, "columns", None) is None:
                    continue
                name = str(hdu.header.get("EXTNAME", "")).strip() or f"HDU{other_index}"
                extensions[name] = _table_to_dict(hdu, other_index)

        # Tiled's JSON serializer rejects non-native byte order, and astropy
        # returns big-endian arrays for HDUs it does not rescale.
        native_dtype = array.dtype.newbyteorder("=")
        if array.dtype != native_dtype:
            array = array.astype(native_dtype)
        array = np.ascontiguousarray(array)

        # Nest the image header so its BITPIX/NAXIS/EXTNAME cards do not
        # clobber the primary header's, which is where the motors live.
        fits_metadata: dict[str, Any] = {**file_metadata, "image_hdu": image_header}
        if extensions:
            fits_metadata["extensions"] = extensions
        metadata = {**fits_metadata, **(metadata or {})}

        fits_spec = Spec("als-bl11012-fits", version="1.0")
        specs = list(specs or [])
        if fits_spec not in specs:
            specs.append(fits_spec)
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
    ) -> "FITSAdapter":
        return init_adapter_from_catalog(cls, data_source, node, **kwargs)

    @classmethod
    def from_uris(
        cls,
        data_uri: str,
        **kwargs: Optional[Any],
    ) -> "FITSAdapter":
        return cls(data_uri, **kwargs)
