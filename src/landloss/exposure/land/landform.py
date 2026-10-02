"""Whether the land under an address is flat or sloping, and why that matters.

Land loss behaves differently on the two. A flat site loses land to liquefaction,
lateral spreading and inundation; a sloping site loses it to slope failure, and
carries a different land value per square metre in the first place. Splitting the
exposure population on this one attribute is the cheapest cut that separates
those two stories, so it is the first attribute attached to an address.

The split is taken from the National Liquefaction Model's flatland layer rather
than rebuilt from a DEM. That is a deliberate reuse: the NLM is the model the
rest of the industry is working to, and rebuilding the same surface from scratch
would produce a second, differently-wrong answer to argue about.

Limitation L-16 in the project register records what that reuse costs. The NLM
flatland representation is simplified -- it is a national-scale flat-versus-
sloping generalisation, not a site-specific slope assessment -- and the team
accepted it as a sensible base model rather than an accurate one. Anything
downstream that is reported per landform class inherits that.

:func:`classify_landform` assigns only :data:`HILL` and :data:`FLAT`, because the
flatland layer is all it reads. :data:`ELEVATED_FLAT` -- flat land raised above
the surrounding valley floor, which is flat for shaking but is out of reach of
the inundation that the rest of the flat land is exposed to -- cannot be told
apart from ordinary flat land without a DEM, and is assigned by the separate
step :func:`assign_elevated_flat`.

The two are kept apart on purpose. The flatland join is a spatial question with
no raster in it and stays testable without one, and the promotion is arithmetic
on a column that some other step has already sampled off the terrain. Running
either without the other is a sensible thing to want: a first pass over a new
extent can skip the DEM entirely.
"""

from dataclasses import dataclass

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from landloss.domain import constants
from landloss.io.area_of_interest import CHRISTCHURCH, AreaOfInterest
from landloss.io.readers import get_koordinates_layer_extent

# The landform classes the exposure model recognises. ``classify_landform``
# assigns the first two; ``assign_elevated_flat`` promotes some of the second
# into the third. See the module docstring for why that is two steps.
LANDFORM_CLASSES = ("hill", "flat", "elevated_flat")

HILL = "hill"
FLAT = "flat"
ELEVATED_FLAT = "elevated_flat"

# The column ``classify_landform`` writes its answer into.
LANDFORM_COLUMN = "landform_class"

# The terrain derivative ``assign_elevated_flat`` reads, in metres above the
# mean elevation of the neighbourhood around the address. Written by
# :func:`landloss.common.utils.terrain.topographic_position` and sampled onto
# the addresses; the window it was measured over is part of what the number
# means, and is carried in the land value factors asset beside the threshold.
TOPOGRAPHIC_POSITION_COLUMN = "topographic_position_m"

# What an address frame has to carry before it can be promoted.
ELEVATED_FLAT_COLUMNS = (LANDFORM_COLUMN, TOPOGRAPHIC_POSITION_COLUMN)


