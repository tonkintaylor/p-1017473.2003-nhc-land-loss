"""Drawing one exposure world's wall population from the line probabilities.

An exposure world is one answer to the question the inventory cannot: which of
the candidate lines are walls, and what type each one is. The existence draw is
one uniform per line, in line order, against the ``p_wall`` that
:mod:`landloss.exposure.rw.wall_probability` put on it, unless the caller
passes which lines are walled; the generator comes from the caller, seeded on
:data:`~landloss.domain.constants.EXPOSURE_BASE_SEED` and the world id
(:mod:`landloss.hazard.realisation`), so a world reproduces and is independent
of every earthquake it is later paired with.

A wall is the line that drew it: its geometry, height, size class and length
come straight off the line, nothing is placed or sized here. Its age bin and
wall type are drawn by the caller on their own stream
(:func:`landloss.exposure.rw.wall_type.draw_wall_types`) and attached here by
``wall_line_id``. ``gen_wall_population.py`` in exposure
rw step 6 drops the walls with no claim, applies the coverage filter and mints
``rw_id`` after the draw, so the stream is the same whatever those keep.
Those two filters decide what is insured, not whether a wall stands: a road
wall above a property still holds the slope. So the script also writes every
wall the world drew, with the minted ``rw_id`` joined back on
``wall_line_id`` where the wall survived both filters and null where it did
not (:func:`attach_rw_ids`); landslide step 8 builds the urban slope model on
that table (decision 36 of the build contract).

Whether a wall unit exists is drawn once per world in landslide step 12
(:func:`landloss.hazard.landslide.wall_units.gen_wall_draws`), so the walls
that shape the hazard are the walls that are exposed; that draw is passed in
as ``walled``. The claim reports (**T-50**) enter before either draw, as the
per-property update on the wall units' probabilities.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain.loss_contract import CLAIM_ID_COLUMN, RW_ID_COLUMN

WALL_LINE_ID_COLUMN = "wall_line_id"

# The line columns a drawn wall carries over, in the order of section 3.7 of
# the build contract with the wall type and age bin in place of the condition
# (.agents/plans/assigning-retaining-wall-types.md); rw_id and world_id are
# added by the script.
POPULATION_COLUMNS = (
    CLAIM_ID_COLUMN,
    WALL_LINE_ID_COLUMN,
    "size_class",
    "wall_type",
    "age_bin",
    "height_m",
    "length_m",
    "wall_position",
    "is_flatland",
    "source",
    "material",
    "geometry",
)

# Line columns carried over where the line table has them: the wall's length
# in every property it enters (landslide step 12's wall units, 2026-10-06),
# for the loss side to count a wall on each property it crosses, and the
# primary property it is drawn on.
OPTIONAL_COLUMNS = ("property_id", "property_lengths_m", "n_properties")

# What a drawn wall's height is on the line: the DEM face height.
HEIGHT_SOURCE_COLUMN = "face_height_m"

# The columns of the type draw a drawn wall takes, by its wall_line_id.
TYPE_COLUMNS = ("wall_type", "age_bin")

# The line columns the draw reads, beyond the ones carried over by name.
REQUIRED_COLUMNS = (
    CLAIM_ID_COLUMN,
    WALL_LINE_ID_COLUMN,
    "p_wall",
    "size_class",
    HEIGHT_SOURCE_COLUMN,
    "length_m",
    "wall_position",
    "is_flatland",
    "source",
    "material",
)


def draw_wall_population(
    probabilities: gpd.GeoDataFrame,
    rng: np.random.Generator,
    *,
    types: pd.DataFrame,
    walled: np.ndarray | None = None,
) -> gpd.GeoDataFrame:
    """Draw which candidate lines are walls, and give each its type.

    One uniform is compared per line in line order against ``p_wall``, so a
    line's draw depends on its position in the table and on nothing after it.
    A line whose ``p_wall`` is NaN draws no wall. Where ``walled`` is given it
    replaces the comparison. Each drawn wall takes its ``wall_type`` and
    ``age_bin`` from ``types`` by its ``wall_line_id``.

    Args:
        probabilities: The output of
            :func:`~landloss.exposure.rw.wall_probability.gen_unit_probability_table`,
            one row per candidate wall unit carrying :data:`REQUIRED_COLUMNS`.
        rng: The world's generator, so the draw reproduces.
        types: The world's type draw, indexed by ``wall_line_id``, carrying
            :data:`TYPE_COLUMNS`
            (:func:`~landloss.exposure.rw.wall_type.draw_wall_types`).
        walled: Optionally, whether each line is a wall, a bool per row of
            ``probabilities``, already drawn.

    Returns:
        The lines that drew a wall, carrying :data:`POPULATION_COLUMNS`
        and the :data:`OPTIONAL_COLUMNS` the lines have:
        ``wall_type`` and ``age_bin`` from ``types``, ``height_m`` the line's
        ``face_height_m``, the rest copied from the line, on a fresh index and
        in line order.

    Raises:
        ValueError: If a required column is missing from ``probabilities`` or
            ``types``, ``walled`` does not have one flag per row, ``types``
            repeats a line, or a drawn wall has no type.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in probabilities.columns]
    if missing:
        msg = f"probabilities is missing {missing}"
        raise ValueError(msg)
    missing = [c for c in TYPE_COLUMNS if c not in types.columns]
    if missing:
        msg = f"types is missing {missing}"
        raise ValueError(msg)
    if types.index.has_duplicates:
        msg = "types repeats a wall_line_id"
        raise ValueError(msg)

    # Two uniforms per line, as when the second drew the retired condition, so
    # the existence stream (column 0) is unchanged from earlier worlds.
    uniforms = rng.random((len(probabilities), 2))
    p_wall = probabilities["p_wall"].to_numpy(dtype=float)
    if walled is None:
        # NaN compares False, so a line with no probability draws nothing.
        has_wall = uniforms[:, 0] < p_wall
    else:
        has_wall = np.asarray(walled, dtype=bool)
        if has_wall.shape != (len(probabilities),):
            msg = (
                f"walled must hold one flag per line: got {has_wall.shape} for "
                f"{len(probabilities)} lines"
            )
            raise ValueError(msg)

    walls = probabilities.loc[has_wall]
    drawn_types = types.reindex(walls[WALL_LINE_ID_COLUMN].to_numpy())[
        list(TYPE_COLUMNS)
    ]
    untyped = drawn_types.isna().any(axis=1).to_numpy()
    if untyped.any():
        ids = walls.loc[untyped, WALL_LINE_ID_COLUMN].tolist()
        msg = f"drawn walls with no type: {ids[:5]}"
        raise ValueError(msg)
    return gpd.GeoDataFrame(
        {
            CLAIM_ID_COLUMN: walls[CLAIM_ID_COLUMN].to_numpy(),
            WALL_LINE_ID_COLUMN: walls[WALL_LINE_ID_COLUMN].to_numpy(),
            "size_class": walls["size_class"].to_numpy(),
            "wall_type": drawn_types["wall_type"].to_numpy(dtype=object),
            "age_bin": drawn_types["age_bin"].to_numpy(dtype=object),
            "height_m": walls[HEIGHT_SOURCE_COLUMN].to_numpy(dtype=float),
            "length_m": walls["length_m"].to_numpy(dtype=float),
            "wall_position": walls["wall_position"].to_numpy(),
            "is_flatland": walls["is_flatland"].to_numpy(dtype=bool),
            "source": walls["source"].to_numpy(),
            "material": walls["material"].to_numpy(),
            **{
                column: walls[column].to_numpy()
                for column in OPTIONAL_COLUMNS
                if column in walls.columns
            },
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
