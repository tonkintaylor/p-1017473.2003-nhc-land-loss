"""What it costs to rebuild a damaged land structure.

`vul` emits a damage state for a retaining wall rather than a price, so the
money is worked out here. This module holds the repair cost half of that: the
rates NHC's own costing tool assesses a claim on, and the site multiplier it
applies to them, so this study's pricing reproduces the tool's answer rather
than arriving at one of its own.

A wall gives two numbers, and the Act needs both. They come off the **same**
square metre rate, which is how the costing tool works, so the whole of the
difference between them is the site allowance::

    repair cost = m2 rate x wall face area x (1 + site multiplier)
    udv         = m2 rate x wall face area

Access, earthworks and constructability are what it costs to work on this
particular site; they are not part of what the wall cost to build, so they have
no place in undepreciated value. Two things follow. For the same construction,
repair cost can never come out below UDV, because the multiplier is never
negative -- though here it holds by construction rather than by evidence. A
wall rebuilt as a cheaper type than the one that failed (T-122) can come out
below it. And nothing about age or condition enters UDV at all:
undepreciated means no deduction for age, so a twenty-year-old wall and a new
one of the same construction and size are worth the same.

**The rates are per square metre of wall face and exclude GST.** The settlement
arithmetic in :mod:`landloss.loss.settlement` works GST-inclusive, because that
is the basis the Act compares on, so the gross-up happens here at the point of
use and every amount leaving this module is named ``_incl_gst_``.

**The site multiplier is three ratings, not two.** The costing tool rates
construction access, earthworks required, and constructability and
reinstatement, each easy, moderate or difficult, and the combination is a
markup. The tool carries all 27 combinations as a lookup table; every row of it
is the sum of a per-rating markup of 0%, 5% and 10%, so :class:`SiteRatings`
computes the figure rather than storing the table, and
``tests/landloss/loss/test_pricing.py`` checks the formula against all 27 rows.
An all-difficult site attracts 30%, which is also the ceiling the tool's own
line items cap at.

**It applies to the wall construction subtotal only** -- the square metre rate
by the wall face area -- and to nothing else. ``nhc-costing-tool.md`` describes
it as going on the Land SOW subtotal, which would take in inundation removal and
land reinstatement as well; the narrower scope is the decision for this study.
It also settles the grain: a markup on one wall's construction is a **per-wall**
figure, so the three ratings belong beside ``rw_size`` and ``rw_length`` rather
than on the claim.

**Inundation removal is folded into the earthworks rating, not costed on its
own.** Clearing spoil off inundated ground is the first line of the Land SOW,
and it could be a cost in its own right -- a volume at a rate per cubic metre --
or it could be what the earthworks rating is already expressing. This study
takes the second reading for now: :func:`classify_inundation_earthworks` turns
the volume into a rating and the volume buys nothing else. That is a
**simplification, not a finding** (**L-33**), and it has a visible cost. The
markup reaches wall construction alone, so a claim with inundated ground and no
retaining wall on it currently attracts nothing at all for the clearing -- the
work is real and the model prices it at zero. If inundation removal turns out to
be its own line item, it wants a rate per cubic metre and a place in the repair
cost rather than only a nudge to a multiplier.

What this module does **not** yet do, each because a figure has not been
obtained rather than because it was decided against:

- **Whether the replacement should be priced at a higher specification than
  the wall it replaces.** One rate serving both numbers assumes the replacement
  matches the wall that failed, and in practice a failed wall is often rebuilt
  to a more substantial current standard, which would want a higher rate on the
  repair side than on the UDV side. The bias runs one way: settlement is
  ``min(repair, cap)`` less the excess, so understating repair can only lower a
  settlement, never raise it. Carried as **L-34**; the same-rate approach is the
  agreed basis meanwhile, not a stand-in for something better specified.
- **Whether the rate rows the wall types are mapped to are the right ones.**
  Exposure draws each wall one of eight types and a retained height, and each
  type is priced at the costing tool row ``retaining-wall-types.csv`` names
  for it (:func:`construction_type`); the two timber pole types take their pile
  size from the height. Two rows are proposals awaiting the lead --
  ``garden_timber`` on the 175 mm pole rather than Sleepers, and
  ``reinforced_concrete_post_1992`` on MSE rather than Soil Nail -- and the
  rates span a factor of 21, so the mapping moves the answer further than
  anything else in this module.
- **Enabling works, and the compliance items.** Chris Ewens was explicit that
  the wall rates carry no enabling works allowance. Whether enabling works is a
  separate line on the scope of works, or is what the constructability and
  reinstatement rating already prices, is unresolved -- as is what the council
  stormwater connection and the fall-from-height barrier add.

The rates and the multiplier table came from the costing tool itself; the
meeting they were walked through at is ``.agents/context/nhc-costing-tool.md``.
"""

from dataclasses import dataclass
from functools import cache

import numpy as np

from landloss.hazard.landslide.urban.wall_type_fragility import load_wall_types
from landloss.loss.policy import PolicySettings

# Retaining wall rates in dollars per square metre of wall face, **excluding
# GST**, from the costing tool's `lists` sheet. These are the QS-derived rates
# Chris Ewens revises every four months, so they are a snapshot rather than a
# constant of nature; see :data:`WALL_RATES_AS_AT`.
WALL_RATE_EXCL_GST_NZD_PER_M2 = {
    "Timber Pole: 175mm SED": 643.19,
    "Timber Pole: 250mm SED": 744.69,
    "Timber Pole: 300mm SED": 798.80,
    "Timber Pole: 350mm SED": 879.87,
    "Concrete Block": 1_010.58,
    "Concrete Crib": 834.08,
    "Gabion Basket": 958.78,
    "Rock: Mortar Bed": 1_130.08,
    "Reinforced Concrete": 1_224.08,
    "Keystone": 930.54,
    "Sleepers": 1_232.41,
    "UC: 200mm x 60mm": 2_286.93,
    "UC: 250mm x 90mm": 3_063.43,
    "UC: 310mm x 158mm": 4_736.23,
    "PFC: 230mm x 90mm": 1_586.69,
    "PFC: 250mm x 90mm": 1_645.73,
    "PFC: 380mm x 100mm": 2_130.35,
    "Sheet Piling: SP3W / STU1800": 1_328.33,
    "Sheet Piling: SP4W / STU2700": 1_538.33,
    "Driven Timber Pole: 175mm SED": 535.39,
    "Driven Timber Pole: 250mm SED": 575.50,
    "Driven Timber Pole: 300mm SED": 622.81,
    "Driven Timber Pole: 350mm SED": 767.38,
    "Mechanically Stabilised Earth (MSE)": 1_034.95,
    "Shotcrete": 226.67,
    "Soil Nail": 775.00,
    "Palisade: Driven Timber Pole": 900.00,
    "Palisade: Concrete Encased Timber Pole": 896.40,
    "Palisade: Steel Cages and Concrete": 1_632.00,
}

# When the rates above were taken from the tool. They are revised every four
# months, so a run made long after this date is pricing on stale figures.
WALL_RATES_AS_AT = "2026-09-23"

# The costing tool row ``retaining-wall-types.csv`` gives a timber pole wall
# type: no single row, but the pile its height calls for
# (:data:`TIMBER_POLE_HEIGHT_BANDS_M`).
TIMBER_POLE_BY_HEIGHT = "Timber Pole: 175mm SED to 350mm SED, by height"

