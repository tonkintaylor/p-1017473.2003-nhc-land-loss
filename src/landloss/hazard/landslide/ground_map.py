"""The reconciled ground map: one planar partition of the slopes, attributed.

What belongs here: the attribute vocabulary of the map (material, modification,
prior failure, groundwater depth class and confidence), the mapping of each
source layer's values onto that vocabulary and the precedence between sources,
the union overlay that builds the partition, the representative-point lookup
that attributes each polygon, and :func:`strength_from_material`, which reads
the Wellington greywacke strength table packaged in :mod:`landloss.io.assets`.
The layer is built by landslide step 4 (``s4_ground_map``).

The map is non-probabilistic and world independent. Every source is a polygon
layer whose boundaries are unioned into one planar partition, and each piece of
that partition takes its attributes from the first source, in precedence order,
whose polygon contains the piece's representative point. Where no source
reaches, the defaults are ``unknown`` material, ``natural`` modification, no
prior failure and an assumed groundwater depth. The precedence per attribute
is section 9.3 of ``.agents/plans/urban-slope-build-contract.md``; the
vocabulary is section 9.1 and the source mappings section 9.2.

Two of the attributes follow from ``material`` by lookup rather than from a
source: the Kingsbury geology factor value [kingsbury_1995] through
:data:`MATERIAL_GEOLOGY_VALUES`, and the effective strength set through
:data:`MATERIAL_STRENGTH_GRADE` and the packaged strength table.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd
import shapely
import xarray as xr
from rasterio import features

from landloss.domain import constants
from landloss.hazard.landslide import susceptibility
from landloss.io import ASSETS_DIR


def flatland_cell_mask(
    ground_map: gpd.GeoDataFrame, template: xr.DataArray
) -> np.ndarray:
    """Return true where a raster cell centre lies on NLM flatland."""
    flat = ground_map.loc[ground_map["is_flatland"].astype(bool), "geometry"]
    if flat.empty:
        return np.zeros(template.shape, dtype=bool)
    burned = features.rasterize(
        ((geometry, 1) for geometry in flat),
        out_shape=template.shape,
        transform=template.rio.transform(),
        fill=0,
        dtype="uint8",
    )
    return burned.astype(bool)


# ---------------------------------------------------------------------------
# Vocabulary (contract section 9.1)
# ---------------------------------------------------------------------------

UNKNOWN = "unknown"
ASSUMED = "assumed"
NATURAL = "natural"
NO_PRIOR_FAILURE = "none"

# Open water is not ground. A material mapper hands this back for a water
# class, and build_ground_map drops the pieces whose only material source says
# so rather than giving them a material.
WATER = "water"

MATERIALS = (
    "rock",
    "rock_uw_mw",
    "rock_hw_cw",
    "rock_crushed",
    "colluvium",
    "loess",
    "alluvium",
    "fill_engineered",
    "fill_uncontrolled",
    "reclamation",
    UNKNOWN,
)
# The materials that are rock (contract section 9.1); the wall lines read it to
# mark a rock cut, which stands unsupported.
ROCK_MATERIALS = ("rock", "rock_uw_mw", "rock_hw_cw", "rock_crushed")
MODIFICATIONS = ("cut", "fill", NATURAL, UNKNOWN)
PRIOR_FAILURES = ("relict", "recent", NO_PRIOR_FAILURE)
GW_DEPTH_CLASSES = ("saturated", "poorly_drained", "well_drained")
CONFIDENCES = ("high", "medium", "low")

# The source name written where the groundwater depth comes from the NLM grid.
NLM_GWD_SOURCE = "nlm_gwd"

# The attributes a GroundSource may supply, and the columns each writes.
ATTRIBUTES = (
    "material",
    "modification",
    "prior_failure",
    "gw_depth_m",
    "fill_thickness_m",
)

# Kingsbury's F_geology per material [kingsbury_1995], Table 4. Rock of
# unknown weathering grade takes the highly to completely weathered class, as
# the NLM mapping in susceptibility already assumes for Wellington basement.
MATERIAL_GEOLOGY_VALUES: dict[str, float] = {
    "rock": susceptibility.GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED,
    "rock_uw_mw": susceptibility.GEOLOGY_UNWEATHERED_TO_MODERATELY_WEATHERED,
    "rock_hw_cw": susceptibility.GEOLOGY_HIGHLY_TO_COMPLETELY_WEATHERED,
    "rock_crushed": susceptibility.GEOLOGY_CRUSHED_AND_SHATTERED_GREYWACKE,
    "colluvium": susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "loess": susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "alluvium": susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "fill_engineered": susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "fill_uncontrolled": susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "reclamation": susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    UNKNOWN: float("nan"),
}

# The weathering grade of the strength table each material reads its strength
# set from. ``unknown`` has no grade and takes NaN.
MATERIAL_STRENGTH_GRADE: dict[str, str] = {
    "rock": "HW",
    "rock_hw_cw": "HW",
    "rock_uw_mw": "MW",
    "rock_crushed": "CW",
    "colluvium": "COL",
    "loess": "RS",
    "alluvium": "RS",
    "fill_engineered": "FILL",
    "fill_uncontrolled": "FILL",
    "reclamation": "FILL",
}

STRENGTH_TABLE_PATH = ASSETS_DIR / "wellington-greywacke-strength.csv"

# The strength row a grade reads where the pick rule's file order is not the
# choice. FILL reads S52, the set GNS supplied for modelling the Priscilla and
# Orchy Crescent greywacke-derived fills (22 kN/m3, c' 2 kPa, phi' 42 deg)
# [monteith_2020], rather than S48, one Orchy Crescent sample's first shear
# stage, a maximum on a densifying sample with no clear peak [lyndsell_2019].
# Brown and Larkin's compacted Wellington fill, phi' 32 deg and c' 5 kPa
# [brown_larkin_2005], is the low case. Accepted by the lead on 2026-10-02.
STRENGTH_GRADE_PICKS: dict[str, str] = {"FILL": "S52"}

# The three strength columns a row has to carry in full to be a usable set.
STRENGTH_VALUE_COLUMNS = ("c_eff_kpa", "phi_eff_deg", "unit_weight_kn_m3")

# ---------------------------------------------------------------------------
# Source mappings (contract section 9.2)
# ---------------------------------------------------------------------------

# The fourteen ``Type`` classes of the SLIDE interpreted materials layer
# (``landloss.io.readers.get_slide_interpreted_materials``; [townsend_2020]).
# "Fill" carries no statement of whether it was engineered, so it takes the
# uncontrolled class; talus and boulders are material that has moved
# downslope, which is colluvium in Kingsbury's vocabulary. Water is not ground.
#
# A mixed fill class is a map unit, not a statement that the whole polygon is
# fill [townsend_2020], and most gully fills in greater Wellington are too
# small to map at all [begg_2000]. So a mixed class takes its natural material
# as the material and records the fill as the modification
# (SLIDE_FILL_TYPES), and where it names colluvium and rock, colluvium wins:
# Wellington fills fail on the buried colluvium at their base, which is weaker
# than the fill above it [brown_larkin_2005; lyndsell_2019; monteith_2020].
# Accepted by the lead on 2026-10-02 (step 4 plan, phase 2).
SLIDE_MATERIALS: dict[str, str] = {
    "Rock at/near surface": "rock",
    "Colluvium (anything that has moved downslope)": "colluvium",
    "Talus": "colluvium",
    "Boulders": "colluvium",
    "Loess": "loess",
    "Alluvium": "alluvium",
    "Sand and gravel": "alluvium",
    "Fill": "fill_uncontrolled",
    "Mixed fill/rock": "rock",
    "Mixed fill/colluvium": "colluvium",
    "Mixed fill/colluvium/rock": "colluvium",
    "Mixed fill/talus": "colluvium",
    "Old alluvium (mixed fill)": "alluvium",
    "Water body": WATER,
}

# The SLIDE material types that say the ground has been filled, and so claim
# the modification as well as the material; every other type claims the
# material only.
SLIDE_FILL_TYPES = (
    "Fill",
    "Mixed fill/rock",
    "Mixed fill/colluvium",
    "Mixed fill/colluvium/rock",
    "Mixed fill/talus",
    "Old alluvium (mixed fill)",
)
SLIDE_MODIFICATIONS: dict[str, str] = dict.fromkeys(SLIDE_FILL_TYPES, "fill")

# Every ``unit_code`` of the 1:50,000 geology layer
# (``landloss.io.readers.get_wellington_urban_geology``; [begg_mazengarb_1996]),
# the 74 codes the layer carried on 1 October 2026. The basement greywacke,
# melange and the Tertiary sedimentary units are rock; the loess-covered
# alluvial gravels (``uQal``, ``eQal``) take loess as their surface mantle;
# fan, scree and colluvial gravels are colluvium; floodplain, alluvial, beach,
# marine, swamp and dune deposits are alluvium; construction and rubbish fill
# are uncontrolled fill. A ``?`` prefix is the map's own uncertainty mark and
# does not change the class.
GEOLOGY_MATERIALS: dict[str, str] = {
    # Torlesse basement: greywacke, argillite, melange, and their volcanic and
    # chert members.
    "Tt": "rock",
    "Te": "rock",
    "Ttm": "rock",
    "Tem": "rock",
    "Teb": "rock",
    "Tebc": "rock",
    "Tebl": "rock",
    "Teab": "rock",
    "Ttab": "rock",
    "Ttb": "rock",
    "Ttbc": "rock",
    "Ttc": "rock",
    "Ttacb": "rock",
    "Ttmac": "rock",
    # Paleogene sedimentary rocks.
    "Pep": "rock",
    "Pea": "rock",
    # Fan, scree and colluvial gravels.
    "Q1af": "colluvium",
    "Q1af_t": "colluvium",
    # Loess-covered alluvial gravels.
    "eQal": "loess",
    "uQal": "loess",
    "uQal_t": "loess",
    "?uQal": "loess",
    "?uQal_t": "loess",
    "?uQal+Q2_t": "loess",
    "uQal+Q1a": "loess",
    "uQal+Q1a_t": "loess",
    # Floodplain and alluvial gravels.
    "Q1al_c": "alluvium",
    "Q1al_ct": "alluvium",
    "Q1al_m": "alluvium",
    "Q1al_mt": "alluvium",
    "Q1al_c/Q1m": "alluvium",
    "Q1al_c+Q2a": "alluvium",
    "Q1al_c+Q2a_t": "alluvium",
    "Q1al+Q1": "alluvium",
    "Q1al+Q1_t": "alluvium",
    "Q1al+Q1m": "alluvium",
    "Q2al": "alluvium",
    "Q2al_t": "alluvium",
    "Q2al_m/Q2as": "alluvium",
    "?Q2al": "alluvium",
    "?Q2al_t": "alluvium",
    "Q5al": "alluvium",
    "Q5al_t": "alluvium",
    # Swamp deposits.
    "Q1as": "alluvium",
    "Q1as_c+Q1m": "alluvium",
    # Beach and marine gravels.
    "Q1b": "alluvium",
    "Q1b_t": "alluvium",
    "Q1b_f": "alluvium",
    "Q1b_f/Q1m": "alluvium",
    "Q1b_m": "alluvium",
    "Q1b_mt": "alluvium",
    "Q1b_m/Q1m": "alluvium",
    "Q1b_m+Tt": "alluvium",
    "Q1b_vf/Q1m": "alluvium",
    "Q1b+Q1a": "alluvium",
    "Q1b+Q1a_t": "alluvium",
    "?Q1b": "alluvium",
    "Q5b": "alluvium",
    "Q5b_t": "alluvium",
    "Q5ba": "alluvium",
    "Q5bc": "alluvium",
    "Q5be": "alluvium",
    "?Q5b": "alluvium",
    "?Q5b_t": "alluvium",
    "Q7b_t": "alluvium",
    "mQb_t": "alluvium",
    # Fixed dunes.
    "Q1df/Q1m": "alluvium",
    "Q1df_m": "alluvium",
    "Q1df_mt": "alluvium",
    "Q1df_t": "alluvium",
    # Fill.
    "Q1nc": "fill_uncontrolled",
    "Q1nc_c": "fill_uncontrolled",
    "Q1nr": "fill_uncontrolled",
}

# The NLM ``l3_yp`` classes (``landloss.io.readers.get_nlm_geomorphology``),
# the regional fallback. The same classes susceptibility scores.
NLM_MATERIALS: dict[str, str] = {
    "Sedimentary": "rock",
    "Metamorphic": "rock",
    "Igneous": "rock",
    "Talus": "colluvium",
    "Colluvium": "colluvium",
    "Loess": "loess",
    "River channel": "alluvium",
    "Floodplain": "alluvium",
    "Foreshore": "alluvium",
    "Swamp": "alluvium",
    "Uncompacted fill": "fill_uncontrolled",
    "Compacted fill": "fill_engineered",
    "Water body": WATER,
}

# The fifteen ``Type`` values of the SLIDE genesis layer
# (``landloss.io.readers.get_slide_genesis``), each claiming one attribute or
# none. The three tuples partition the fifteen.
GENESIS_MODIFICATION_TYPES = (
    "Cut slope",
    "Fill body",
    "Landfill",
    "Dam (material would be fill)",
)
GENESIS_PRIOR_FAILURE_TYPES = ("Landslide relict", "Landslide recent", "Rockfall")
GENESIS_NO_CLAIM_TYPES = (
    "Modified terrain",
    "Terracettes",
    "Fan",
    "Dune",
    "Gully erosion",
    "Beach",
    "Swamp/wetland",
    "Seepage (damp areas)",
)
GENESIS_TYPES = (
    *GENESIS_MODIFICATION_TYPES,
    *GENESIS_PRIOR_FAILURE_TYPES,
    *GENESIS_NO_CLAIM_TYPES,
)

GENESIS_MODIFICATIONS: dict[str, str] = {
    "Cut slope": "cut",
    "Fill body": "fill",
    "Landfill": "fill",
    "Dam (material would be fill)": "fill",
}

# The rockfall subtypes, both of which count as a relict failure: scattered
# boulders are evidence the slope above has failed, undated.
ROCKFALL_SUBTYPES = ("few", "many")

WCC_MODIFICATIONS: dict[str, str] = {"cut": "cut", "fill": "fill"}


@dataclass(frozen=True)
class GroundSource:
    """One polygon layer supplying one attribute of the ground map.

    Attributes:
        name: The source's name, written to the attribute's ``*_source``
            column, for example ``"slide_materials"``.
        frame: The polygons, carrying ``column``, in a projected system.
        column: The column of ``frame`` holding the attribute, already in the
            vocabulary of ``attribute`` (or in metres for the two depths).
        attribute: Which attribute the source supplies, one of
            :data:`ATTRIBUTES`.
        confidence: The confidence written beside the attribute, one of
            :data:`CONFIDENCES`.
    """

    name: str
    frame: gpd.GeoDataFrame
    column: str
    attribute: str
    confidence: str


def _map_classes(values: pd.Series, mapping: dict[str, str], what: str) -> pd.Series:
    """Map a source's own classes onto the vocabulary, refusing any unlisted one.

    Args:
        values: The source's classes.
        mapping: Source class to vocabulary value.
        what: What the classes are, for the error message.

    Returns:
        The vocabulary value for each class, on ``values.index``.

    Raises:
        ValueError: If a class has no rule, which means the source has gained a
            class and somebody has to decide what it is rather than have it
            defaulted.
    """
    unknown = set(values.dropna().unique()) - set(mapping)
    if unknown:
        known = ", ".join(repr(name) for name in sorted(mapping))
        msg = (
            f"No rule maps the {what} {', '.join(repr(n) for n in sorted(unknown))} "
            f"onto the ground map vocabulary. Known: {known}"
        )
        raise ValueError(msg)
    return values.map(mapping)


def material_from_slide(types: pd.Series) -> pd.Series:
    """Map the SLIDE interpreted materials ``Type`` onto the material vocabulary.

    Args:
        types: The ``Type`` column of
            :func:`landloss.io.readers.get_slide_interpreted_materials`.

    Returns:
        The material for each polygon, on the caller's index; :data:`WATER`
        for a water body.

    Raises:
        ValueError: If a type is not one of the fourteen in
            :data:`SLIDE_MATERIALS`.
    """
    return _map_classes(types, SLIDE_MATERIALS, "SLIDE material type(s)")


def modification_from_slide(types: pd.Series) -> pd.Series:
    """Map a SLIDE interpreted materials ``Type`` that names fill to ``fill``.

    Only the fill types in :data:`SLIDE_FILL_TYPES` have a rule; the caller
    filters the materials frame to them first.

    Args:
        types: The ``Type`` column of
            :func:`landloss.io.readers.get_slide_interpreted_materials`,
            filtered.

    Returns:
        ``fill`` for each polygon, on the caller's index.

    Raises:
        ValueError: If a type does not name fill.
    """
    return _map_classes(types, SLIDE_MODIFICATIONS, "SLIDE material type(s)")


def material_from_geology(unit_codes: pd.Series) -> pd.Series:
    """Map the 1:50,000 geology ``unit_code`` onto the material vocabulary.

    Args:
        unit_codes: The ``unit_code`` column of
            :func:`landloss.io.readers.get_wellington_urban_geology`.

    Returns:
        The material for each polygon, on the caller's index.

    Raises:
        ValueError: If a code is not in :data:`GEOLOGY_MATERIALS`.
    """
    return _map_classes(unit_codes, GEOLOGY_MATERIALS, "geology unit code(s)")


def material_from_nlm(l3_yp: pd.Series) -> pd.Series:
    """Map the NLM geomorphology ``l3_yp`` class onto the material vocabulary.

    Args:
        l3_yp: The ``l3_yp`` column of
            :func:`landloss.io.readers.get_nlm_geomorphology`.

    Returns:
        The material for each polygon, on the caller's index; :data:`WATER`
        for a water body.

    Raises:
        ValueError: If a class is not in :data:`NLM_MATERIALS`.
    """
    return _map_classes(l3_yp, NLM_MATERIALS, "NLM material class(es)")


def modification_from_genesis(types: pd.Series) -> pd.Series:
    """Map the SLIDE genesis ``Type`` of a modified-ground polygon to cut or fill.

    Only the claiming types in :data:`GENESIS_MODIFICATION_TYPES` have a rule;
    the caller filters the genesis frame to them first.

    Args:
        types: The ``Type`` column of
            :func:`landloss.io.readers.get_slide_genesis`, filtered.

    Returns:
        ``cut`` or ``fill`` for each polygon, on the caller's index.

    Raises:
        ValueError: If a type does not claim the modification attribute.
    """
    return _map_classes(types, GENESIS_MODIFICATIONS, "genesis type(s)")


def modification_from_wcc(kind: pd.Series) -> pd.Series:
    """Map a Wellington City Council earthworks kind to cut or fill.

    Args:
        kind: ``"cut"`` for a polygon of
            :func:`landloss.io.readers.get_wcc_cut_areas` and ``"fill"`` for
            one of :func:`~landloss.io.readers.get_wcc_fill_areas`.

    Returns:
        ``cut`` or ``fill`` for each polygon, on the caller's index.

    Raises:
        ValueError: If a kind is neither.
    """
    return _map_classes(kind, WCC_MODIFICATIONS, "earthworks kind(s)")


def modification_from_residual(
    residual_m: npt.NDArray[np.floating], *, threshold_m: float
) -> npt.NDArray[np.object_]:
    """Class the cut-and-fill residual as cut, fill or natural ground.

    The residual is the 1 m surface minus a coarser one, negative where the
    ground has been cut below its surroundings and positive where it stands
    above them (``landloss.common.utils.terrain.cut_fill_residual``).

    Args:
        residual_m: The residual, in metres.
        threshold_m: The magnitude beyond which the residual marks a cut or a
            fill; between the two the ground is natural.

    Returns:
        ``cut``, ``fill`` or ``natural`` per cell, ``unknown`` where the
        residual is NaN.

    Raises:
        ValueError: If the threshold is not positive.
    """
    if threshold_m <= 0:
        msg = f"threshold_m has to be positive, not {threshold_m}"
        raise ValueError(msg)
    residual_m = np.asarray(residual_m, dtype=float)
    classed = np.full(residual_m.shape, NATURAL, dtype=object)
    classed[residual_m < -threshold_m] = "cut"
    classed[residual_m > threshold_m] = "fill"
    classed[np.isnan(residual_m)] = UNKNOWN
    return classed


def prior_failure_from_genesis(types: pd.Series, subtypes: pd.Series) -> pd.Series:
    """Map a SLIDE genesis landslide or rockfall polygon to relict or recent.

    Both rockfall subtypes count as relict: scattered boulders are evidence the
    slope above has failed, undated.

    Args:
        types: The ``Type`` column of
            :func:`landloss.io.readers.get_slide_genesis`, filtered to
            :data:`GENESIS_PRIOR_FAILURE_TYPES`.
        subtypes: The ``Subtype`` column, on the same index.

    Returns:
        ``relict`` or ``recent`` for each polygon, on the caller's index.

    Raises:
        ValueError: If a type does not claim the prior failure attribute, or a
            rockfall carries a subtype other than ``few`` or ``many``.
    """
    mapping = {"Landslide relict": "relict", "Landslide recent": "recent"}
    rockfall = types == "Rockfall"
    bad_subtype = rockfall & ~subtypes.isin(ROCKFALL_SUBTYPES)
    if bad_subtype.any():
        found = ", ".join(repr(s) for s in sorted(subtypes[bad_subtype].astype(str)))
        msg = (
            f"Rockfall subtype(s) {found} have no prior failure rule; "
            f"known: {', '.join(repr(s) for s in ROCKFALL_SUBTYPES)}"
        )
        raise ValueError(msg)
    mapped = _map_classes(types[~rockfall], mapping, "genesis type(s)")
    result = pd.Series("relict", index=types.index, dtype=object)
    result[~rockfall] = mapped
    return result


def gw_depth_class_from_depth(
    depth_m: npt.NDArray[np.floating],
) -> npt.NDArray[np.object_]:
    """Class a depth to groundwater as saturated, poorly drained or well drained.

    The breaks are this study's reading of Kingsbury's three drainage
    conditions [kingsbury_1995], held in
    :mod:`landloss.hazard.landslide.susceptibility`: saturated at or above
    ``GROUNDWATER_SATURATED_DEPTH_M``, poorly drained at or above
    ``GROUNDWATER_POORLY_DRAINED_DEPTH_M``, well drained below.

    Args:
        depth_m: Depth to groundwater in metres below ground.

    Returns:
        The class per value, ``None`` where the depth is NaN.
    """
    depth_m = np.asarray(depth_m, dtype=float)
    classed = np.full(depth_m.shape, "well_drained", dtype=object)
    classed[depth_m <= susceptibility.GROUNDWATER_POORLY_DRAINED_DEPTH_M] = (
        "poorly_drained"
    )
    classed[depth_m <= susceptibility.GROUNDWATER_SATURATED_DEPTH_M] = "saturated"
    classed[np.isnan(depth_m)] = None
    return classed


def kingsbury_geology_value(materials: pd.Series) -> pd.Series:
    """Score Kingsbury's geology factor, F_geology, from the material.

    Args:
        materials: Materials in the vocabulary of :data:`MATERIALS`.

    Returns:
        The factor value, 0 to 10, on the caller's index; NaN for ``unknown``.

    Raises:
        ValueError: If a material is not in the vocabulary.
    """
    unknown = set(materials.dropna().unique()) - set(MATERIAL_GEOLOGY_VALUES)
    if unknown:
        msg = (
            f"{', '.join(repr(m) for m in sorted(unknown))} are not ground map "
            f"materials; known: {', '.join(repr(m) for m in MATERIALS)}"
        )
        raise ValueError(msg)
    return materials.map(MATERIAL_GEOLOGY_VALUES).astype(float)


def _as_bool(values: pd.Series) -> pd.Series:
    """Read a ``check`` column as booleans whether it was parsed or left as text."""
    mapping = {True: True, False: False, "True": True, "False": False}
    unknown = set(values.unique()) - set(mapping)
    if unknown:
        msg = f"check column holds {sorted(map(str, unknown))}; expected True or False"
        raise ValueError(msg)
    return values.map(mapping).astype(bool)


def _pick_strength_row(strength_table: pd.DataFrame, grade: str) -> pd.Series:
    """Choose the one strength row a grade reads.

    A grade in :data:`STRENGTH_GRADE_PICKS` reads the row it names, which has
    to be of that grade and carry all three of :data:`STRENGTH_VALUE_COLUMNS`.
    Otherwise, among the rows of ``grade`` carrying all three: ``check`` false
    before true, then ``source_type == "published"`` before the rest, then
    file order.
    """
    rows = strength_table.loc[strength_table["grade"] == grade]
    complete = rows.dropna(subset=list(STRENGTH_VALUE_COLUMNS))
    if grade in STRENGTH_GRADE_PICKS:
        record_id = STRENGTH_GRADE_PICKS[grade]
        picked = complete.loc[complete["record_id"] == record_id]
        if picked.empty:
            msg = (
                f"The strength pick for grade {grade!r} is {record_id!r}, but no "
                f"row {record_id!r} of that grade carries all of "
                f"{', '.join(STRENGTH_VALUE_COLUMNS)}."
            )
            raise ValueError(msg)
        return picked.iloc[0]
    if complete.empty:
        msg = (
            f"No row of grade {grade!r} in the strength table carries all of "
            f"{', '.join(STRENGTH_VALUE_COLUMNS)}, so no strength set can be chosen."
        )
        raise ValueError(msg)
    ordered = complete.assign(
        _check=_as_bool(complete["check"]),
        _unpublished=complete["source_type"] != "published",
    ).sort_values(["_check", "_unpublished"], kind="mergesort")
    return ordered.iloc[0]


def strength_from_material(
    materials: pd.Series, strength_table: pd.DataFrame
) -> pd.DataFrame:
    """Look up the effective strength set each material reads.

    The grade is :data:`MATERIAL_STRENGTH_GRADE` of the material, and the row
    of that grade is the one :func:`_pick_strength_row` chooses. The unit
    weight is required alongside the two strength parameters because the
    readers downstream take the three together, and a row missing one is not a
    set.

    Args:
        materials: Materials in the vocabulary of :data:`MATERIALS`.
        strength_table: The strength table as read by ``pd.read_csv`` from
            :data:`STRENGTH_TABLE_PATH`, with columns ``record_id``, ``grade``,
            ``source_type``, ``check`` and :data:`STRENGTH_VALUE_COLUMNS`.

    Returns:
        On ``materials.index``, the columns ``strength_source`` (the
        ``record_id`` used; ``None`` for ``unknown``), ``c_kpa``, ``phi_deg``
        and ``unit_weight_kn_m3`` (NaN for ``unknown``).

    Raises:
        ValueError: If a material is not in the vocabulary, or a grade needed
            has no row carrying all three values.
    """
    present = set(materials.dropna().unique())
    unknown = present - set(MATERIALS)
    if unknown:
        msg = (
            f"{', '.join(repr(m) for m in sorted(unknown))} are not ground map "
            f"materials; known: {', '.join(repr(m) for m in MATERIALS)}"
        )
        raise ValueError(msg)

    grades = sorted({MATERIAL_STRENGTH_GRADE[m] for m in present if m != UNKNOWN})
    picks = {grade: _pick_strength_row(strength_table, grade) for grade in grades}

    grade_of = materials.map(MATERIAL_STRENGTH_GRADE)

    def column(name: str) -> pd.Series:
        return grade_of.map({g: float(row[name]) for g, row in picks.items()})

    # Built by hand so that ``unknown`` is a null, not a NaN, in a string column.
    source = pd.Series(
        [None if pd.isna(grade) else picks[grade]["record_id"] for grade in grade_of],
        index=materials.index,
        dtype=object,
    )
    return pd.DataFrame(
        {
            "strength_source": source,
            "c_kpa": column("c_eff_kpa").astype(float),
            "phi_deg": column("phi_eff_deg").astype(float),
            "unit_weight_kn_m3": column("unit_weight_kn_m3").astype(float),
        },
        index=materials.index,
    )


# ---------------------------------------------------------------------------
# The overlay
# ---------------------------------------------------------------------------


def _check_projected(frame: gpd.GeoDataFrame, what: str) -> None:
    if frame.crs is None or frame.crs.is_geographic:
        msg = (
            f"The {what} is in {frame.crs}, which is not a projected system; "
            "work in NZGD2000 / NZTM."
        )
        raise ValueError(msg)


def _check_sources(sources: Sequence[GroundSource]) -> None:
    for source in sources:
        if source.attribute not in ATTRIBUTES:
            msg = (
                f"Source {source.name!r} supplies {source.attribute!r}; "
                f"an attribute is one of {', '.join(ATTRIBUTES)}"
            )
            raise ValueError(msg)
        if source.confidence not in CONFIDENCES:
            msg = (
                f"Source {source.name!r} has confidence {source.confidence!r}; "
                f"it is one of {', '.join(CONFIDENCES)}"
            )
            raise ValueError(msg)
        if source.column not in source.frame.columns:
            msg = f"Source {source.name!r} has no column {source.column!r}"
            raise ValueError(msg)
        _check_projected(source.frame, f"source {source.name!r}")


def _planar_partition(
    extent: shapely.Polygon, frames: Sequence[gpd.GeoDataFrame], crs: str
) -> gpd.GeoDataFrame:
    """Cut the extent into the faces formed by every frame's polygon boundaries."""
    linework = [extent.boundary]
    for frame in frames:
        if frame.empty:
            continue
        geometries = frame.geometry.to_crs(crs)
        touching = geometries[geometries.intersects(extent)]
        if touching.empty:
            continue
        linework.append(shapely.intersection(touching.boundary.union_all(), extent))
    noded = shapely.union_all(linework)
    faces = shapely.get_parts(shapely.polygonize(np.array([noded])))
    pieces = gpd.GeoDataFrame(geometry=faces, crs=crs)
    inside = pieces.representative_point().within(extent)
    return pieces.loc[inside].reset_index(drop=True)


