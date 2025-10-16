import logging
import os
import pathlib
from logging import StreamHandler

import fabio
from tiled.adapters.array import ArrayAdapter
from tiled.structures.core import Spec
from tiled.utils import path_from_uri

logger = logging.getLogger("tiled.adapters.edf")
logger.addHandler(StreamHandler())
logger.setLevel("INFO")


def parse_txt_accompanying_edf(filepath):
    """Pase a .txt file produced at ALS beamline 7.3.3 into a dictionary.

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
        logger.warn(f"{filepath} has no corresponding .txt.")
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


def read(data_uri, structure=None, metadata=None, specs=None, access_policy=None):
    """Read a detector image saved as .edf produced at ALS beamline 7.3.3

    Parameters
    ----------
    data_uri: str
        Uri of the .edf file, typically a file:// uri.
    """
    # TODO Should we catch any read errors here?
    filepath = path_from_uri(data_uri)
    file = fabio.open(filepath)
    array = file.data

    # Merge parameters from the header into other meta data
    if metadata is None:
        metadata = file.header
    else:
        metadata = {**metadata, **file.header}

    # If a .txt file with the same name exists
    # extract additional meta data from it
    txt_params = parse_txt_accompanying_edf(filepath)
    metadata = {**metadata, **txt_params}
    return ArrayAdapter.from_array(array, metadata=metadata, specs=[Spec("edf")])


async def walk_edf_with_txt(
    catalog,
    path,
    files,
    directories,
    settings,
):
    """
    Possible patters:
    1-1 txt-edf
    1 log, many edfs
    1 txt - 2 edf with _hi _lo
    """
    # TODO
    unhandled_files = files
    unhandled_directories = directories
    return unhandled_files, unhandled_directories