# The wall types a failed wall is rebuilt as, rather than as a timber pole wall
# (T-122; Wgtn Land Model 2026-10-07, confirmed by Perrie Gilbert 2026-10-12).
# Reinforced masonry block walls and sprayed concrete walls go back like for
# like; everything else -- brick, stone, stacked concrete blocks, crib, old
# poured concrete, garden timber -- is rebuilt as the timber pole wall its
# height calls for. Undepreciated value is always the failed type's.
#
# No wall type is sprayed concrete yet (T-119); add it here when one is.
# `concrete_block` is taken as reinforced block masonry throughout, so stacked
# unreinforced blocks belong under `brick_rock`, the gravity masonry type.
REPLACED_IN_KIND = frozenset({"concrete_block"})

EASY = "E"
MODERATE = "M"
DIFFICULT = "D"

# What each rating adds, as a fraction of the wall cost. The tool enumerates all
# 27 combinations of the three; every row is exactly the sum of these, which is
# why the table itself is not reproduced here.
RATING_MARKUP = {EASY: 0.00, MODERATE: 0.05, DIFFICULT: 0.10}

# What an all-difficult site attracts, and the ceiling the tool's individual
# line items cap at. Named so a test can assert the formula never exceeds it.
MAX_SITE_MULTIPLIER = 3 * RATING_MARKUP[DIFFICULT]

# The timber pole wall a wall of a given retained height is built as, by pile
# size. A taller wall retains more ground and needs a stiffer pile, so the pile
# is chosen off the height rather than drawn: below 1 m it is 175 mm SED, 1 to
# 2 m is 250 mm, 2 to 3 m is 300 mm, and 3 m and above is 350 mm. Each upper
# bound is exclusive, so a wall of exactly 1 m takes the 250 mm pile. These are
# the non-driven timber pole walls; the driven ones are a separate and cheaper
# family in the tool and are deliberately left out.
#
# **The bands are assumed**, set on 2026-09-30 as a first cut rather than taken
# from a design guide. An existing wall is priced at the height exposure drew
# for it; a wall invented for a landslide at its size class's set height
# (:data:`BETA_SIZE_CLASS_HEIGHT_M`).
#
# Age and condition do not move the rate -- they belong to whether the wall
# fails, which is `vul`'s question, not to what replacing it costs.
TIMBER_POLE_HEIGHT_BANDS_M = (
    (1.0, "Timber Pole: 175mm SED"),
    (2.0, "Timber Pole: 250mm SED"),
    (3.0, "Timber Pole: 300mm SED"),
    (np.inf, "Timber Pole: 350mm SED"),
)

# The retained height each size class is priced at. An existing wall carries its
# own height from exposure; this is for a size class with no wall behind it --
# the wall a landslide needs, which is a class before it is a height.
#
# Each is the midpoint of what its class can actually contain. The class bands
# in `landloss.exposure.rw.beta_population` are small below 1 m, medium 1 to
# 2.5 m and large 2.5 m and above, and that module draws heights over 0.4 to
# 3.0 m, so the realised bands are 0.4 to 1.0, 1.0 to 2.5 and 2.5 to 3.0 -- and
# their midpoints land a clean metre apart. Every height here classifies back to
# its own size class, which is what keeps this mapping and those bands from
# drifting apart unnoticed.
#
# These are **set values, not draws**: every medium wall in the study is priced
# at 1.75 m, and so on the 250 mm timber pole rate. So a size class carries no
# variation of its own, and the spread in wall cost within a class comes from
# length, the concrete share and the site ratings alone. Drawing within the
# band, or setting the height off the slope the wall sits on, are both better
# and both deferred (**I-14**).
BETA_SIZE_CLASS_HEIGHT_M = {
    "small": 0.75,
    "medium": 1.75,
    "large": 2.75,
}

# The size classes in ascending order, which is the order the heights above are
# written in. Taken from that mapping rather than restated, so a class cannot be
# added to one and forgotten in the other.
SIZE_CLASSES = tuple(BETA_SIZE_CLASS_HEIGHT_M)

# Inundation volume, in cubic metres, at which clearing the spoil stops being
# one kind of job and becomes the next. They set the **earthworks required**
# rating, which is the one of the three site ratings a land claim can answer
# from its own geometry rather than having to be told.
#
# ---------------------------------------------------------------------------
# THESE TWO NUMBERS ARE ASSUMED AND HAVE NOT BEEN CONFIRMED BY ANYONE AT NHC.
# ---------------------------------------------------------------------------
#
# Nothing in the repository, and nothing said at the costing tool demo, attaches
# a volume to the change of method. What is recorded is qualitative only:
# `nhc-land-cover-and-settlement.md` and **L-28** give two rates per square
# metre, "one for volumes a shovel and a truck can clear, one for volumes
# needing an excavator". No cubic metre figure divides them there or anywhere
# else. The thresholds below were reasoned from plant capability rather than
# taken from a source, so they are **engineering judgement fitted to nothing**,
# in the same class as the culvert and bridge split. They were adopted as a
# working assumption on 2026-09-23 so the chain could run, and are the first
# thing to replace when NHC give a figure (**Q-11**).
#
# They are not idle: through the earthworks rating they set the markup on any
# retaining wall on the same property, so an error here moves wall costs too.
#
# The reasoning behind them:
#
# - **Easy, up to 20 m3.** Hand tools, a wheelbarrow and a truck. A labourer
#   shifts of the order of a cubic metre an hour, so this is a job two people
#   finish in a day or two and nobody hires a machine for.
# - **Moderate, 20 to 200 m3.** A mini excavator, small enough to come through
#   a residential gate or down a driveway. This is where most claims should sit.
# - **Difficult, above 200 m3.** A full-size excavator and truck cartage, which
#   needs proper site access and usually traffic management -- the largest
#   single cost driver Chris Ewens named.
# Bands for the two site ratings nothing measures, proxied off exposure layers
# that do exist. **All four numbers are invented.** They are placeholders with a
# bounded cost: each rating contributes at most 0.10 to the site multiplier and
# the three together cap at 0.30, so the whole proxy can move a wall's repair
# cost by 30% at the outside -- against the factor of 21 that the construction
# type spans. Getting these roughly right matters far less than getting the
# rate right, which is why guessing them is worth doing and guessing the rate
# is not.
#
# Construction access is proxied by the driveway `exposure` routes from the
# building to the road: a longer run is further to carry plant and material.
# Length is a poor stand-in for what actually makes access hard -- width,
# gradient, gateways, overhead lines -- so this orders sites rather than
# measuring them.
EASY_ACCESS_MAX_DRIVEWAY_M = 20.0
MODERATE_ACCESS_MAX_DRIVEWAY_M = 50.0

# Constructability and reinstatement are proxied by the slope at the address.
# Steeper ground is harder to build a wall on and harder to leave tidy. The
# slope is sampled at the address point, not at the wall, so a flat house site
# on a steep section reads as easy.
EASY_CONSTRUCTABILITY_MAX_SLOPE_DEG = 10.0
MODERATE_CONSTRUCTABILITY_MAX_SLOPE_DEG = 20.0

# Where landslide damage is remediated by building a wall that was never there,
# these bands turn the damaged area into a size class. **Invented**, and set low
# on the reasoning that ground which has actually failed is not retained by a
# garden edge: a slip worth remediating wants a wall of consequence, so the
# small class is reserved for the slightest loss rather than being the default.
# Against the pilot's slips -- a median of 17 m2 and a quartile range of 6 to
# 70 -- these put most claims in the medium class and leave both others
# reachable.
SMALL_LANDSLIDE_MAX_AREA_M2 = 10.0
MEDIUM_LANDSLIDE_MAX_AREA_M2 = 100.0

