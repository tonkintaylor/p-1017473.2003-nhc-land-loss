"""Tests for the reconciled ground map and landslide step 4.

The library is exercised on synthetic overlapping sources carrying every
vocabulary value, and the step's chain is run end to end through its
``main()`` with every reader replaced by a synthetic frame or raster written
under ``tmp_path``, so nothing reaches the network or a drive.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rioxarray  # noqa: F401  # registers the .rio accessor
import xarray as xr
from shapely.geometry import Point, box

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.landslide import ground_map as gm
from landloss.hazard.landslide.ground_map import GroundSource, build_ground_map
from scripts.landloss.hazard.landslide.steps.s4_ground_map import gen_ground_map as step

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

CRS = constants.DEFAULT_CRS

# An arbitrary but realistic corner in NZTM, so the synthetic extent sits where
# a Wellington extent would sit rather than at the origin.
X0 = 1_748_000.0
Y0 = 5_425_000.0
SIZE = 100.0
EXTENT = box(X0, Y0, X0 + SIZE, Y0 + SIZE)

# The columns build_ground_map returns: the contract's, less the id and the
# area the step adds.
LIBRARY_COLUMNS = [c for c in step.COLUMNS if c not in ("ground_id", "area_m2")]


def square(x0, y0, x1, y1):
    """A box in the extent's own frame, offset from its corner."""
    return box(X0 + x0, Y0 + y0, X0 + x1, Y0 + y1)


def frame(geometries, **columns):
    return gpd.GeoDataFrame(columns, geometry=list(geometries), crs=CRS)


def at(ground, x, y):
    """The one row whose polygon holds the point, in the extent's frame."""
    hits = ground.loc[ground.contains(Point(X0 + x, Y0 + y))]
    assert len(hits) == 1, f"{len(hits)} pieces hold ({x}, {y})"
    return hits.iloc[0]


def make_grid(values, resolution: float = 1.0, *, x0=X0, y0=Y0):
    """Wrap an array as a north-up raster in NZTM, as step 3 writes one."""
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    eastings = x0 + resolution * (np.arange(columns) + 0.5)
    northings = y0 + resolution * (np.arange(rows)[::-1] + 0.5)
    grid = xr.DataArray(values, dims=("y", "x"), coords={"y": northings, "x": eastings})
    return grid.rio.write_crs(CRS)


# ---------------------------------------------------------------------------
# Vocabulary and mappers
# ---------------------------------------------------------------------------


def test_the_genesis_tuples_partition_the_fifteen_types():
    groups = (
        set(gm.GENESIS_MODIFICATION_TYPES),
        set(gm.GENESIS_PRIOR_FAILURE_TYPES),
        set(gm.GENESIS_NO_CLAIM_TYPES),
    )
    assert sum(len(g) for g in groups) == 15
    assert set.union(*groups) == set(gm.GENESIS_TYPES)
    assert len(gm.GENESIS_TYPES) == 15
    assert groups[0].isdisjoint(groups[1])
    assert groups[0].isdisjoint(groups[2])
    assert groups[1].isdisjoint(groups[2])


def test_every_mapper_lands_in_the_vocabulary():
    ground = set(gm.MATERIALS) | {gm.WATER}
    assert len(gm.SLIDE_MATERIALS) == 14
    assert set(gm.SLIDE_MATERIALS.values()) <= ground
    assert set(gm.GEOLOGY_MATERIALS.values()) <= set(gm.MATERIALS)
    assert set(gm.NLM_MATERIALS.values()) <= ground
    assert set(gm.GENESIS_MODIFICATIONS) == set(gm.GENESIS_MODIFICATION_TYPES)
    assert set(gm.GENESIS_MODIFICATIONS.values()) <= set(gm.MODIFICATIONS)
    assert set(gm.MATERIAL_GEOLOGY_VALUES) == set(gm.MATERIALS)
    assert set(gm.MATERIAL_STRENGTH_GRADE) == set(gm.MATERIALS) - {gm.UNKNOWN}