def classify_landform(
    addresses: gpd.GeoDataFrame, flatland: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Tag each address as sitting on flat land or on a hill.

    An address falling inside a flatland polygon is :data:`FLAT`; anything else
    is :data:`HILL`. There is no third answer here -- :data:`ELEVATED_FLAT` is
    never assigned by this function, because telling raised flat land apart from
    ordinary flat land needs the DEM. :func:`assign_elevated_flat` is the step
    that does it, and it runs after this one.

    The join is deliberately ``within`` rather than ``intersects``: an address is
    a point, so the two agree except on a point lying exactly on a polygon edge,
    and a point on the boundary of the flat land is better treated as the hill it
    is about to climb than as flat.

    Kept separate from :func:`get_flatland` so that the classification can be
    exercised without reaching for the network.

    Args:
        addresses: Address points, in the same CRS as ``flatland``.
        flatland: The flat land polygons to test the addresses against. Only the
            geometry is used; any attributes on the layer are ignored.

    Returns:
        A new GeoDataFrame with a single :data:`LANDFORM_COLUMN` column added,
        holding one of :data:`LANDFORM_CLASSES` on every row, and re-indexed from
        zero. The caller's frame is left untouched.
    """
    # Re-indexed up front so that the spatial join's left index is unique, which
    # is what lets a match be collapsed back to a row without ambiguity.
    classified = addresses.copy().reset_index(drop=True)

    # Carry only the geometry across, so a column on the flatland layer cannot
    # collide with a column on the addresses and be silently renamed by the join.
    polygons = gpd.GeoDataFrame(geometry=flatland.geometry)

    # The join emits one row per address/polygon pair, so an address covered by
    # two overlapping flatland polygons appears twice. Reducing to the set of
    # matched left-hand labels is what keeps the result one row per address; the
    # question being asked is only "did it match anything", not "what did it
    # match".
    matches = classified.sjoin(polygons, how="inner", predicate="within")
    is_flat = classified.index.isin(matches.index)

    classified[LANDFORM_COLUMN] = HILL
    classified.loc[is_flat, LANDFORM_COLUMN] = FLAT

    return classified


def assign_elevated_flat(
    addresses: gpd.GeoDataFrame, *, min_topographic_position_m: float
) -> gpd.GeoDataFrame:
    """Promote flat addresses that stand above the land around them.

    An address is :data:`ELEVATED_FLAT` when it is already :data:`FLAT` and its
    topographic position -- metres above the mean elevation of the
    neighbourhood around it -- is above ``min_topographic_position_m``. That is
    the terrace, the raised river bank and the old beach ridge: ground that
    behaves as flat land in an earthquake but sits above the valley floor that
    floods.

    A :data:`HILL` address is never promoted, however high it stands. A spur
    stands well above its valley and would clear any threshold set here, but it
    is not flat and nothing about being high up makes it so. The promotion only
    ever moves an address between the two flat classes.

    An address with no topographic position -- outside the DEM, or on a nodata
    cell -- stays as it is. NaN fails the comparison, so the effect is to leave
    the address in the class the flatland join gave it rather than to guess.

    The threshold belongs to the caller rather than to this function, because it
    is the one number here that is tuned. It is carried in the land value
    factors asset as ``elevated_flat_min_topographic_position_m``, next to the
    window width the topographic position has to have been measured over for it
    to mean anything.

    Args:
        addresses: Address points carrying :data:`ELEVATED_FLAT_COLUMNS`: the
            landform class from :func:`classify_landform`, and a topographic
            position in metres sampled from the DEM.
        min_topographic_position_m: How far above its neighbourhood an address
            has to stand, in metres, before it counts as elevated. Compared
            strictly, so an address exactly on the threshold is not promoted.

    Returns:
        A new GeoDataFrame with :data:`LANDFORM_COLUMN` updated in place of the
        old one. The index is left as it was, and the caller's frame is
        untouched.

    Raises:
        ValueError: If either required column is absent, naming the ones that
            are. Without the topographic position every address would silently
            stay flat, and a whole class quietly going missing is the kind of
            thing that is noticed three steps downstream.
    """
    missing = [
        column for column in ELEVATED_FLAT_COLUMNS if column not in addresses.columns
    ]
    if missing:
        msg = (
            f"The address frame is missing the column(s) {', '.join(missing)}, "
            "so elevated flat land cannot be separated from ordinary flat land. "
            f"Expected all of: {', '.join(ELEVATED_FLAT_COLUMNS)}."
        )
        raise ValueError(msg)

    assigned = addresses.copy()

    # astype rather than to_numeric, so that a column of text fails loudly here
    # instead of being coerced to NaN and leaving every address unpromoted.
    position = assigned[TOPOGRAPHIC_POSITION_COLUMN].astype(float)
    promoted = (assigned[LANDFORM_COLUMN] == FLAT) & (
        position > min_topographic_position_m
    )

    assigned[LANDFORM_COLUMN] = assigned[LANDFORM_COLUMN].mask(promoted, ELEVATED_FLAT)

    return assigned


def get_flatland(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    clip_to: gpd.GeoDataFrame | gpd.GeoSeries | BaseGeometry | None = None,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the National Liquefaction Model flatland polygons for an extent.

    The layer is the NLM's flat-versus-sloping split, mirrored on the T+T
    Koordinates instance as layer
    :data:`landloss.domain.constants.NLM_FLATLAND_LAYER_ID`.

    The first call downloads a national layer and is slow -- minutes, not
    seconds. It is cached by ttpy afterwards, so the cost is paid once per
    machine, but a pilot extent is still the right way to exercise a script the
    first time.

    The representation is simplified. The NLM draws flat land at national scale,
    so a small terrace or a steep pocket inside a flat suburb is generalised
    away. The team accepted this as a sensible base model rather than an accurate
    one, and it is carried as limitation L-16 in the project register; results
    reported per landform class should be read with that in mind.

    Args:
        bbox: The extent to read (minx, miny, maxx, maxy) in ``crs``. Omitting it
            reads the whole national layer, which is rarely wanted.
        crs: The coordinate reference system to return the polygons in.
        clip_to: Optionally, a boundary to cut the polygons back to, in ``crs``.
            Anything ``geopandas.clip`` accepts. A bounding box is a rectangle
            and the study area is not, so pass this as well to cut the read back
            to the real boundary.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of flat land polygons.
    """
    flatland = get_koordinates_layer_extent(
        layer=constants.NLM_FLATLAND_LAYER_ID,
        crs=crs,
        bbox=bbox,
        domain=constants.TTGROUP_DOMAIN,
        use_cache=use_cache,
    )

    if clip_to is not None:
        flatland = flatland.clip(clip_to)

    return flatland


@dataclass(frozen=True)
class LandformArea:
    """A rectangular extent cut down to the flat, or the sloping, land inside it.

    An :class:`landloss.io.area_of_interest.AreaOfInterest` is a rectangle and
    flat land is not, so an extent that means "the flat part of this city" cannot
    be written as four numbers. This pairs a rectangle with one of the classes
    :func:`classify_landform` assigns, which lets such an extent be named once and
    passed around like any other.

    Unlike a plain rectangle, resolving one reads the National Liquefaction Model
    flatland layer, so the first call needs network access and a Koordinates key.
    Limitation L-16 -- the layer is a national-scale generalisation, not a
    site-specific slope assessment -- applies to everything masked with one of
    these, exactly as it does to :func:`get_flatland`.

    Attributes:
        name: A human readable name, used in outputs and file names.
        area: The rectangle the landform is taken from within.
        landform: :data:`FLAT` or :data:`HILL`. :data:`ELEVATED_FLAT` is refused:
            it is promoted from a DEM by :func:`assign_elevated_flat` rather than
            read off the flatland layer, so there is no area to resolve it to.
    """

    name: str
    area: AreaOfInterest
    landform: str

    def __post_init__(self) -> None:
        """Reject a landform class that no layer can answer for.

        Raises:
            ValueError: If ``landform`` is not :data:`FLAT` or :data:`HILL`.
        """
        if self.landform not in (FLAT, HILL):
            msg = (
                f"{self.landform!r} cannot be resolved to an area. A LandformArea "
                f"is {FLAT!r} or {HILL!r}; {ELEVATED_FLAT!r} is promoted from a "
                "DEM by assign_elevated_flat and has no layer of its own to read."
            )
            raise ValueError(msg)

    def geometry(
        self,
        crs: int | str = constants.DEFAULT_CRS,
        *,
        use_cache: bool = True,
    ) -> BaseGeometry:
        """Return the flat, or the sloping, land inside the rectangle.

        Args:
            crs: The coordinate reference system to return the geometry in.
            use_cache: Whether to read and write the clipped extent cache.

        Returns:
            A single geometry covering the part of :attr:`area` that is of this
            landform class. Empty if the rectangle holds none of it.
        """
        rectangle = self.area.polygon(crs)
        flatland = get_flatland(
            bbox=self.area.bbox(crs),
            crs=crs,
            clip_to=rectangle,
            use_cache=use_cache,
        )

        # Intersected with the rectangle here rather than left to ``clip_to``.
        # The bounding box of a reprojected rectangle is larger than the
        # rectangle itself -- a WGS84 box is not axis-aligned in NZTM -- so
        # reading by bbox alone reaches past the extent's own edges.
        flat = flatland.geometry.union_all().intersection(rectangle)
        if self.landform == FLAT:
            return flat

        # Sloping land is whatever the flatland layer does not cover, which is
        # how :func:`classify_landform` reads it too: HILL is the absence of a
        # match, not a class the layer carries.
        return rectangle.difference(flat)

    def to_geoseries(
        self,
        crs: int | str = constants.DEFAULT_CRS,
        *,
        use_cache: bool = True,
    ) -> gpd.GeoSeries:
        """Return the extent as a single-element GeoSeries, matching AreaOfInterest."""
        return gpd.GeoSeries([self.geometry(crs, use_cache=use_cache)], crs=crs)

    def clip(
        self, frame: gpd.GeoDataFrame, *, use_cache: bool = True
    ) -> gpd.GeoDataFrame:
        """Cut a frame back to this extent, dropping whatever falls outside it.

        The mask is resolved in the frame's own CRS, so the caller does not have
        to reproject to use it.

        Args:
            frame: The layer to mask. Any geometry type; points keep whichever
                rows fall inside, and polygons are cut at the boundary.
            use_cache: Whether to read and write the clipped extent cache.

        Returns:
            The rows of ``frame`` inside this extent, with their columns intact.
        """
        return frame.clip(self.to_geoseries(frame.crs, use_cache=use_cache))


# The Canterbury earthquake sequence is dominated by flat land liquefaction --
# limitation L-09 in the project register -- so the two halves of the
# Christchurch extent are named apart rather than used together. Evidence drawn
# from CHCH_FLAT_ONLY speaks to the liquefaction land damage relationships;
# CHCH_SLOPE_ONLY is what shows how little of the sequence bears on the
# landslide ones.
CHCH_FLAT_ONLY = LandformArea(
    name="Christchurch flat land", area=CHRISTCHURCH, landform=FLAT
)
CHCH_SLOPE_ONLY = LandformArea(
    name="Christchurch sloping land", area=CHRISTCHURCH, landform=HILL
)
