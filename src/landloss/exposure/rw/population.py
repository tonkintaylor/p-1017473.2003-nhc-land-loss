"""Drawing one exposure world's wall population from the line probabilities.

An exposure world is one answer to the question the inventory cannot: which of
the candidate lines are walls, and which of those are in poor condition. The
draw is two uniforms per line, in line order, against the ``p_wall`` and
``p_poor`` that :mod:`landloss.exposure.rw.wall_probability` put on it; the
generator comes from the caller, seeded on
:data:`~landloss.domain.constants.EXPOSURE_BASE_SEED` and the world id
(:mod:`landloss.hazard.realisation`), so a world reproduces and is independent
of every earthquake it is later paired with.

A wall is the line that drew it: its geometry, height, size class and length
come straight off the line, nothing is placed or sized here. The condition is
the only thing drawn beyond existence. ``gen_wall_population.py`` in exposure
rw step 6 drops the walls with no claim, applies the coverage filter and mints
``rw_id`` after the draw, so the stream is the same whatever those keep.
Those two filters decide what is insured, not whether a wall stands: a road
wall above a property still holds the slope. So the script also writes every
wall the world drew, with the minted ``rw_id`` joined back on
``wall_line_id`` where the wall survived both filters and null where it did
not (:func:`attach_rw_ids`); landslide step 8 builds the urban slope model on
that table (decision 36 of the build contract).

The count bounds (**T-50**) enter before the draw, as a scaling of the
probabilities inside each property
(:func:`landloss.exposure.rw.wall_probability.apply_count_bounds`), so the
draw itself has no second form.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain.loss_contract import CLAIM_ID_COLUMN, RW_ID_COLUMN
from landloss.exposure.rw.beta_population import INITIAL_CONDITIONS

MODERN, POOR = INITIAL_CONDITIONS

WALL_LINE_ID_COLUMN = "wall_line_id"

# The line columns a drawn wall carries over, in the order of section 3.7 of
# the build contract; rw_id and world_id are added by the script.
POPULATION_COLUMNS = (
    CLAIM_ID_COLUMN,
    WALL_LINE_ID_COLUMN,
    "size_class",
    "initial_condition",
    "height_m",
    "length_m",
    "wall_position",
    "is_flatland",
    "source",
    "material",
    "geometry",
)

# What a drawn wall's height is on the line: the DEM face height.
HEIGHT_SOURCE_COLUMN = "face_height_m"

# The line columns the draw reads, beyond the ones carried over by name.
REQUIRED_COLUMNS = (
    CLAIM_ID_COLUMN,
    WALL_LINE_ID_COLUMN,
    "p_wall",
    "p_poor",
    "size_class",
    HEIGHT_SOURCE_COLUMN,
    "length_m",
    "wall_position",
    "is_flatland",
    "source",
    "material",
)


def draw_wall_population(
    probabilities: gpd.GeoDataFrame, rng: np.random.Generator
) -> gpd.GeoDataFrame:
    """Draw which candidate lines are walls, and the condition of each.

    Two uniforms are drawn per line in line order, the first against
    ``p_wall`` and the second against ``p_poor``, so a line's draw depends on
    its position in the table and on nothing after it. A line whose ``p_wall``
    is NaN draws no wall.

    Args:
        probabilities: The output of
            :func:`~landloss.exposure.rw.wall_probability.wall_probability_table`,
            one row per candidate line carrying :data:`REQUIRED_COLUMNS`.
        rng: The world's generator, so the draw reproduces.

    Returns:
        The lines that drew a wall, carrying :data:`POPULATION_COLUMNS`:
        ``initial_condition`` drawn, ``height_m`` the line's ``face_height_m``,
        the rest copied from the line, on a fresh index and in line order.

    Raises:
        ValueError: If a required column is missing.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in probabilities.columns]
    if missing:
        msg = f"probabilities is missing {missing}"
        raise ValueError(msg)

    uniforms = rng.random((len(probabilities), 2))
    p_wall = probabilities["p_wall"].to_numpy(dtype=float)
    p_poor = probabilities["p_poor"].to_numpy(dtype=float)
    # NaN compares False, so a line with no probability draws nothing.
    has_wall = uniforms[:, 0] < p_wall
    poor = uniforms[:, 1] < p_poor

    walls = probabilities.loc[has_wall]
    condition = np.where(poor[has_wall], POOR, MODERN)
    return gpd.GeoDataFrame(
        {
            CLAIM_ID_COLUMN: walls[CLAIM_ID_COLUMN].to_numpy(),
            WALL_LINE_ID_COLUMN: walls[WALL_LINE_ID_COLUMN].to_numpy(),
            "size_class": walls["size_class"].to_numpy(),
            "initial_condition": condition,
            "height_m": walls[HEIGHT_SOURCE_COLUMN].to_numpy(dtype=float),
            "length_m": walls["length_m"].to_numpy(dtype=float),
            "wall_position": walls["wall_position"].to_numpy(),
            "is_flatland": walls["is_flatland"].to_numpy(dtype=bool),
            "source": walls["source"].to_numpy(),
            "material": walls["material"].to_numpy(),
        },
        geometry=walls.geometry.to_numpy(),
        crs=probabilities.crs,
    ).reset_index(drop=True)


def attach_rw_ids(
    drawn: gpd.GeoDataFrame, population: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Give every drawn wall the ``rw_id`` it was minted, null where none was.

    The claim filter and the insured land coverage filter decide which drawn
    walls are insured; they do not decide whether a wall stands. A council or
    road-reserve wall with no claim, or a wall at the back of a section beyond
    the coverage buffer, still holds its slope in the world, so the urban slope
    model must see it (decision 36 of the build contract). This keeps every
    drawn wall and joins the insured population's ``rw_id`` back onto it by
    ``wall_line_id``.

    Args:
        drawn: :func:`draw_wall_population`'s output for one world, one row
            per line that drew a wall, carrying :data:`POPULATION_COLUMNS`.
        population: The insured subset of ``drawn`` after the claim and
            coverage filters, carrying ``rw_id`` and ``wall_line_id``.

    Returns:
        A copy of ``drawn`` in its own order, on a fresh index, with ``rw_id``
        inserted as the first column: the minted id where the wall is in
        ``population``, ``None`` otherwise.

    Raises:
        ValueError: If a ``wall_line_id`` repeats in either frame, or
            ``population`` names a line ``drawn`` does not carry.
    """
    for name, frame in (("drawn", drawn), ("population", population)):
        repeated = frame[WALL_LINE_ID_COLUMN].duplicated()
        if repeated.any():
            ids = frame.loc[repeated, WALL_LINE_ID_COLUMN].unique().tolist()
            msg = f"{name} repeats wall_line_id {ids[:5]}"
            raise ValueError(msg)
    strangers = ~population[WALL_LINE_ID_COLUMN].isin(drawn[WALL_LINE_ID_COLUMN])
    if strangers.any():
        ids = population.loc[strangers, WALL_LINE_ID_COLUMN].tolist()
        msg = f"population names lines that drew no wall: {ids[:5]}"
        raise ValueError(msg)

    minted = population.set_index(WALL_LINE_ID_COLUMN)[RW_ID_COLUMN]
    rw_ids = drawn[WALL_LINE_ID_COLUMN].map(minted)
    out = drawn.reset_index(drop=True)
    out.insert(
        0,
        RW_ID_COLUMN,
        pd.Series(
            rw_ids.astype(object).where(rw_ids.notna(), None).to_numpy(),
            dtype=object,
        ),
    )
    return out