def test_material_mappers_read_their_sources_classes():
    slide = gm.material_from_slide(
        pd.Series(["Rock at/near surface", "Mixed fill/rock", "Talus", "Water body"])
    )
    assert slide.tolist() == ["rock", "fill_uncontrolled", "colluvium", gm.WATER]

    geology = gm.material_from_geology(
        pd.Series(["Tt", "Q1nc", "Q1af", "uQal_t", "Q1b"])
    )
    assert geology.tolist() == [
        "rock",
        "fill_uncontrolled",
        "colluvium",
        "loess",
        "alluvium",
    ]

    nlm = gm.material_from_nlm(
        pd.Series(["Sedimentary", "Compacted fill", "Uncompacted fill", "Water body"])
    )
    assert nlm.tolist() == ["rock", "fill_engineered", "fill_uncontrolled", gm.WATER]


@pytest.mark.parametrize(
    ("mapper", "values"),
    [
        (gm.material_from_slide, ["Rock at/near surface", "Peat"]),
        (gm.material_from_geology, ["Tt", "Qzz"]),
        (gm.material_from_nlm, ["Sedimentary", "Glacial till"]),
        (gm.modification_from_genesis, ["Cut slope", "Modified terrain"]),
        (gm.modification_from_genesis, ["Landslide relict"]),
        (gm.modification_from_wcc, ["cut", "quarry"]),
    ],
)
def test_a_mapper_refuses_a_class_it_has_no_rule_for(mapper, values):
    with pytest.raises(ValueError, match="No rule maps"):
        mapper(pd.Series(values))


def test_modification_mappers():
    genesis = gm.modification_from_genesis(
        pd.Series(
            ["Cut slope", "Fill body", "Landfill", "Dam (material would be fill)"]
        )
    )
    assert genesis.tolist() == ["cut", "fill", "fill", "fill"]
    assert gm.modification_from_wcc(pd.Series(["fill", "cut"])).tolist() == [
        "fill",
        "cut",
    ]


def test_the_residual_classes_cut_fill_and_natural_about_the_threshold():
    classed = gm.modification_from_residual(
        np.array([-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, np.nan]), threshold_m=1.0
    )
    assert classed.tolist() == [
        "cut",
        "natural",
        "natural",
        "natural",
        "natural",
        "natural",
        "fill",
        gm.UNKNOWN,
    ]
    with pytest.raises(ValueError, match="positive"):
        gm.modification_from_residual(np.array([1.0]), threshold_m=0.0)


def test_prior_failure_reads_landslides_and_counts_both_rockfall_subtypes_relict():
    types = pd.Series(["Landslide relict", "Landslide recent", "Rockfall", "Rockfall"])
    subtypes = pd.Series(["source area", "debris trail", "few", "many"])
    assert gm.prior_failure_from_genesis(types, subtypes).tolist() == [
        "relict",
        "recent",
        "relict",
        "relict",
    ]
    with pytest.raises(ValueError, match="Rockfall subtype"):
        gm.prior_failure_from_genesis(pd.Series(["Rockfall"]), pd.Series(["scattered"]))
    with pytest.raises(ValueError, match="No rule maps"):
        gm.prior_failure_from_genesis(pd.Series(["Fan"]), pd.Series([None]))


def test_groundwater_depth_classes_at_the_breaks():
    classed = gm.gw_depth_class_from_depth(np.array([0.5, 1.0, 2.0, 3.0, 5.0, np.nan]))
    assert classed.tolist() == [
        "saturated",
        "saturated",
        "poorly_drained",
        "poorly_drained",
        "well_drained",
        None,
    ]


def test_kingsbury_geology_value_follows_the_material():
    values = gm.kingsbury_geology_value(
        pd.Series(["rock", "rock_uw_mw", "rock_crushed", "colluvium", gm.UNKNOWN])
    )
    assert values.tolist()[:4] == [4.0, 0.0, 8.0, 10.0]
    assert np.isnan(values.iloc[4])
    with pytest.raises(ValueError, match="not ground map materials"):
        gm.kingsbury_geology_value(pd.Series(["granite"]))


# ---------------------------------------------------------------------------
# Strength
# ---------------------------------------------------------------------------