def _lookup(
    points: gpd.GeoSeries, frame: gpd.GeoDataFrame, column: str, crs: str
) -> pd.Series:
    """Read ``column`` of the polygon containing each point; first match wins."""
    if frame.empty or points.empty:
        return pd.Series(dtype=object)
    right = gpd.GeoDataFrame(
        {column: frame[column].to_numpy()},
        geometry=frame.geometry.to_numpy(),
        crs=frame.crs,
    ).to_crs(crs)
    left = gpd.GeoDataFrame(geometry=points, crs=crs)
    joined = gpd.sjoin(left, right, how="inner", predicate="within")
    joined = joined.loc[~joined.index.duplicated(keep="first")]
    return joined[column]


def _fill_by_precedence(
    points: gpd.GeoSeries,
    sources: Sequence[GroundSource],
    attribute: str,
    *,
    default: object,
    crs: str,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Attribute each point from the first source in order whose polygon holds it.

    Returns:
        ``(values, source, confidence, saw_water)``: the attribute, the name
        of the source that supplied it (:data:`ASSUMED` where none), its
        confidence (``low`` where none), and whether a source said water and
        no later source said ground.
    """
    values = pd.Series(default, index=points.index, dtype=object)
    source = pd.Series(ASSUMED, index=points.index, dtype=object)
    confidence = pd.Series("low", index=points.index, dtype=object)
    filled = pd.Series(data=False, index=points.index)
    saw_water = pd.Series(data=False, index=points.index)

    for item in (s for s in sources if s.attribute == attribute):
        found = _lookup(points[~filled], item.frame, item.column, crs).dropna()
        if found.empty:
            continue
        is_water = found == WATER
        saw_water.loc[found.index[is_water]] = True
        ground = found[~is_water]
        values.loc[ground.index] = ground
        source.loc[ground.index] = item.name
        confidence.loc[ground.index] = item.confidence
        filled.loc[ground.index] = True

    return values, source, confidence, saw_water & ~filled


def build_ground_map(
    extent: shapely.Polygon,
    sources: Sequence[GroundSource],
    *,
    flatland: gpd.GeoDataFrame,
    default_gw_depth_m: float,
    crs: str = constants.DEFAULT_CRS,
) -> gpd.GeoDataFrame:
    """Union every source into one planar partition and attribute each piece.

    The partition of ``extent`` is the faces formed by the boundaries of every
    source's polygons and of the flatland. Each face takes each attribute from
    the first source in ``sources`` supplying that attribute whose polygon
    contains the face's representative point, so the order of ``sources`` is
    the precedence (contract section 9.3). Where no source reaches, the
    material is ``unknown``, the modification ``natural``, the prior failure
    ``none``, the groundwater depth ``default_gw_depth_m`` with source
    :data:`ASSUMED`, and the fill thickness NaN. A fill thickness is kept only
    on pieces whose modification is ``fill``. Pieces whose only material source
    says water are dropped: open water is not ground.

    Args:
        extent: The polygon to map, in ``crs``.
        sources: The sources in precedence order, first wins per attribute.
        flatland: The NLM flatland polygons; a piece whose representative
            point lies in one is ``is_flatland``.
        default_gw_depth_m: The depth to groundwater assumed off the modelled
            footprint, in metres.
        crs: The projected system to work and return in.

    Returns:
        One row per piece with every column of the ground map except
        ``ground_id`` and ``area_m2``, which the step mints and measures:
        ``material``, ``material_source``, ``material_confidence``,
        ``modification``, ``modification_source``, ``modification_confidence``,
        ``is_flatland``, ``flatland_version``, ``gw_depth_m``,
        ``gw_depth_class``, ``gw_source``, ``prior_failure``,
        ``prior_failure_source``, ``fill_thickness_m``, ``geology_value``,
        ``c_kpa``, ``phi_deg``, ``unit_weight_kn_m3``, ``strength_source``,
        ``geometry``.

    Raises:
        ValueError: If a source supplies an attribute or confidence outside the
            vocabulary, lacks its column, or any frame is in a geographic
            system.
    """
    _check_sources(sources)
    _check_projected(flatland, "flatland")

    pieces = _planar_partition(extent, [*(s.frame for s in sources), flatland], crs)
    points = pieces.representative_point()

    material, material_source, material_confidence, water = _fill_by_precedence(
        points, sources, "material", default=UNKNOWN, crs=crs
    )
    modification, modification_source, modification_confidence, _ = _fill_by_precedence(
        points, sources, "modification", default=NATURAL, crs=crs
    )
    prior_failure, prior_failure_source, _, _ = _fill_by_precedence(
        points, sources, "prior_failure", default=NO_PRIOR_FAILURE, crs=crs
    )
    gw_depth, gw_source, _, _ = _fill_by_precedence(
        points, sources, "gw_depth_m", default=default_gw_depth_m, crs=crs
    )
    fill_thickness, _, _, _ = _fill_by_precedence(
        points, sources, "fill_thickness_m", default=np.nan, crs=crs
    )

    gw_depth = gw_depth.astype(float)
    fill_thickness = fill_thickness.astype(float).where(modification == "fill")

    on_flatland = _lookup(points, flatland.assign(_flat=True), "_flat", crs).reindex(
        points.index, fill_value=False
    )

    strength = strength_from_material(material, pd.read_csv(STRENGTH_TABLE_PATH))

    ground = gpd.GeoDataFrame(
        {
            "material": material,
            "material_source": material_source,
            "material_confidence": material_confidence,
            "modification": modification,
            "modification_source": modification_source,
            "modification_confidence": modification_confidence,
            "is_flatland": on_flatland.astype(bool),
            "flatland_version": constants.FLATLAND_NLM_VERSION,
            "gw_depth_m": gw_depth,
            "gw_depth_class": gw_depth_class_from_depth(gw_depth.to_numpy()),
            "gw_source": gw_source,
            "prior_failure": prior_failure,
            "prior_failure_source": prior_failure_source,
            "fill_thickness_m": fill_thickness,
            "geology_value": kingsbury_geology_value(material),
            "c_kpa": strength["c_kpa"],
            "phi_deg": strength["phi_deg"],
            "unit_weight_kn_m3": strength["unit_weight_kn_m3"],
            "strength_source": strength["strength_source"],
        },
        geometry=pieces.geometry,
        crs=crs,
    )
    return ground.loc[~water].reset_index(drop=True)