# The same bands read as a volume, used where an inundated depth makes one
# available. Set at the area bands times a nominal half-metre slip, so the two
# measures agree on a deposit of that depth and the deeper one wins otherwise.
# **Invented**, on the same footing as the areas.
SMALL_LANDSLIDE_MAX_VOLUME_M3 = 5.0
MEDIUM_LANDSLIDE_MAX_VOLUME_M3 = 50.0

# The shape of the ground a slip takes, and the wall that goes back in its place.
# A failure on a residential section takes a strip off the slope, wider along the
# face than it is deep into the section, so the wall follows the width. Two to
# one is the assumed aspect; the margin is the length beyond the failure at each
# end, because a wall is not stopped at the edge of the ground that moved; and
# the minimum is what it is worth mobilising for at all. **All three invented.**
#
# **The land and the wall are priced independently.** Repairing a damaged wall
# was once taken to reinstate a metre of ground behind it, which the land then
# paid nothing for. That allowance is gone, decided on 2026-09-29: a retaining
# wall and the ground it holds are two assets with two caps, and letting one
# discharge the other's repair made the land's cost depend on whether the site
# happened to own a wall.
LANDSLIDE_WALL_ASPECT_RATIO = 2.0
LANDSLIDE_WALL_MARGIN_M = 2.0
MIN_LANDSLIDE_WALL_LENGTH_M = 5.0

# What it costs to clear a cubic metre of slip debris off a section.
#
# **From the costing tool's own `lists` sheet**, not assumed: the line item
# "Clear site: Load, cart and tip material", unit m3, rate 150. Excluding GST,
# on the same basis as the retaining wall square metre rates that come off the
# same sheet.
#
# The sheet's only other cubic metre option is a skip bin -- $340 for 3.5 m3 and
# $450 for 6.0 m3, which work out dearer per cubic metre on a small job and
# cheaper on none. Load, cart and tip is the line that describes clearing a
# slip, so it is the one used.
INUNDATION_REMOVAL_RATE_EXCL_GST_NZD_PER_M3 = 150.0
INUNDATION_REMOVAL_LINE_ITEM = "Clear site: Load, cart and tip material"

# What a damaged culvert or bridge costs (John Leeves, 2026-10-13), both
# excluding GST and the same for either kind. A replacement is a rate per lineal
# metre of span; nothing supplies a span, so every crossing takes the default,
# $75,000 in all. A crossing a landslide buried but did not break is cleared
# for a fixed sum instead.
CROSSING_RATE_EXCL_GST_NZD_PER_M = 15_000.0
CROSSING_DEFAULT_SPAN_M = 5.0
CROSSING_CLEARING_EXCL_GST_NZD = 1_000.0

# The professional fees a claim carries beyond the physical work, **from the
# costing tool's own `lists` sheet**, its "Fee type" table. Mileage is the one
# fee left out, on instruction; the tool carries it at zero in any case, so
# leaving it out changes no number and only says where the line is.
#
# These answer a question the study had open: the square metre rates do **not**
# carry design, consent or survey. They are separate line items, so a wall
# priced on the rate alone was missing all of them.
PROFESSIONAL_FEES_EXCL_GST_NZD = {
    "Consent costs": 1000.0,
    "Design costs": 800.0,
    "Engineering costs": 1000.0,
    "H&S costs": 300.0,
    "Project management costs": 1000.0,
    "Survey costs": 1000.0,
}
PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD = sum(PROFESSIONAL_FEES_EXCL_GST_NZD.values())

# Professional fees as a share of the walls they are for (Perrie Gilbert,
# 2026-10-12): 20% of what the claim's walls cost to build, with the costing
# tool's own fee total as the floor. A large wall needs more design, engineering
# and supervision than the flat fee allows; a small one still needs a consent.
PROFESSIONAL_FEES_SHARE = 0.20

# The on-costs a claim's works carry beyond the walls and their fees, and the
# contingency on the whole repair (Perrie Gilbert, 2026-10-13), each excluding
# GST and each built on the one before, in this order:
#
# - **Mobilisation and demobilisation**, on a claim with wall works: 15% of the
#   walls as built -- site multiplier, specification uplift and rate scaling
#   all in -- plus the professional fees, never less than $5,000.
# - **Project management**: 10% of the walls, the professional fees, the
#   mobilisation and the culverts and bridges, so a claim whose only works are
#   a crossing carries it too.
# - **Contingency**: 20% of the whole repair cost -- the wall works above, and
#   spoil removal, liquefaction and culverts and bridges as well -- applied
#   last, on every claim, with wall works or without.
MOB_DEMOB_SHARE = 0.15
MOB_DEMOB_MIN_EXCL_GST_NZD = 5_000.0
PROJECT_MANAGEMENT_SHARE = 0.10
CONTINGENCY_SHARE = 0.20

# What a Canterbury liquefaction land cost in 2010/2011 dollars is multiplied by
# to bring it to today's, **a placeholder on instruction** (L-23): the growth in
# construction labour costs since the February 2011 earthquake.
#
# From the Stats NZ Labour Cost Index, salary and ordinary time wage rates for
# the construction industry (series LCIQ.SG51E9, base June 2009 quarter = 1000):
# 1,030 in the March 2011 quarter to 1,465 in the December 2025 quarter, the
# latest published, is 1.422. Taken from the September 2010 or June 2011
# quarter instead it is 1.438 or 1.413, and all industries combined
# (LCIQ.SG51Z9) gives 1.400. The index measures pay rates only, so it does not
# follow the plant and materials a land repair also uses (L-74).
LIQ_COST_ESCALATION = 1.42
LIQ_COST_ESCALATION_SOURCE = (
    "Stats NZ Labour Cost Index, construction salary and ordinary time wage rates "
    "(LCIQ.SG51E9), March 2011 quarter 1,030 to December 2025 quarter 1,465"
)

EASY_INUNDATION_MAX_VOLUME_M3 = 20.0
MODERATE_INUNDATION_MAX_VOLUME_M3 = 200.0


def _as_markup(rating: np.ndarray | str, *, name: str) -> np.ndarray:
    """Return the markup a rating attracts, refusing anything else.

    Args:
        rating: The rating, ``"E"``, ``"M"`` or ``"D"``, scalar or array. Case
            is not significant.
        name: The parameter's name, for the error message.

    Returns:
        The markup as a float array, shaped like ``rating``.

    Raises:
        ValueError: If any element is not one of the three ratings.
    """
    ratings = np.char.upper(np.asarray(rating, dtype=str))
    flat = ratings.ravel().tolist()
    unknown = sorted(set(flat) - set(RATING_MARKUP))
    if unknown:
        msg = (
            f"{name} must be one of {EASY}, {MODERATE} or {DIFFICULT}; "
            f"got {', '.join(repr(value) for value in unknown)}"
        )
        raise ValueError(msg)
    markups = np.array([RATING_MARKUP[value] for value in flat], dtype=float)
    return markups.reshape(ratings.shape)