def test_the_strength_picks_on_the_committed_table_are_the_contracts_six():
    table = pd.read_csv(gm.STRENGTH_TABLE_PATH)
    materials = pd.Series(list(gm.MATERIALS))
    strength = gm.strength_from_material(materials, table)

    expected = {
        "rock": "S17",
        "rock_hw_cw": "S17",
        "rock_uw_mw": "S10",
        "rock_crushed": "S20",
        "colluvium": "S08",
        "loess": "S30",
        "alluvium": "S30",
        "fill_engineered": "S48",
        "fill_uncontrolled": "S48",
        "reclamation": "S48",
        gm.UNKNOWN: None,
    }
    assert dict(zip(materials, strength["strength_source"], strict=True)) == expected
    assert list(strength.columns) == [
        "strength_source",
        "c_kpa",
        "phi_deg",
        "unit_weight_kn_m3",
    ]
    assert strength.index.equals(materials.index)

    loess = strength.loc[materials == "loess"].iloc[0]
    assert (loess["c_kpa"], loess["phi_deg"], loess["unit_weight_kn_m3"]) == (
        4.0,
        36.0,
        18.0,
    )
    unknown = strength.loc[materials == gm.UNKNOWN].iloc[0]
    assert unknown[["c_kpa", "phi_deg", "unit_weight_kn_m3"]].isna().all()


def strength_table(rows):
    return pd.DataFrame(
        rows,
        columns=[
            "record_id",
            "source_type",
            "grade",
            "check",
            "c_eff_kpa",
            "phi_eff_deg",
            "unit_weight_kn_m3",
        ],
    )


def test_the_strength_pick_order_is_check_then_published_then_file_order():
    table = strength_table(
        [
            ("A", "published", "HW", True, 1.0, 30.0, 20.0),
            ("B", "tt_project", "HW", False, 2.0, 31.0, 20.0),
            ("C", "published", "HW", False, 3.0, 32.0, 20.0),
            ("D", "published", "HW", False, 4.0, 33.0, 20.0),
            ("E", "published", "COL", False, 5.0, 34.0, np.nan),
            ("F", "tt_project", "COL", False, 6.0, 35.0, 18.0),
        ]
    )
    strength = gm.strength_from_material(pd.Series(["rock", "colluvium"]), table)
    # Check false before true, published before the rest, then file order: C.
    # The incomplete published COL row is passed over for the complete one.
    assert strength["strength_source"].tolist() == ["C", "F"]
    assert strength["c_kpa"].tolist() == [3.0, 6.0]


def test_a_grade_with_no_complete_row_raises_naming_it():
    table = strength_table([("A", "published", "HW", False, 1.0, 30.0, np.nan)])
    with pytest.raises(ValueError, match="grade 'HW'"):
        gm.strength_from_material(pd.Series(["rock"]), table)
    # A grade nothing asks for is not inspected.
    assert (
        gm.strength_from_material(pd.Series([gm.UNKNOWN]), table)["c_kpa"].isna().all()
    )


def test_a_check_column_left_as_text_still_sorts():
    table = strength_table(
        [
            ("A", "published", "RS", "True", 1.0, 30.0, 20.0),
            ("B", "published", "RS", "False", 2.0, 31.0, 20.0),
        ]
    )
    assert gm.strength_from_material(pd.Series(["loess"]), table)[
        "strength_source"
    ].tolist() == ["B"]


# ---------------------------------------------------------------------------
# The overlay
# ---------------------------------------------------------------------------


def material_source(name, geometries, materials, confidence):
    return GroundSource(
        name, frame(geometries, material=materials), "material", "material", confidence
    )


