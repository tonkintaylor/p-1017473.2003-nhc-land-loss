"""Read a USGS ShakeMap ``grid.xml`` or ``uncertainty.xml`` into a Dataset.

ShakeMap publishes its gridded ground motions as XML: a ``grid_specification``
giving the node spacing and count, a list of ``grid_field`` names, and a block
of whitespace-separated rows, one per node, ordered from the north-west corner
row by row. Values sit on the nodes, so the nodes are treated as cell centres
here, which is also how the USGS ``groundfailure`` package resamples them.

Units are ShakeMap's own and are not converted: PGA and the PSA fields in %g,
PGV in cm/s, and the ``STD*`` fields of ``uncertainty.xml`` in natural-log
units.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr

_NAMESPACE = "{http://earthquake.usgs.gov/eqcenter/shakemap}"


def get_shakemap_grid(path: Path | str) -> xr.Dataset:
    """Read a ShakeMap grid file.

    Args:
        path: A ShakeMap ``grid.xml`` or ``uncertainty.xml``.

    Returns:
        One variable per grid field other than LON and LAT, named in lower case
        (``pga``, ``pgv``, ``stdpgv``, ...), on ``y`` (latitude, north first)
        and ``x`` (longitude) coordinates in EPSG:4326. The event's attributes
        (``event_id``, ``magnitude``, ...) are carried in ``attrs``.

    Raises:
        ValueError: If the number of values does not match the grid
            specification, which means the file is truncated or not a ShakeMap
            grid.
    """
    root = ET.parse(path).getroot()  # noqa: S314 -- a USGS product, not user input
    spec = root.find(f"{_NAMESPACE}grid_specification").attrib
    nlon, nlat = int(spec["nlon"]), int(spec["nlat"])
    fields = sorted(
        root.findall(f"{_NAMESPACE}grid_field"), key=lambda f: int(f.attrib["index"])
    )
    names = [f.attrib["name"].lower() for f in fields]
    values = np.array(root.find(f"{_NAMESPACE}grid_data").text.split(), dtype=float)
    if values.size != nlon * nlat * len(names):
        msg = (
            f"{Path(path).name} holds {values.size} values, but its grid "
            f"specification of {nlon} x {nlat} nodes and {len(names)} fields "
            f"needs {nlon * nlat * len(names)}."
        )
        raise ValueError(msg)
    table = values.reshape(nlat, nlon, len(names))

    lon = table[0, :, names.index("lon")]
    lat = table[:, 0, names.index("lat")]
    data = {
        name: (("y", "x"), table[:, :, i])
        for i, name in enumerate(names)
        if name not in {"lon", "lat"}
    }
    ds = xr.Dataset(data, coords={"y": lat, "x": lon})
    event = root.find(f"{_NAMESPACE}event")
    if event is not None:
        ds.attrs.update(event.attrib)
    return ds.rio.write_crs("EPSG:4326")