@dataclass(frozen=True)
class SiteRatings:
    """How hard a site is to work on, as the costing tool rates it.

    The three are rated independently, each easy, moderate or difficult. T+T
    already supply all three in the duty geotechnical report, so this study can
    generate them rather than having to source them.

    Scalars rate one wall; arrays of equal length rate a population, which is
    how a portfolio is priced in one call.

    Attributes:
        construction_access: Getting people and machinery to the wall.
        earthworks_required: The earthworks the remedial solution needs.
        constructability_reinstatement: Building the wall, and tidying the site
            up on the way out.
    """

    construction_access: np.ndarray | str
    earthworks_required: np.ndarray | str
    constructability_reinstatement: np.ndarray | str

    @property
    def multiplier(self) -> np.ndarray:
        """Return the markup on the wall cost, from 0 to 0.30.

        Returns:
            The sum of the three ratings' markups.
        """
        return (
            _as_markup(self.construction_access, name="construction_access")
            + _as_markup(self.earthworks_required, name="earthworks_required")
            + _as_markup(
                self.constructability_reinstatement,
                name="constructability_reinstatement",
            )
        )


def inundation_volume_m3(
    inundated_area_m2: np.ndarray | float,
    inundated_mean_depth_m: np.ndarray | float,
) -> np.ndarray:
    """Return the volume of spoil to be cleared off inundated ground.

    `vul` sends the inundated insured area and the mean depth of what came to
    rest on it, which is all a volume needs. Mean depth rather than maximum, so
    this is the volume of the deposit as modelled and not a worst case.

    Args:
        inundated_area_m2: Insured area buried by material coming to rest.
        inundated_mean_depth_m: How deep that material lies, on average.

    Returns:
        The volume in cubic metres.

    Raises:
        ValueError: If either is negative or not finite.
    """
    area = np.asarray(inundated_area_m2, dtype=float)
    depth = np.asarray(inundated_mean_depth_m, dtype=float)
    for name, values in (
        ("inundated_area_m2", area),
        ("inundated_mean_depth_m", depth),
    ):
        if not np.all(np.isfinite(values)) or np.any(values < 0):
            msg = f"{name} must be finite and not negative"
            raise ValueError(msg)
    return area * depth


def professional_fees_incl_gst_nzd(
    wall_cost_incl_gst_nzd: np.ndarray | float,
    *,
    policy: PolicySettings,
    share: float = PROFESSIONAL_FEES_SHARE,
    floor_excl_gst_nzd: float = PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD,
) -> np.ndarray:
    """Return a claim's professional fees, including GST.

    Consent, design, engineering, health and safety, project management and
    survey: :data:`PROFESSIONAL_FEES_SHARE` of what the claim's walls cost to
    build, as built -- site multiplier, specification uplift and all -- and
    never less than the costing tool's own total,
    :data:`PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD`, which takes no multiplier.
    Mileage is excluded on instruction.

    **Fees are per claim, not per wall or per cost line.** A claim gets one
    consent, one design and one survey however many walls stand on it, so this
    is charged once and not folded into a wall's square metre cost. The caller
    decides which claims pay them; a wall, failed or invented, is what gets
    designed and consented.

    Args:
        wall_cost_incl_gst_nzd: What the claim's walls cost to build, failed and
            invented together, including GST.
        policy: The settings this scenario runs under, which carry the GST rate.
        share: The fees as a share of the wall cost.
        floor_excl_gst_nzd: The least the fees can be, before GST.

    Returns:
        The fees in GST-inclusive dollars, one per claim.

    Raises:
        ValueError: If any wall cost is negative or not finite.
    """
    cost = np.asarray(wall_cost_incl_gst_nzd, dtype=float)
    if not np.all(np.isfinite(cost)) or np.any(cost < 0):
        msg = "wall_cost_incl_gst_nzd must be finite and not negative"
        raise ValueError(msg)
    floor = floor_excl_gst_nzd * (1.0 + policy.gst_rate)
    return np.maximum(share * cost, floor)


@dataclass(frozen=True)
class OnCosts:
    """The on-costs a claim's works carry, including GST, one per claim.

    Attributes:
        mob_demob: Mobilisation and demobilisation.
        project_management: Project management.
    """

    mob_demob: np.ndarray
    project_management: np.ndarray

    @property
    def total(self) -> np.ndarray:
        """Return the two summed."""
        return self.mob_demob + self.project_management


def on_costs_incl_gst_nzd(
    wall_cost_incl_gst_nzd: np.ndarray | float,
    fees_incl_gst_nzd: np.ndarray | float,
    crossing_cost_incl_gst_nzd: np.ndarray | float,
    *,
    policy: PolicySettings,
) -> OnCosts:
    """Return the on-costs of a claim's works, including GST.

    Each is built on the one before (:data:`MOB_DEMOB_SHARE` and below):
    mobilisation on the walls and fees, with a floor, on a claim with wall
    works only; then project management on the walls, fees, mobilisation and
    crossings, so a claim whose only works are a crossing carries project
    management and no mobilisation. The contingency is not among them: it goes
    on the whole repair (:func:`contingency_incl_gst_nzd`).

    Args:
        wall_cost_incl_gst_nzd: What the claim's walls cost to build, failed and
            invented together, as built, including GST. Zero where it has none.
        fees_incl_gst_nzd: The claim's professional fees, from
            :func:`professional_fees_incl_gst_nzd`.
        crossing_cost_incl_gst_nzd: What replacing or clearing the claim's
            culverts and bridges costs, including GST.
        policy: The settings this scenario runs under, which carry the GST rate.

    Returns:
        The two on-costs in GST-inclusive dollars.

    Raises:
        ValueError: If any cost or fee is negative or not finite.
    """
    cost = np.asarray(wall_cost_incl_gst_nzd, dtype=float)
    fees = np.asarray(fees_incl_gst_nzd, dtype=float)
    crossing = np.asarray(crossing_cost_incl_gst_nzd, dtype=float)
    for name, values in (
        ("wall_cost_incl_gst_nzd", cost),
        ("fees_incl_gst_nzd", fees),
        ("crossing_cost_incl_gst_nzd", crossing),
    ):
        if not np.all(np.isfinite(values)) or np.any(values < 0):
            msg = f"{name} must be finite and not negative"
            raise ValueError(msg)
    floor = MOB_DEMOB_MIN_EXCL_GST_NZD * (1.0 + policy.gst_rate)
    mob = np.where(cost > 0, np.maximum(MOB_DEMOB_SHARE * (cost + fees), floor), 0.0)
    pm = PROJECT_MANAGEMENT_SHARE * (cost + fees + mob + crossing)
    return OnCosts(mob_demob=mob, project_management=pm)


def contingency_incl_gst_nzd(
    repair_cost_incl_gst_nzd: np.ndarray | float,
) -> np.ndarray:
    """Return the contingency on a claim's repair, including GST.

    :data:`CONTINGENCY_SHARE` of everything else the repair costs -- walls,
    spoil, fees, on-costs, liquefaction and crossings -- applied last.

    Args:
        repair_cost_incl_gst_nzd: The claim's repair cost before contingency,
            including GST.

    Returns:
        The contingency in GST-inclusive dollars.

    Raises:
        ValueError: If any repair cost is negative or not finite.
    """
    repair = np.asarray(repair_cost_incl_gst_nzd, dtype=float)
    if not np.all(np.isfinite(repair)) or np.any(repair < 0):
        msg = "repair_cost_incl_gst_nzd must be finite and not negative"
        raise ValueError(msg)
    return CONTINGENCY_SHARE * repair