def overlapping_sources():
    """Sources that overlap so every precedence rule has a piece to decide.

    In the extent's own frame (0 to 100 each way):

    - material: SLIDE colluvium over (20-60, 20-60) and water over (60-70,
      20-40) and (80-100, 80-100); geology rock over the south half; NLM rock
      over the west 70 m.
    - modification: genesis cut over (0-30, 0-30); WCC fill over (0-50,
      0-50); residual fill over (40-100, 40-100).
    - prior failure: relict over (0-30, 50-100), recent over (30-60, 50-100).
    - groundwater: 0.5 m over the south 20 m, 2 m over the next 10 m.
    - fill thickness: 3 m over (40-100, 40-100).
    """
    return [
        material_source(
            "slide_materials",
            [square(20, 20, 60, 60), square(60, 20, 70, 40), square(80, 80, 100, 100)],
            ["colluvium", gm.WATER, gm.WATER],
            "high",
        ),
        material_source("geology_1_50k", [square(0, 0, 100, 50)], ["rock"], "medium"),
        material_source("nlm_geomorphology", [square(0, 0, 70, 100)], ["rock"], "low"),
        GroundSource(
            "slide_genesis",
            frame([square(0, 0, 30, 30)], modification=["cut"]),
            "modification",
            "modification",
            "high",
        ),
        GroundSource(
            "wcc_fill_areas",
            frame([square(0, 0, 50, 50)], modification=["fill"]),
            "modification",
            "modification",
            "medium",
        ),
        GroundSource(
            "residual_30m",
            frame([square(40, 40, 100, 100)], modification=["fill"]),
            "modification",
            "modification",
            "low",
        ),
        GroundSource(
            "slide_genesis",
            frame(
                [square(0, 50, 30, 100), square(30, 50, 60, 100)],
                prior_failure=["relict", "recent"],
            ),
            "prior_failure",
            "prior_failure",
            "low",
        ),
        GroundSource(
            gm.NLM_GWD_SOURCE,
            frame(
                [square(0, 0, 100, 20), square(0, 20, 100, 30)], gw_depth_m=[0.5, 2.0]
            ),
            "gw_depth_m",
            "gw_depth_m",
            "medium",
        ),
        GroundSource(
            "residual_100m",
            frame([square(40, 40, 100, 100)], fill_thickness_m=[3.0]),
            "fill_thickness_m",
            "fill_thickness_m",
            "low",
        ),
    ]


FLATLAND = frame([square(0, 0, 100, 20)])


@pytest.fixture
def ground():
    return build_ground_map(
        EXTENT,
        overlapping_sources(),
        flatland=FLATLAND,
        default_gw_depth_m=4.0,
        crs=CRS,
    )


def test_the_map_carries_the_contracts_columns_and_dtypes(ground):
    assert list(ground.columns) == LIBRARY_COLUMNS
    assert ground.crs == CRS
    assert ground["is_flatland"].dtype == bool
    assert ground["gw_depth_m"].dtype == float
    assert ground["fill_thickness_m"].dtype == float
    assert ground["geology_value"].dtype == float
    assert (ground["flatland_version"] == constants.FLATLAND_NLM_VERSION).all()
    assert set(ground["material"]) <= set(gm.MATERIALS)
    assert set(ground["modification"]) <= set(gm.MODIFICATIONS)
    assert set(ground["prior_failure"]) <= set(gm.PRIOR_FAILURES)
    assert set(ground["gw_depth_class"]) <= set(gm.GW_DEPTH_CLASSES)
    assert set(ground["material_confidence"]) <= set(gm.CONFIDENCES)
    assert set(ground["modification_confidence"]) <= set(gm.CONFIDENCES)


def test_the_map_is_a_planar_partition_less_the_water(ground):
    # The water-only corner (80-100, 80-100) is dropped; everything else tiles.
    assert ground.area.sum() == pytest.approx(SIZE**2 - 20.0**2)
    assert ground.geometry.is_valid.all()
    overlaps = ground.sjoin(ground[["geometry"]], predicate="overlaps")
    assert overlaps.empty


def test_the_finer_material_source_wins_inside_and_the_coarser_outside(ground):
    inside = at(ground, 45, 45)
    assert (
        inside["material"],
        inside["material_source"],
        inside["material_confidence"],
    ) == (
        "colluvium",
        "slide_materials",
        "high",
    )
    south = at(ground, 15, 15)
    assert (
        south["material"],
        south["material_source"],
        south["material_confidence"],
    ) == (
        "rock",
        "geology_1_50k",
        "medium",
    )
    north_west = at(ground, 15, 85)
    assert (north_west["material"], north_west["material_source"]) == (
        "rock",
        "nlm_geomorphology",
    )
    assert north_west["material_confidence"] == "low"


def test_water_yields_to_a_ground_source_beneath_it(ground):
    pond = at(ground, 65, 35)
    assert (pond["material"], pond["material_source"]) == ("rock", "geology_1_50k")
    assert not ground.contains(Point(X0 + 85, Y0 + 85)).any()


