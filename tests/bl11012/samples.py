"""Helpers that write small synthetic BL11.0.1.2 FITS files.

They mirror the real ALS CCD layout (metadata-only primary HDU, an ``Izeros``
BINTABLE, and the frame in an IMAGE extension named ``Images`` with BZERO
rescaling) without needing the real 33 MB files.
"""

from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pytest

fits = pytest.importorskip("astropy.io.fits")

SAMPLE_FITS_DATA = np.array([[0, 1, 65535], [10, 20, 30], [1, 2, 3]], dtype=np.uint16)


def base_primary_header():
    """Primary header with HIERARCH, boolean, undefined and COMMENT cards."""
    header = fits.Header()
    header["HIERARCH EPU Polarization"] = (100.0, "Counts")
    header["FLAG"] = True
    header["UNDEF"] = fits.card.Undefined()
    header["COMMENT"] = "first comment"
    header["COMMENT"] = "second comment"
    return header


def make_fits(
    tmp_path: Path,
    *,
    filename: str = "frame.fits",
    image_extname: str = "Images",
    include_decoy: bool = True,
    include_izeros: bool = True,
    izeros_values: Sequence[float] = (1.1, 2.2, 3.3, 4.4),
    image_data: Optional[np.ndarray] = None,
) -> Path:
    """Write a FITS file shaped like an ALS CCD frame and return its path."""
    primary = fits.PrimaryHDU()
    primary.header.update(base_primary_header())

    hdus = [primary]
    if include_decoy:
        decoy = fits.ImageHDU(data=np.zeros((4, 4), dtype=np.uint8))
        decoy.header["EXTNAME"] = "Decoy"
        hdus.append(decoy)

    if image_data is None:
        image_data = SAMPLE_FITS_DATA
    # Set EXTNAME directly rather than via name=: astropy uppercases that, but
    # the real files store mixed-case 'Images'/'Izeros'.
    image_hdu = fits.ImageHDU(data=image_data)
    image_hdu.header["EXTNAME"] = image_extname
    hdus.append(image_hdu)

    if include_izeros:
        col = fits.Column(
            name="0", format="E", array=np.asarray(izeros_values, dtype=np.float32)
        )
        table = fits.BinTableHDU.from_columns([col])
        table.header["EXTNAME"] = "Izeros"
        hdus.append(table)

    path = tmp_path / filename
    fits.HDUList(hdus).writeto(path, overwrite=True)
    return path
