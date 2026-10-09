"""Tests for the waterway classification."""

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from landloss.domain import constants
from landloss.hazard.liquefaction import waterways as waterways_module
from landloss.hazard.liquefaction.waterways import (
    FREE_FACE_POLYGON_KINDS,
    FREE_FACE_TYPES,
    WATERWAY_TYPES,
    assemble_free_faces,
    classify_waterways,
    get_free_faces,
    get_waterways,
)


def make_waterways(names: list[str | None], geometries: list | None = None):
    """Build a watercourse frame with one feature per name."""
    if geometries is None:
        geometries = [LineString([(0, i), (10, i)]) for i, _ in enumerate(names)]
    return gpd.GeoDataFrame(
        {"name": names}, geometry=geometries, crs=constants.DEFAULT_CRS
    )


# --- classification -----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Hutt River", "river"),
        ("Korokoro Stream", "other"),
        ("Kaiwharawhara Stream", "other"),
        ("Pauatahanui Creek", "other"),
    ],
)
def test_a_name_decides_the_waterway_type(name: str, expected: str) -> None:
    """A watercourse is a river when its name says so, and otherwise is not."""
    result = classify_waterways(make_waterways([name]))

    assert result["wtype"].iloc[0] == expected


def test_the_river_match_ignores_case() -> None:
    """A lowercase name is still recognised as a river."""
    result = classify_waterways(make_waterways(["hutt river"]))

    assert result["wtype"].iloc[0] == "river"


def test_an_unnamed_feature_is_not_a_river() -> None:
    """A null name falls through to other rather than becoming NaN."""
    result = classify_waterways(make_waterways([None]))

    assert result["wtype"].iloc[0] == "other"


def test_every_type_is_one_of_the_declared_values() -> None:
    """The wtype column never holds a value outside WATERWAY_TYPES."""
    result = classify_waterways(make_waterways(["Hutt River", "Owhiro Stream", None]))

    assert set(result["wtype"]) <= set(WATERWAY_TYPES)


# --- geometry -----------------------------------------------------------------


def test_empty_geometry_is_dropped() -> None:
    """A feature with empty geometry cannot be plotted, so it is removed."""
    waterways = make_waterways(
        ["Hutt River", "Empty Stream"],
        geometries=[LineString([(0, 0), (10, 0)]), LineString()],
    )

    result = classify_waterways(waterways)

    assert list(result["name"]) == ["Hutt River"]


def test_missing_geometry_is_dropped() -> None:
    """A feature with no geometry at all is removed."""
    waterways = make_waterways(
        ["Hutt River", "Missing Stream"],
        geometries=[LineString([(0, 0), (10, 0)]), None],
    )

    result = classify_waterways(waterways)

    assert list(result["name"]) == ["Hutt River"]


def test_the_index_is_reset_after_dropping() -> None:
    """Dropping a feature leaves a contiguous index behind."""
    waterways = make_waterways(
        ["Empty Stream", "Hutt River"],
        geometries=[LineString(), LineString([(0, 0), (10, 0)])],
    )

    result = classify_waterways(waterways)

    assert list(result.index) == [0]


def test_the_input_is_not_modified() -> None:
    """Classifying returns a copy, leaving the caller's frame untouched."""
    waterways = make_waterways(["Hutt River"])

    classify_waterways(waterways)

    assert "wtype" not in waterways


# --- clipping -----------------------------------------------------------------


@pytest.fixture
def fake_source(monkeypatch: pytest.MonkeyPatch):
    """Serve a fixed two-feature layer in place of the LINZ read."""
    source = make_waterways(
        ["Inside River", "Outside River"],
        geometries=[
            LineString([(0, 0), (10, 0)]),
            LineString([(100, 100), (110, 100)]),
        ],
    )
    monkeypatch.setattr(
        waterways_module, "get_nz_river_name_lines", lambda **_: source.copy()
    )
    return source


def test_without_a_clip_everything_read_is_kept(fake_source) -> None:
    """Omitting clip_to leaves the bounding box read untouched."""
    result = get_waterways()

    assert len(result) == 2


def test_clip_to_removes_what_falls_outside_the_boundary(fake_source) -> None:
    """A bounding box is a rectangle; clip_to cuts back to the real boundary."""
    boundary = gpd.GeoDataFrame(
        geometry=[Polygon([(-5, -5), (50, -5), (50, 50), (-5, 50)])],
        crs=constants.DEFAULT_CRS,
    )

    result = get_waterways(clip_to=boundary)

    assert list(result["name"]) == ["Inside River"]


# --- free faces ---------------------------------------------------------------


def square(x: float, side: float) -> Polygon:
    """A square of the given side with its lower left corner at (x, 0)."""
    return Polygon([(x, 0), (x + side, 0), (x + side, side), (x, side)])


def make_names(names: list[str | None], ids: list[int]) -> gpd.GeoDataFrame:
    """River name lines carrying a name and a river_section_id."""
    frame = make_waterways(names)
    frame["river_section_id"] = ids
    return frame