def test_defaults_where_no_source_reaches(ground):
    bare = at(ground, 85, 65)
    assert bare["material"] == gm.UNKNOWN
    assert bare["material_source"] == gm.ASSUMED
    assert bare["material_confidence"] == "low"
    assert bare["modification"] == "fill"  # the residual reaches here
    assert bare["prior_failure"] == gm.NO_PRIOR_FAILURE
    assert bare["prior_failure_source"] == gm.ASSUMED
    assert bare["gw_depth_m"] == 4.0
    assert bare["gw_source"] == gm.ASSUMED
    assert bare["gw_depth_class"] == "well_drained"
    assert np.isnan(bare["geology_value"])
    assert bare["strength_source"] is None
    assert np.isnan(bare["c_kpa"])

    untouched = at(ground, 85, 15)
    assert untouched["modification"] == gm.NATURAL
    assert untouched["modification_source"] == gm.ASSUMED
    assert untouched["modification_confidence"] == "low"


def test_modification_precedence_genesis_then_wcc_then_residual(ground):
    assert (
        at(ground, 15, 15)["modification"],
        at(ground, 15, 15)["modification_source"],
    ) == (
        "cut",
        "slide_genesis",
    )
    assert (
        at(ground, 45, 15)["modification"],
        at(ground, 45, 15)["modification_source"],
    ) == (
        "fill",
        "wcc_fill_areas",
    )
    assert (
        at(ground, 75, 75)["modification"],
        at(ground, 75, 75)["modification_source"],
    ) == (
        "fill",
        "residual_30m",
    )
    assert at(ground, 15, 15)["modification_confidence"] == "high"
    assert at(ground, 45, 15)["modification_confidence"] == "medium"
    assert at(ground, 75, 75)["modification_confidence"] == "low"


def test_prior_failure_groundwater_flatland_and_fill_thickness(ground):
    assert at(ground, 15, 85)["prior_failure"] == "relict"
    assert at(ground, 45, 85)["prior_failure"] == "recent"
    assert at(ground, 45, 85)["prior_failure_source"] == "slide_genesis"

    south = at(ground, 15, 15)
    assert (south["gw_depth_m"], south["gw_depth_class"], south["gw_source"]) == (
        0.5,
        "saturated",
        gm.NLM_GWD_SOURCE,
    )
    assert south["is_flatland"]
    strip = at(ground, 15, 25)
    assert (strip["gw_depth_m"], strip["gw_depth_class"]) == (2.0, "poorly_drained")
    assert not strip["is_flatland"]

    # Fill thickness is kept on fill pieces only.
    assert at(ground, 75, 75)["fill_thickness_m"] == 3.0
    assert at(ground, 45, 45)["fill_thickness_m"] == 3.0
    assert np.isnan(at(ground, 15, 15)["fill_thickness_m"])


def test_geology_value_and_strength_follow_the_material(ground):
    inside = at(ground, 45, 45)
    assert inside["geology_value"] == 10.0
    assert inside["strength_source"] == "S08"
    south = at(ground, 15, 15)
    assert south["geology_value"] == 4.0
    assert south["strength_source"] == "S17"
    assert (south["c_kpa"], south["phi_deg"], south["unit_weight_kn_m3"]) == (
        10.0,
        34.0,
        19.0,
    )


def test_reversing_the_source_order_reverses_the_precedence():
    sources = [
        material_source("fine", [square(20, 20, 60, 60)], ["colluvium"], "high"),
        material_source("coarse", [EXTENT], ["rock"], "low"),
    ]
    first = build_ground_map(EXTENT, sources, flatland=FLATLAND, default_gw_depth_m=4.0)
    second = build_ground_map(
        EXTENT, sources[::-1], flatland=FLATLAND, default_gw_depth_m=4.0
    )
    assert at(first, 45, 45)["material"] == "colluvium"
    assert at(second, 45, 45)["material"] == "rock"
    assert at(second, 45, 45)["material_source"] == "coarse"


