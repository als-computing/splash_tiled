import logging
import pathlib
from typing import Any

logger = logging.getLogger(__name__)


def parse_txt_accompanying_edf(filepath_edf: pathlib.Path) -> dict[str, Any]:
    """Parse the .txt metadata file accompanying an EDF file at ALS beamline 7.3.3.

    Parameters
    ----------
    filepath_edf:
        Path to the .edf file. The companion .txt is expected at the same path
        with the extension replaced by .txt.
    """
    filepath_txt = filepath_edf.with_suffix(".txt")

    if not filepath_txt.is_file():
        logger.warning(f"{filepath_edf} has no corresponding .txt.")
        return {}

    with open(filepath_txt) as f:
        lines = f.readlines()

    # Lines have the format "key: value" or are bare values with no key.
    metadata: dict[str, Any] = {}
    unnamed_count = 0
    for line in lines:
        before, sep, after = line.partition(":")
        if sep:
            metadata[before.strip()] = after.strip()
        elif before.strip() != "!0":
            metadata[f"unnamed_{unnamed_count}"] = before.strip()
            unnamed_count += 1
    return metadata