def inundation_removal_cost_incl_gst_nzd(
    volume_m3: np.ndarray | float,
    *,
    policy: PolicySettings,
    rate_excl_gst_nzd_per_m3: float = INUNDATION_REMOVAL_RATE_EXCL_GST_NZD_PER_M3,
) -> np.ndarray:
    """Return what it costs to clear the spoil a landslide left, including GST.

    The volume times a rate, and nothing else. No minimum, no mobilisation, no
    allowance for where the material has to go -- all of which a real quote
    would carry and none of which there is a basis for here.

    **The spoil now costs something as well as setting a rating.** It used to do
    only the latter, which meant a claim with buried ground and no retaining
    wall was charged nothing at all for the clearing -- real work priced at zero
    (**L-33**). That is now closed, at the price of a possible double count
    worth watching: the same volume still sets ``earthworks_required``, which
    marks up wall construction. The rating is about how hard the site is to
    build on and this is the cost of carting material away, so they are
    different things, but nothing has confirmed that the costing tool sees it
    the same way.

    Args:
        volume_m3: Volume of spoil, from :func:`inundation_volume_m3`.
        policy: The settings this scenario runs under, which carry the GST rate.
        rate_excl_gst_nzd_per_m3: What a cubic metre costs to clear, excluding
            GST. Defaults to the costing tool's own
            :data:`INUNDATION_REMOVAL_LINE_ITEM` rate.

    Returns:
        The cost in GST-inclusive dollars.

    Raises:
        ValueError: If any volume is negative or not finite.
    """
    volumes = np.asarray(volume_m3, dtype=float)
    if not np.all(np.isfinite(volumes)) or np.any(volumes < 0):
        msg = "volume_m3 must be finite and not negative"
        raise ValueError(msg)
    return volumes * rate_excl_gst_nzd_per_m3 * (1.0 + policy.gst_rate)


def crossing_replacement_cost_incl_gst_nzd(
    span_m: np.ndarray | float | None = None,
    *,
    policy: PolicySettings,
    rate_excl_gst_nzd_per_m: float = CROSSING_RATE_EXCL_GST_NZD_PER_M,
    default_span_m: float = CROSSING_DEFAULT_SPAN_M,
) -> np.ndarray:
    """Return what it costs to replace a culvert or a bridge, including GST.

    A rate per lineal metre of span, the same for a culvert as for a bridge
    (John Leeves, 2026-10-13). Nothing supplies a span yet, so every crossing
    takes :data:`CROSSING_DEFAULT_SPAN_M`; a span, where one arrives, is used
    in its place.

    The same figure is the crossing's undepreciated value: it is what the
    structure costs to build new, with nothing for the site, so it serves both
    sides of the Act's comparison, as a wall's square metre rate does.

    Args:
        span_m: Each crossing's span, or ``None`` for the default throughout.
            A missing span within an array also takes the default.
        policy: The settings this scenario runs under, which carry the GST rate.
        rate_excl_gst_nzd_per_m: What a metre of span costs, excluding GST.
        default_span_m: The span taken where none is known.

    Returns:
        The cost in GST-inclusive dollars.

    Raises:
        ValueError: If any span is negative.
    """
    span = np.asarray(default_span_m if span_m is None else span_m, dtype=float)
    span = np.where(np.isnan(span), default_span_m, span)
    if np.any(span < 0):
        msg = "span_m must not be negative"
        raise ValueError(msg)
    return span * rate_excl_gst_nzd_per_m * (1.0 + policy.gst_rate)


def crossing_clearing_cost_incl_gst_nzd(
    *,
    policy: PolicySettings,
    clearing_excl_gst_nzd: float = CROSSING_CLEARING_EXCL_GST_NZD,
) -> float:
    """Return what it costs to clear mud out of a culvert or bridge, with GST.

    A fixed sum per crossing (John Leeves, 2026-10-13), for a structure a
    landslide buried but did not break.

    Args:
        policy: The settings this scenario runs under, which carry the GST rate.
        clearing_excl_gst_nzd: The sum, excluding GST.

    Returns:
        The cost in GST-inclusive dollars.
    """
    return clearing_excl_gst_nzd * (1.0 + policy.gst_rate)


def classify_inundation_earthworks(volume_m3: np.ndarray | float) -> np.ndarray:
    """Return the earthworks rating the spoil volume implies.

    The bands are :data:`EASY_INUNDATION_MAX_VOLUME_M3` and
    :data:`MODERATE_INUNDATION_MAX_VOLUME_M3`. **Both are assumed and neither
    has been confirmed**; what they rest on, which is nothing, is set out where
    they are defined.

    This rating is the *only* thing the spoil volume buys. Clearing it is not
    costed as a line of its own, so on a claim with no retaining wall the
    volume reaches no cost at all -- see the module docstring and **L-33**.

    A claim with no inundation rates easy, which is the right answer rather
    than a missing one: there is no spoil to clear.

    Args:
        volume_m3: Volume of spoil, from :func:`inundation_volume_m3`.

    Returns:
        ``"E"``, ``"M"`` or ``"D"`` per claim, ready for
        :class:`SiteRatings`.

    Raises:
        ValueError: If any volume is negative or not finite.
    """
    volumes = np.asarray(volume_m3, dtype=float)
    if not np.all(np.isfinite(volumes)) or np.any(volumes < 0):
        msg = "volume_m3 must be finite and not negative"
        raise ValueError(msg)
    return np.select(
        [
            volumes <= EASY_INUNDATION_MAX_VOLUME_M3,
            volumes <= MODERATE_INUNDATION_MAX_VOLUME_M3,
        ],
        [EASY, MODERATE],
        default=DIFFICULT,
    )


def _classify(
    values: np.ndarray | float,
    name: str,
    easy_max: float,
    moderate_max: float,
) -> np.ndarray:
    """Return E/M/D for values against two ascending thresholds.

    Args:
        values: The measure, scalar or array.
        name: The measure's name, for the error message.
        easy_max: At or below this is easy.
        moderate_max: At or below this is moderate; above it is difficult.

    Returns:
        ``"E"``, ``"M"`` or ``"D"`` per element.

    Raises:
        ValueError: If any value is negative or not finite.
    """
    measured = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(measured)) or np.any(measured < 0):
        msg = f"{name} must be finite and not negative"
        raise ValueError(msg)
    return np.select(
        [measured <= easy_max, measured <= moderate_max],
        [EASY, MODERATE],
        default=DIFFICULT,
    )


def classify_construction_access(driveway_length_m: np.ndarray | float) -> np.ndarray:
    """Return the construction access rating the driveway length implies.

    A **proxy, not a measurement**. `exposure` routes a driveway from each
    building to the road, and its length stands in for how far plant and
    material have to be carried. The bands are
    :data:`EASY_ACCESS_MAX_DRIVEWAY_M` and
    :data:`MODERATE_ACCESS_MAX_DRIVEWAY_M`, both invented.

    A claim with no driveway routed is the caller's to handle: this reads a
    zero length as the easiest site, which is right for a house on the street
    front and wrong for one the router could not reach at all.

    Args:
        driveway_length_m: Length of the routed driveway.

    Returns:
        ``"E"``, ``"M"`` or ``"D"``, ready for :class:`SiteRatings`.

    Raises:
        ValueError: If any length is negative or not finite.
    """
    return _classify(
        driveway_length_m,
        "driveway_length_m",
        EASY_ACCESS_MAX_DRIVEWAY_M,
        MODERATE_ACCESS_MAX_DRIVEWAY_M,
    )