def test_every_vocabulary_value_passes_through_the_overlay():
    materials = [m for m in gm.MATERIALS if m != gm.UNKNOWN]
    width = 80.0 / len(materials)
    strips = [square(i * width, 0, (i + 1) * width, 100) for i in range(len(materials))]
    sources = [
        material_source("strips", strips, materials, "medium"),
        GroundSource(
            "mods",
            frame(
                [square(0, 0, 100, 30), square(0, 30, 100, 60)],
                modification=["cut", "fill"],
            ),
            "modification",
            "modification",
            "high",
        ),
        GroundSource(
            "failures",
            frame(
                [square(0, 0, 100, 30), square(0, 30, 100, 60)],
                prior_failure=["relict", "recent"],
            ),
            "prior_failure",
            "prior_failure",
            "low",
        ),
        GroundSource(
            gm.NLM_GWD_SOURCE,
            frame(
                [square(0, 0, 100, 30), square(0, 30, 100, 60)], gw_depth_m=[0.5, 2.0]
            ),
            "gw_depth_m",
            "gw_depth_m",
            "medium",
        ),
    ]
    ground = build_ground_map(
        EXTENT, sources, flatland=FLATLAND, default_gw_depth_m=4.0
    )

    assert set(ground["material"]) == set(gm.MATERIALS)
    assert set(ground["modification"]) == {"cut", "fill", gm.NATURAL}
    assert set(ground["prior_failure"]) == set(gm.PRIOR_FAILURES)
    assert set(ground["gw_depth_class"]) == set(gm.GW_DEPTH_CLASSES)
    assert set(ground["gw_source"]) == {gm.NLM_GWD_SOURCE, gm.ASSUMED}

    by_material = ground.drop_duplicates("material").set_index("material")
    for material in materials:
        assert (
            by_material.loc[material, "geology_value"]
            == gm.MATERIAL_GEOLOGY_VALUES[material]
        )
        assert by_material.loc[material, "strength_source"] is not None
    assert np.isnan(by_material.loc[gm.UNKNOWN, "geology_value"])


def test_a_source_outside_the_vocabulary_or_a_geographic_frame_is_refused():
    good = frame([EXTENT], material=["rock"])
    with pytest.raises(ValueError, match="an attribute is one of"):
        build_ground_map(
            EXTENT,
            [GroundSource("x", good, "material", "colour", "high")],
            flatland=FLATLAND,
            default_gw_depth_m=4.0,
        )
    with pytest.raises(ValueError, match="confidence"):
        build_ground_map(
            EXTENT,
            [GroundSource("x", good, "material", "material", "certain")],
            flatland=FLATLAND,
            default_gw_depth_m=4.0,
        )
    with pytest.raises(ValueError, match="no column"):
        build_ground_map(
            EXTENT,
            [GroundSource("x", good, "lithology", "material", "high")],
            flatland=FLATLAND,
            default_gw_depth_m=4.0,
        )
    with pytest.raises(ValueError, match="not a projected system"):
        build_ground_map(
            EXTENT,
            [
                GroundSource(
                    "x", good.to_crs("EPSG:4326"), "material", "material", "high"
                )
            ],
            flatland=FLATLAND,
            default_gw_depth_m=4.0,
        )


def test_an_empty_source_list_gives_one_default_piece():
    ground = build_ground_map(
        EXTENT, [], flatland=FLATLAND.iloc[0:0], default_gw_depth_m=4.0
    )
    assert len(ground) == 1
    assert ground.area.sum() == pytest.approx(SIZE**2)
    assert ground.iloc[0]["material"] == gm.UNKNOWN
    assert not ground.iloc[0]["is_flatland"]


# ---------------------------------------------------------------------------
# The step
# ---------------------------------------------------------------------------


def test_the_path_names_the_extent():
    assert step.ground_map_path(pilot=True).name == "ground-map-pilot.geoparquet"
    assert step.ground_map_path(pilot=False).name == "ground-map.geoparquet"
    assert step.ground_map_path(pilot=True).parent == step.WORK_DIR


def test_slide_confidence_folds_the_qualified_highs():
    folded = step.slide_confidence(
        pd.Series(
            ["low", "medium", "high", "high (verified GE)", "high (post-2013 modified)"]
        )
    )
    assert folded.tolist() == ["low", "medium", "high", "high", "high"]
    with pytest.raises(ValueError, match="not high, medium or low"):
        step.slide_confidence(pd.Series(["certain"]))


