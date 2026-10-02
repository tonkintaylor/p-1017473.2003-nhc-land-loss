import numpy as np

from landloss.common.utils.hydrology import (
    OUTLET,
    d8_receivers,
    flow_accumulation,
    priority_flood,
    route_grid,
)


def route(z, spacing=1.0):
    filled, order, parent = priority_flood(z)
    rows = z.shape[0]
    receiver = d8_receivers(filled, parent, np.full(rows, spacing), spacing)
    return filled, order, receiver


def test_a_pit_is_filled_to_its_spill_level():
    z = np.full((5, 5), 10.0)
    z[2, 2] = 1.0
    filled, _, _ = route(z)
    assert filled[2, 2] == 10.0


def test_every_cell_drains_to_the_single_outlet():
    # A bowl tilted towards one corner cell next to nodata: all the flow ends
    # there, so its accumulated count is every valid cell.
    y, x = np.indices((6, 6))
    z = (x + y).astype(float) + 1.0
    z[0, 0] = np.nan
    _, order, receiver = route(z)
    total = flow_accumulation(receiver, order, np.where(np.isnan(z), np.nan, 1.0))
    outlets = [
        i for i in order if receiver[i] == OUTLET or np.isnan(z.ravel()[receiver[i]])
    ]
    assert np.nansum(total.ravel()[outlets]) == np.sum(~np.isnan(z))


def test_a_flat_drains_rather_than_stalling():
    # A flat plateau walled on three sides, open to the sea on the west: every
    # cell reaches the sea, none is left pointing nowhere.
    z = np.full((5, 7), 5.0)
    z[0, :] = z[-1, :] = z[:, -1] = 50.0
    z[:, 0] = np.nan
    _, order, receiver = route(z)
    total = flow_accumulation(receiver, order, np.where(np.isnan(z), np.nan, 1.0))
    valid = ~np.isnan(z.ravel())
    drains_to_sea = [
        i
        for i in np.flatnonzero(valid)
        if receiver[i] != OUTLET and not valid[receiver[i]]
    ]
    edge_outlets = [i for i in np.flatnonzero(valid) if receiver[i] == OUTLET]
    outflow = total.ravel()[drains_to_sea + edge_outlets].sum()
    assert outflow == valid.sum()
    assert total[2, 1] > 1  # the plateau's interior drains west through here


def test_route_grid_accumulates_cell_area_to_the_outlets():
    # The tilted bowl again, in square metres: the area leaving the grid across
    # every outlet is the grid's whole valid area, and a cell holds at least
    # its own.
    y, x = np.indices((6, 6))
    z = (x + y).astype(float) + 1.0
    z[0, 0] = np.nan
    routing = route_grid(z, dx_m=10.0, dy_m=10.0)
    assert routing.filled.shape == z.shape
    assert np.isnan(routing.upstream_area_m2[0, 0])
    assert np.nanmin(routing.upstream_area_m2) == 100.0
    valid = ~np.isnan(z.ravel())
    outlets = [
        i
        for i in np.flatnonzero(valid)
        if routing.receiver[i] == OUTLET or not valid[routing.receiver[i]]
    ]
    assert routing.upstream_area_m2.ravel()[outlets].sum() == 35 * 100.0
    # The receiver of every cell comes earlier in the order than the cell.
    position = np.empty(z.size, dtype=int)
    position[routing.order] = np.arange(routing.order.size)
    for idx in routing.order:
        downstream = routing.receiver[idx]
        if downstream != OUTLET and not np.isnan(z.ravel()[downstream]):
            assert position[downstream] < position[idx]