def classify_constructability(slope_deg: np.ndarray | float) -> np.ndarray:
    """Return the constructability rating the ground slope implies.

    A **proxy, not a measurement**, on the same footing as
    :func:`classify_construction_access`. Steeper ground is harder to build a
    wall on and harder to reinstate on the way out. The bands are
    :data:`EASY_CONSTRUCTABILITY_MAX_SLOPE_DEG` and
    :data:`MODERATE_CONSTRUCTABILITY_MAX_SLOPE_DEG`, both invented, and the
    slope is sampled at the address rather than at the wall.

    Args:
        slope_deg: Ground slope in degrees.

    Returns:
        ``"E"``, ``"M"`` or ``"D"``, ready for :class:`SiteRatings`.

    Raises:
        ValueError: If any slope is negative or not finite.
    """
    return _classify(
        slope_deg,
        "slope_deg",
        EASY_CONSTRUCTABILITY_MAX_SLOPE_DEG,
        MODERATE_CONSTRUCTABILITY_MAX_SLOPE_DEG,
    )


def classify_landslide_wall_size(
    damaged_area_m2: np.ndarray | float,
    inundated_volume_m3: np.ndarray | float = 0.0,
) -> np.ndarray:
    """Return the size of wall a landslide-damaged area is remediated with.

    Where a landslide takes ground on a claim that carries **no damaged
    retaining wall**, reinstating the land is assumed to mean building one,
    sized by how much ground went.

    **Both measures are used where both are available.** Area always is;
    volume only where an inundated mean depth came through, and it is zero
    otherwise. Each gives a class, and the **larger of the two** is taken, so a
    deep deposit over a small footprint is not read as a small job. The bands
    are :data:`SMALL_LANDSLIDE_MAX_AREA_M2`,
    :data:`MEDIUM_LANDSLIDE_MAX_AREA_M2`,
    :data:`SMALL_LANDSLIDE_MAX_VOLUME_M3` and
    :data:`MEDIUM_LANDSLIDE_MAX_VOLUME_M3`, and all four are **assumed, not
    sourced**.

    This is a remediation cost, not an asset: a wall that never existed has no
    undepreciated value, so it belongs on the repair side of
    ``min(repair, cap)`` and must not be added to the cap.

    Args:
        damaged_area_m2: Insured area taken by the landslide.
        inundated_volume_m3: Volume of the deposit, from
            :func:`inundation_volume_m3`. Zero where no depth was sent.

    Returns:
        ``"small"``, ``"medium"`` or ``"large"``, ready for
        :func:`beta_wall_face_area_m2`.

    Raises:
        ValueError: If any area or volume is negative or not finite.
    """
    areas = np.asarray(damaged_area_m2, dtype=float)
    volumes = np.asarray(inundated_volume_m3, dtype=float)
    for name, values in (
        ("damaged_area_m2", areas),
        ("inundated_volume_m3", volumes),
    ):
        if not np.all(np.isfinite(values)) or np.any(values < 0):
            msg = f"{name} must be finite and not negative"
            raise ValueError(msg)
    by_area = np.select(
        [areas <= SMALL_LANDSLIDE_MAX_AREA_M2, areas <= MEDIUM_LANDSLIDE_MAX_AREA_M2],
        [0, 1],
        default=2,
    )
    by_volume = np.select(
        [
            volumes <= SMALL_LANDSLIDE_MAX_VOLUME_M3,
            volumes <= MEDIUM_LANDSLIDE_MAX_VOLUME_M3,
        ],
        [0, 1],
        default=2,
    )
    return np.asarray(SIZE_CLASSES)[np.maximum(by_area, by_volume)]


def landslide_wall_length_m(evacuated_area_m2: np.ndarray | float) -> np.ndarray:
    """Return the length of the wall a landslide-damaged area is remediated with.

    The wall follows the **width of the failure**, not a side of it, and is
    measured off the **evacuated** insured ground alone: the wall goes across
    the scar, and the deposit below it is cleared, not retained (2026-10-14).
    Ground lost off a residential slope goes as a strip that is wider along the
    face than it is deep into the section, taken here as
    :data:`LANDSLIDE_WALL_ASPECT_RATIO` to one, so a slip of area ``A`` is
    ``sqrt(A / 2)`` deep and twice that wide. To the width is added
    :data:`LANDSLIDE_WALL_MARGIN_M` at each end, because a wall is not stopped
    at the edge of the ground that moved, and the result is floored at
    :data:`MIN_LANDSLIDE_WALL_LENGTH_M`, because remediation does not scale down
    to nothing -- there is a length below which nobody mobilises.

    That floor is what stops the pilot's many small slips pricing at almost
    zero. **Every one of the three numbers is invented**, and together they set
    how large the invented walls are, which is the largest single lever on the
    landslide side of the repair cost.

    Args:
        evacuated_area_m2: Insured area the landslide evacuated.

    Returns:
        The length in metres.

    Raises:
        ValueError: If any area is negative or not finite.
    """
    areas = np.asarray(evacuated_area_m2, dtype=float)
    if not np.all(np.isfinite(areas)) or np.any(areas < 0):
        msg = "evacuated_area_m2 must be finite and not negative"
        raise ValueError(msg)
    across = LANDSLIDE_WALL_ASPECT_RATIO * np.sqrt(areas / LANDSLIDE_WALL_ASPECT_RATIO)
    return np.maximum(
        across + 2.0 * LANDSLIDE_WALL_MARGIN_M, MIN_LANDSLIDE_WALL_LENGTH_M
    )


def timber_pole_wall_type(height_m: np.ndarray | float) -> np.ndarray:
    """Return the timber pole wall a wall of this height is built as.

    Banded by :data:`TIMBER_POLE_HEIGHT_BANDS_M`, so a taller wall takes a
    larger pile and a dearer rate.

    Args:
        height_m: Retained height of the wall, scalar or array.

    Returns:
        The wall type, named as :data:`WALL_RATE_EXCL_GST_NZD_PER_M2` keys it,
        shaped like ``height_m``.

    Raises:
        ValueError: If any height is negative or not finite.
    """
    heights = np.asarray(height_m, dtype=float)
    if not np.all(np.isfinite(heights)) or np.any(heights < 0):
        msg = "height_m must be finite and not negative"
        raise ValueError(msg)
    bounds = np.array([bound for bound, _ in TIMBER_POLE_HEIGHT_BANDS_M[:-1]])
    names = np.array([name for _, name in TIMBER_POLE_HEIGHT_BANDS_M])
    # side="right" puts a height sitting on a bound into the band above it.
    return names[np.searchsorted(bounds, heights, side="right")]


def timber_pole_rate_excl_gst_nzd_per_m2(height_m: np.ndarray | float) -> np.ndarray:
    """Return the timber pole rate for a wall of this height, excluding GST.

    Args:
        height_m: Retained height of the wall, scalar or array.

    Returns:
        The rate in GST-exclusive dollars per square metre of wall face, shaped
        like ``height_m``.

    Raises:
        ValueError: If any height is negative or not finite.
    """
    return wall_rate_excl_gst_nzd_per_m2(timber_pole_wall_type(height_m))


