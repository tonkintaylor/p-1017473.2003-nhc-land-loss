import numpy as np
import pytest

from landloss.io.shakemap import get_shakemap_grid

GRID = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<shakemap_grid xmlns="http://earthquake.usgs.gov/eqcenter/shakemap" event_id="x">
<event event_id="x" magnitude="6.9" />
<grid_specification lon_min="174.0" lat_min="-41.1" lon_max="174.2" lat_max="-41.0"
 nominal_lon_spacing="0.1" nominal_lat_spacing="0.1" nlon="3" nlat="2"/>
<grid_field index="1" name="LON" units="dd" />
<grid_field index="2" name="LAT" units="dd" />
<grid_field index="3" name="PGA" units="pctg" />
<grid_field index="4" name="PGV" units="cms" />
<grid_data>
174.0 -41.0 10 20
174.1 -41.0 11 21
174.2 -41.0 12 22
174.0 -41.1 13 23
174.1 -41.1 14 24
174.2 -41.1 15 25
</grid_data>
</shakemap_grid>
"""


def test_reads_fields_onto_a_north_up_grid(tmp_path):
    path = tmp_path / "grid.xml"
    path.write_text(GRID)
    ds = get_shakemap_grid(path)
    assert set(ds.data_vars) == {"pga", "pgv"}
    assert np.allclose(ds["x"], [174.0, 174.1, 174.2])
    assert np.allclose(ds["y"], [-41.0, -41.1])
    assert ds["pgv"].values[1, 2] == 25
    assert ds.attrs["magnitude"] == "6.9"
    assert ds.rio.crs.to_epsg() == 4326


def test_a_truncated_grid_is_refused(tmp_path):
    path = tmp_path / "grid.xml"
    path.write_text(GRID.replace("174.2 -41.1 15 25\n", ""))
    with pytest.raises(ValueError, match="needs 24"):
        get_shakemap_grid(path)