def make_polygons(sides: list[float]) -> gpd.GeoDataFrame:
    """Water body polygons, squares of the given sides set apart along x."""
    return gpd.GeoDataFrame(
        geometry=[square(1000 * i, side) for i, side in enumerate(sides)],
        crs=constants.DEFAULT_CRS,
    )


def make_coast() -> gpd.GeoDataFrame:
    """A coastline of one line."""
    return gpd.GeoDataFrame(
        geometry=[LineString([(0, -50), (5000, -50)])], crs=constants.DEFAULT_CRS
    )


def test_a_river_line_is_kept_by_its_name() -> None:
    """A name line is a free face when its name says river, as the NLM has it."""
    names = make_names(["Hutt River", "Korokoro Stream"], [1, 2])

    result = assemble_free_faces(names, {}, make_coast())

    rivers = result.loc[result["source"] == "name line"]
    assert list(rivers["name"]) == ["Hutt River"]
    assert set(rivers["wtype"]) == {"river"}


def test_a_listed_id_is_kept_whatever_its_name() -> None:
    """The extra IDs bring in watercourses whose name does not say river."""
    names = make_names(["Korokoro Stream", "Owhiro Stream"], [7, 8])

    result = assemble_free_faces(names, {}, make_coast(), extra_ids=(8,))

    rivers = result.loc[result["source"] == "name line"]
    assert list(rivers["name"]) == ["Owhiro Stream"]


def test_a_water_body_under_the_minimum_area_is_dropped() -> None:
    """A pond-sized lake carries no free face, so it is not one."""
    lakes = make_polygons([100.0, 300.0])  # 1 ha and 9 ha

    result = assemble_free_faces(
        make_names([], []), {"lake": lakes}, make_coast(), min_area_m2=50_000.0
    )

    kept = result.loc[result["wtype"] == "lake"]
    assert len(kept) == 1
    assert kept.geometry.area.iloc[0] == pytest.approx(90_000.0)


def test_water_bodies_stay_areas() -> None:
    """A lake is kept as a polygon, so a buffer covers the water as well."""
    result = assemble_free_faces(
        make_names([], []), {"lake": make_polygons([300.0])}, make_coast()
    )

    assert result.loc[result["wtype"] == "lake"].geom_type.tolist() == ["Polygon"]


def test_each_polygon_layer_takes_its_own_type() -> None:
    """River polygons are rivers, and the other layers keep their kind."""
    polygons = {kind: make_polygons([300.0]) for kind in FREE_FACE_POLYGON_KINDS}

    result = assemble_free_faces(make_names([], []), polygons, make_coast())

    by_source = result.groupby("source")["wtype"].apply(set).to_dict()
    assert by_source["polygon"] == set(FREE_FACE_POLYGON_KINDS)
    assert by_source["coastline"] == {"coast"}


def test_every_free_face_type_is_a_declared_value() -> None:
    """The wtype column never holds a value outside FREE_FACE_TYPES."""
    polygons = {kind: make_polygons([300.0]) for kind in FREE_FACE_POLYGON_KINDS}
    names = make_names(["Hutt River"], [1])

    result = assemble_free_faces(names, polygons, make_coast())

    assert set(result["wtype"]) == set(FREE_FACE_TYPES)


def test_an_unknown_polygon_layer_is_refused() -> None:
    """A typo in a layer key fails loudly rather than inventing a type."""
    with pytest.raises(ValueError, match="polygon layers"):
        assemble_free_faces(
            make_names([], []), {"pond": make_polygons([300.0])}, make_coast()
        )


def test_layers_in_different_crs_are_refused() -> None:
    """The area filter is in metres, so every layer must share the CRS."""
    with pytest.raises(ValueError, match="more than one CRS"):
        assemble_free_faces(make_names([], []), {}, make_coast().to_crs(4326))


def test_get_free_faces_reads_every_layer_and_clips(monkeypatch) -> None:
    """Every kind is read, and clip_to cuts the result back to the boundary."""
    names = make_names(["Hutt River", "Outside River"], [1, 2])
    names.loc[1, "geometry"] = LineString([(9000, 0), (9100, 0)])
    monkeypatch.setattr(
        waterways_module, "get_nz_river_name_lines", lambda **_: names.copy()
    )
    read: list[str] = []

    def fake_water(kind: str, **_) -> gpd.GeoDataFrame:
        read.append(kind)
        return make_coast() if kind == "coast" else make_polygons([300.0])

    boundary = Polygon([(-100, -100), (2000, -100), (2000, 2000), (-100, 2000)])

    result = get_free_faces(bbox=(0, 0, 1, 1), clip_to=boundary, read_water=fake_water)

    assert sorted(read) == sorted([*FREE_FACE_POLYGON_KINDS, "coast"])
    assert "Outside River" not in set(result["name"].dropna())
    assert "Hutt River" in set(result["name"].dropna())


def test_the_waiwhetu_stream_is_left_out_by_default() -> None:
    """No Wellington stream is added by ID while Q-19 is open."""
    names = make_names(["Waiwhetū Stream", "Korokoro Stream"], [6818507, 1])

    result = assemble_free_faces(names, {}, make_coast())

    rivers = result.loc[result["source"] == "name line"]
    assert rivers.empty