def wall_rate_excl_gst_nzd_per_m2(wall_type: np.ndarray | str) -> np.ndarray:
    """Return the square metre rate for a wall type, excluding GST.

    Args:
        wall_type: The construction type, named as
            :data:`WALL_RATE_EXCL_GST_NZD_PER_M2` keys it. Scalar or array.

    Returns:
        The rate in GST-exclusive dollars per square metre of wall face.

    Raises:
        ValueError: If any wall type is not one the costing tool carries. The
            rates are a closed list, so an unrecognised type is a mapping error
            upstream rather than a wall the tool would price some other way.
    """
    types = np.asarray(wall_type, dtype=str)
    flat = types.ravel().tolist()
    unknown = sorted(set(flat) - set(WALL_RATE_EXCL_GST_NZD_PER_M2))
    if unknown:
        msg = f"unknown wall type(s): {', '.join(repr(value) for value in unknown)}"
        raise ValueError(msg)
    rates = np.array(
        [WALL_RATE_EXCL_GST_NZD_PER_M2[value] for value in flat], dtype=float
    )
    return rates.reshape(types.shape)


@cache
def _rate_items() -> dict[str, str]:
    """Return the costing tool row each wall type is priced at."""
    table = load_wall_types()
    return dict(zip(table["wall_type"], table["nhc_rate_item"], strict=True))


def construction_type(
    wall_type: np.ndarray | str, height_m: np.ndarray | float
) -> np.ndarray:
    """Return the costing tool row a wall of this type and height is priced at.

    The row ``retaining-wall-types.csv`` names for the type, except that the two
    timber pole types take the pile their height calls for
    (:func:`timber_pole_wall_type`).

    Args:
        wall_type: The wall type exposure drew, one of
            :data:`~landloss.hazard.landslide.urban.wall_type_fragility.WALL_TYPES`.
        height_m: Retained height of the wall, shaped like ``wall_type``.

    Returns:
        The construction type, named as :data:`WALL_RATE_EXCL_GST_NZD_PER_M2`
        keys it, shaped like ``wall_type``.

    Raises:
        ValueError: If a wall type is not one of the eight, or a height is
            negative or not finite.
    """
    types = np.asarray(wall_type, dtype=object)
    heights = np.broadcast_to(np.asarray(height_m, dtype=float), types.shape)
    items = _rate_items()
    unknown = sorted({str(value) for value in types.ravel()} - set(items))
    if unknown:
        msg = f"unknown wall type(s): {', '.join(repr(value) for value in unknown)}"
        raise ValueError(msg)
    rows = np.vectorize(items.__getitem__, otypes=[object])(types)
    by_height = rows == TIMBER_POLE_BY_HEIGHT
    return np.where(by_height, timber_pole_wall_type(heights), rows).astype(str)


def wall_type_rate_excl_gst_nzd_per_m2(
    wall_type: np.ndarray | str, height_m: np.ndarray | float
) -> np.ndarray:
    """Return the square metre rate for a wall of this type and height, excl GST.

    Args:
        wall_type: The wall type exposure drew.
        height_m: Retained height of the wall, shaped like ``wall_type``.

    Returns:
        The rate in GST-exclusive dollars per square metre of wall face.

    Raises:
        ValueError: As :func:`construction_type`.
    """
    return wall_rate_excl_gst_nzd_per_m2(construction_type(wall_type, height_m))


def replacement_construction_type(
    wall_type: np.ndarray | str, height_m: np.ndarray | float
) -> np.ndarray:
    """Return the costing tool row a failed wall is rebuilt as.

    A wall of a type in :data:`REPLACED_IN_KIND` is rebuilt as itself
    (:func:`construction_type`); any other is rebuilt as the timber pole wall
    its height calls for (:func:`timber_pole_wall_type`).

    Args:
        wall_type: The type that failed.
        height_m: Retained height of the replacement, shaped like ``wall_type``.

    Returns:
        The construction type, named as :data:`WALL_RATE_EXCL_GST_NZD_PER_M2`
        keys it, shaped like ``wall_type``.

    Raises:
        ValueError: As :func:`construction_type`.
    """
    types = np.asarray(wall_type, dtype=object)
    heights = np.broadcast_to(np.asarray(height_m, dtype=float), types.shape)
    own = construction_type(types, heights)
    in_kind = np.isin(types.astype(str), list(REPLACED_IN_KIND))
    return np.where(in_kind, own, timber_pole_wall_type(heights)).astype(str)


def replacement_rate_excl_gst_nzd_per_m2(
    wall_type: np.ndarray | str, height_m: np.ndarray | float
) -> np.ndarray:
    """Return the square metre rate a failed wall is rebuilt at, excluding GST.

    Args:
        wall_type: The type that failed.
        height_m: Retained height of the replacement, shaped like ``wall_type``.

    Returns:
        The rate in GST-exclusive dollars per square metre of wall face.

    Raises:
        ValueError: As :func:`construction_type`.
    """
    return wall_rate_excl_gst_nzd_per_m2(
        replacement_construction_type(wall_type, height_m)
    )


def beta_wall_height_m(rw_size: np.ndarray | str) -> np.ndarray:
    """Return the retained height a size class is priced at.

    Args:
        rw_size: The size class, ``"small"``, ``"medium"`` or ``"large"``, as
            `vul` sends it. Scalar or array. Case is not significant.

    Returns:
        The height in metres, shaped like ``rw_size``.

    Raises:
        ValueError: If any element is not one of the three size classes.
    """
    sizes = np.char.lower(np.asarray(rw_size, dtype=str))
    flat = sizes.ravel().tolist()
    unknown = sorted(set(flat) - set(BETA_SIZE_CLASS_HEIGHT_M))
    if unknown:
        msg = (
            "rw_size must be one of "
            f"{', '.join(BETA_SIZE_CLASS_HEIGHT_M)}; "
            f"got {', '.join(repr(value) for value in unknown)}"
        )
        raise ValueError(msg)
    heights = np.array([BETA_SIZE_CLASS_HEIGHT_M[value] for value in flat], dtype=float)
    return heights.reshape(sizes.shape)


def wall_face_area_m2(
    height_m: np.ndarray | float,
    length_m: np.ndarray | float,
) -> np.ndarray:
    """Return the area of wall face the rate is charged against.

    Retained height rather than built height, since that is what the wall
    population carries and what a geotechnical report records.

    Args:
        height_m: Retained height of the wall.
        length_m: Length of the wall along its run.

    Returns:
        The face area in square metres.

    Raises:
        ValueError: If either is negative or not finite.
    """
    height = np.asarray(height_m, dtype=float)
    length = np.asarray(length_m, dtype=float)
    for name, values in (("height_m", height), ("length_m", length)):
        if not np.all(np.isfinite(values)) or np.any(values < 0):
            msg = f"{name} must be finite and not negative"
            raise ValueError(msg)
    return height * length


def beta_wall_face_area_m2(
    rw_size: np.ndarray | str,
    length_m: np.ndarray | float,
) -> np.ndarray:
    """Return the wall face area from the size class and length `vul` sends.

    The height is the set value :data:`BETA_SIZE_CLASS_HEIGHT_M` gives the
    class, so two walls of the same class and length price identically.

    Args:
        rw_size: The size class, scalar or array.
        length_m: Length of the wall along its run.

    Returns:
        The face area in square metres.

    Raises:
        ValueError: If the length is negative or not finite, or the size class
            is not one of the three.
    """
    return wall_face_area_m2(beta_wall_height_m(rw_size), length_m)