def test_genesis_sources_filter_to_the_claiming_types():
    genesis = frame(
        [square(0, 0, 10, 10)] * 6,
        Type=[
            "Cut slope",
            "Dam (material would be fill)",
            "Landslide relict",
            "Rockfall",
            "Modified terrain",
            "Fan",
        ],
        Subtype=[None, None, "source area", "few", "residential", None],
    )
    complete, dams, failures = step.genesis_sources(genesis)
    assert complete.frame["modification"].tolist() == ["cut"]
    assert complete.confidence == "high"
    assert dams.frame["modification"].tolist() == ["fill"]
    assert dams.confidence == "low"
    assert failures.frame["prior_failure"].tolist() == ["relict", "relict"]
    assert failures.attribute == "prior_failure"


def test_slide_material_sources_split_by_confidence_highest_first():
    materials = frame(
        [square(0, 0, 10, 10)] * 3,
        Type=["Rock at/near surface", "Fill", "Loess"],
        confidence=["low", "high (verified GE)", "medium"],
    )
    sources = step.slide_material_sources(materials)
    assert [s.confidence for s in sources] == ["high", "medium", "low"]
    assert [s.frame["material"].tolist() for s in sources] == [
        ["fill_uncontrolled"],
        ["loess"],
        ["rock"],
    ]


@ignore_affine_matmul
def test_the_residual_is_polygonised_into_cut_and_fill():
    values = np.zeros((10, 10))
    values[:, :3] = -2.0
    values[:, 7:] = 2.0
    polygons = step.polygonise_residual(make_grid(values), threshold_m=1.0)
    assert sorted(polygons["modification"]) == ["cut", "fill"]
    assert polygons.area.tolist() == pytest.approx([30.0, 30.0])
    assert list(polygons.columns) == ["geometry", "modification"]


@ignore_affine_matmul
def test_the_groundwater_grid_is_polygonised_over_the_flat_land(tmp_path):
    depth = make_grid([[np.nan, 2.0], [0.5, 0.5]], resolution=50.0)
    path = write_raster(
        depth.astype("float32").rename("gw_depth_m"), tmp_path / "gwd.tif"
    )
    flatland = frame([square(0, 0, 100, 25)])
    polygons = step.polygonise_groundwater(path, EXTENT, flatland)
    # The two 0.5 m cells are one run, clipped to the flat land's 25 m strip.
    assert polygons["gw_depth_m"].tolist() == [0.5]
    assert polygons.area.sum() == pytest.approx(100.0 * 25.0)
    assert step.polygonise_groundwater(path, EXTENT, flatland.iloc[0:0]).empty


@ignore_affine_matmul
def test_fill_thickness_is_the_mean_positive_residual_over_fill_pieces():
    values = np.full((100, 100), -1.0)
    values[:50, :] = 2.0  # the north half stands 2 m above the 100 m surface
    values[:10, :] = 4.0  # and its top 10 m, 4 m
    residual = make_grid(values)
    ground = frame(
        [square(0, 50, 100, 100), square(0, 0, 100, 50), square(0, 90, 100, 100)],
        modification=["fill", "fill", "cut"],
    )
    thickness = step.mean_positive_residual(ground, residual)
    assert thickness.iloc[0] == pytest.approx((40 * 2.0 + 10 * 4.0) / 50)
    assert np.isnan(thickness.iloc[1])  # fill with no positive cell
    assert np.isnan(thickness.iloc[2])  # not fill