def _wall_cost_incl_gst_nzd(
    rate_excl_gst_nzd_per_m2: np.ndarray | float,
    face_area_m2: np.ndarray | float,
    *,
    site_multiplier: np.ndarray | float,
    spec_uplift: float = 0.0,
    policy: PolicySettings,
) -> np.ndarray:
    """Return a wall's cost from a rate and a site allowance, including GST.

    The one calculation behind both numbers this module produces. Repair cost
    passes the site multiplier and the specification uplift; undepreciated value
    passes neither, which is the whole of the difference between them.

    The two allowances are different things and both belong on the repair side.
    The **site multiplier** is what this particular site costs to work on. The
    **specification uplift** is that a failed wall is rebuilt to a more
    substantial current standard than the one that failed, which the rates carry
    no allowance for (**L-34**).

    Args:
        rate_excl_gst_nzd_per_m2: The square metre rate, excluding GST.
        face_area_m2: Area of wall face.
        site_multiplier: The site allowance, or zero for none.
        spec_uplift: The specification allowance, or zero for a like-for-like
            rebuild. Undepreciated value always passes zero.
        policy: The settings this scenario runs under.

    Returns:
        The cost in GST-inclusive dollars.

    Raises:
        ValueError: If the area is negative or not finite.
    """
    area = np.asarray(face_area_m2, dtype=float)
    if not np.all(np.isfinite(area)) or np.any(area < 0):
        msg = "face_area_m2 must be finite and not negative"
        raise ValueError(msg)
    excl_gst = (
        rate_excl_gst_nzd_per_m2 * area * (1.0 + site_multiplier) * (1.0 + spec_uplift)
    )
    return excl_gst * (1.0 + policy.gst_rate)


def wall_repair_cost_incl_gst_nzd(
    wall_type: np.ndarray | str,
    face_area_m2: np.ndarray | float,
    *,
    ratings: SiteRatings,
    policy: PolicySettings,
) -> np.ndarray:
    """Return what it costs to replace a wall of a known type, including GST.

    A tilted or failed wall is replaced rather than repaired: partial repair is
    about 1% of cases and is not modelled, so this is the only wall cost the
    study produces.

    Args:
        wall_type: The construction type, scalar or array.
        face_area_m2: Area of wall face, from :func:`wall_face_area_m2`.
        ratings: How hard the site is to work on.
        policy: The settings this scenario runs under, which carry the rate the
            GST-exclusive figures are grossed up at.

    Returns:
        The repair cost in GST-inclusive dollars. It excludes enabling works
        and the compliance items, neither of which the rates carry.

    Raises:
        ValueError: If the area is negative or not finite, or if the wall type
            or any rating is not one the costing tool carries.
    """
    return _wall_cost_incl_gst_nzd(
        wall_rate_excl_gst_nzd_per_m2(wall_type),
        face_area_m2,
        site_multiplier=ratings.multiplier,
        spec_uplift=policy.replacement_spec_uplift,
        policy=policy,
    )


def wall_udv_incl_gst_nzd(
    wall_type: np.ndarray | str,
    face_area_m2: np.ndarray | float,
    *,
    policy: PolicySettings,
) -> np.ndarray:
    """Return a wall's undepreciated value, including GST.

    What the same wall would have cost to build new, on the **same square metre
    rate** the repair cost uses. The costing tool works this way, so the whole
    of the difference between the two numbers is the site allowance: access,
    earthworks and constructability are what it costs to work on this
    particular site, not part of what the wall cost to build.

    Two consequences worth holding on to. For a wall rebuilt in kind, repair
    cost can never come out below UDV, because the multiplier is never
    negative. A wall rebuilt as timber pole (T-122,
    :func:`replacement_rate_excl_gst_nzd_per_m2`) can: a brick or concrete wall
    is valued at its own dearer rate and repaired at the timber one. And **no
    age or condition enters**: undepreciated means no deduction for age, so a
    twenty-year-old wall and a new one of the same construction and size have
    the same value.

    The scope is the **whole insured wall** even where only part of it failed.
    `vul` emits a binary replace per wall, so that holds by construction today,
    but a partial damage state must not follow UDV down.

    Pricing the replacement at the failed wall's specification is a known
    limitation (**L-34**): walls are often rebuilt to a more substantial
    current standard, which would want a higher rate on the repair side than on
    this one.

    Args:
        wall_type: The construction type, scalar or array.
        face_area_m2: Area of wall face, from :func:`wall_face_area_m2`.
        policy: The settings this scenario runs under, which carry the rate the
            GST-exclusive figures are grossed up at.

    Returns:
        The undepreciated value in GST-inclusive dollars, ready for
        :class:`landloss.loss.settlement.DamagedClaim`.

    Raises:
        ValueError: If the area is negative or not finite, or the wall type is
            not one the costing tool carries.
    """
    return _wall_cost_incl_gst_nzd(
        wall_rate_excl_gst_nzd_per_m2(wall_type),
        face_area_m2,
        site_multiplier=0.0,
        policy=policy,
    )


def beta_wall_repair_cost_incl_gst_nzd(
    face_area_m2: np.ndarray | float,
    *,
    ratings: SiteRatings,
    rate_excl_gst_nzd_per_m2: np.ndarray | float,
    policy: PolicySettings,
) -> np.ndarray:
    """Return what it costs to replace a wall of unknown type, including GST.

    The rate is passed in rather than a construction type. A failed wall takes
    :func:`replacement_rate_excl_gst_nzd_per_m2` on its type and replacement
    height; a wall invented for a landslide has no type of its own and takes
    :func:`timber_pole_rate_excl_gst_nzd_per_m2` on its height.

    Args:
        face_area_m2: Area of wall face, from :func:`wall_face_area_m2`.
        ratings: How hard the site is to work on.
        rate_excl_gst_nzd_per_m2: The square metre rate, excluding GST.
        policy: The settings this scenario runs under.

    Returns:
        The repair cost in GST-inclusive dollars, on the same exclusions as
        :func:`wall_repair_cost_incl_gst_nzd`.

    Raises:
        ValueError: If the area is negative or not finite, or any rating is not
            one the costing tool carries.
    """
    return _wall_cost_incl_gst_nzd(
        rate_excl_gst_nzd_per_m2,
        face_area_m2,
        site_multiplier=ratings.multiplier,
        spec_uplift=policy.replacement_spec_uplift,
        policy=policy,
    )


def beta_wall_udv_incl_gst_nzd(
    face_area_m2: np.ndarray | float,
    *,
    rate_excl_gst_nzd_per_m2: np.ndarray | float,
    policy: PolicySettings,
) -> np.ndarray:
    """Return the undepreciated value of a wall of unknown type, including GST.

    :func:`wall_udv_incl_gst_nzd` on a rate passed in, for the same reason
    :func:`beta_wall_repair_cost_incl_gst_nzd` takes one.

    Args:
        face_area_m2: Area of wall face, from :func:`beta_wall_face_area_m2`.
        rate_excl_gst_nzd_per_m2: The square metre rate, excluding GST. Pass
            :func:`wall_type_rate_excl_gst_nzd_per_m2` so a wall is valued at
            the rate its repair is priced at.
        policy: The settings this scenario runs under.

    Returns:
        The undepreciated value in GST-inclusive dollars.

    Raises:
        ValueError: If the area is negative or not finite.
    """
    return _wall_cost_incl_gst_nzd(
        rate_excl_gst_nzd_per_m2,
        face_area_m2,
        site_multiplier=0.0,
        policy=policy,
    )