@pytest.fixture
def synthetic_inputs(tmp_path, monkeypatch):
    """Every reader the step calls, replaced by a synthetic layer under tmp_path."""
    bbox = tuple(float(v) for v in EXTENT.bounds)
    monkeypatch.setattr(step, "WORK_DIR", tmp_path)
    monkeypatch.setattr(step, "resolve_extent", lambda *, pilot: (bbox, "synthetic"))

    materials = frame(
        [square(20, 20, 60, 60), square(80, 80, 100, 100)],
        Type=["Colluvium (anything that has moved downslope)", "Water body"],
        confidence=["high", "low"],
    )
    geology = frame([square(0, 0, 100, 50)], unit_code=["Tt"])
    landforms = frame([square(0, 0, 70, 100)], l3_yp=["Sedimentary"])
    genesis = frame(
        [square(0, 0, 30, 30), square(0, 50, 30, 100), square(0, 0, 5, 5)],
        Type=["Cut slope", "Landslide relict", "Modified terrain"],
        Subtype=[None, "source area", "residential"],
    )
    cut = frame([], CW_file_number=[])
    fill = frame([square(0, 0, 50, 50)], CW_file_number=["x"])
    flatland = frame([square(0, 0, 100, 20)]).to_crs("EPSG:4326")

    def reader(result):
        return lambda *args, **kwargs: result

    monkeypatch.setattr(step, "get_slide_interpreted_materials", reader(materials))
    monkeypatch.setattr(step, "get_wellington_urban_geology", reader(geology))
    monkeypatch.setattr(step, "get_nlm_geomorphology", reader(landforms))
    monkeypatch.setattr(step, "get_slide_genesis", reader(genesis))
    monkeypatch.setattr(step, "get_wcc_cut_areas", reader(cut))
    monkeypatch.setattr(step, "get_wcc_fill_areas", reader(fill))
    monkeypatch.setattr(step, "get_nlm_flatland", reader(flatland))

    depth = make_grid([[np.nan, np.nan], [0.5, 2.0]], resolution=50.0)
    gwd = write_raster(
        depth.astype("float32").rename("gw_depth_m"), tmp_path / "gwd.tif"
    )
    monkeypatch.setattr(step, "get_gwd_median_depth", lambda: gwd)

    residual_30 = np.zeros((100, 100))
    residual_30[:60, 40:] = 2.0  # fill over (40-100, 40-100)
    residual_100 = np.where(residual_30 > 0, 3.0, -1.0)
    paths = {
        30: write_raster(make_grid(residual_30), tmp_path / "residual-30m.tif"),
        100: write_raster(make_grid(residual_100), tmp_path / "residual-100m.tif"),
    }
    monkeypatch.setattr(step, "residual_path", lambda base, *, pilot: paths[base])
    return bbox


@ignore_affine_matmul
def test_the_step_writes_the_contracts_file_from_synthetic_sources(synthetic_inputs):
    step.main(
        pilot=True,
        use_cached_layers=True,
        default_gw_depth_m=4.0,
        residual_modification_threshold_m=1.0,
    )

    ground = gpd.read_parquet(step.ground_map_path(pilot=True))
    assert list(ground.columns) == list(step.COLUMNS)
    assert ground.crs == CRS
    assert ground.geometry.geom_type.eq("Polygon").all()

    # Ids are minted by location, numbered from one, and the frame is sorted.
    assert ground["ground_id"].str.fullmatch(r"GM\d{7}").all()
    assert ground["ground_id"].iloc[0] == "GM0000001"
    assert ground["ground_id"].is_monotonic_increasing
    points = ground.representative_point()
    order = sorted(zip(points.x, points.y, strict=True))
    assert order == list(zip(points.x, points.y, strict=True))

    # The water corner is dropped and the rest tiles the extent.
    assert ground["area_m2"].sum() == pytest.approx(SIZE**2 - 20.0**2)
    assert (ground["area_m2"] == ground.area).all()

    assert ground["is_flatland"].dtype == bool
    assert ground["gw_depth_m"].dtype == float
    assert pd.api.types.is_string_dtype(ground["strength_source"])
    assert pd.isna(at(ground, 85, 65)["strength_source"])

    inside = at(ground, 45, 45)
    assert (inside["material"], inside["material_source"]) == (
        "colluvium",
        "slide_materials",
    )
    assert at(ground, 15, 15)["material"] == "rock"
    assert at(ground, 15, 15)["modification"] == "cut"
    assert at(ground, 45, 15)["modification_source"] == "wcc_fill_areas"
    assert at(ground, 75, 75)["modification_source"] == "residual_30m"
    assert at(ground, 75, 75)["fill_thickness_m"] == pytest.approx(3.0)
    assert np.isnan(at(ground, 15, 15)["fill_thickness_m"])
    assert at(ground, 15, 85)["prior_failure"] == "relict"
    assert at(ground, 85, 65)["material"] == gm.UNKNOWN
    south_west = at(ground, 15, 15)
    assert south_west["is_flatland"]
    assert (south_west["gw_depth_m"], south_west["gw_source"]) == (
        0.5,
        gm.NLM_GWD_SOURCE,
    )
    assert at(ground, 15, 85)["gw_source"] == gm.ASSUMED
