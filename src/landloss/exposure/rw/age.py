"""The construction age of a property's retaining walls, inferred from its titles.

The wall model sets a wall's initial condition partly from when it was built
(:mod:`landloss.exposure.rw.wall_probability`), and the study area holds no
record of that. This module estimates it for every claim property, in the four
bins set out in ``assets/choice-of-rwt-bin-ages.md`` beside this package, from
the open, property-level dates there are: the date each Record of Title was
issued (LINZ NZ Property Titles List), and the date of the survey plan the lot
was created on, read from the plan's number.

Three proxies are stacked, and each is a source of error:

- **The wall is as old as the dwelling.** The first wall on a lot is usually
  built with the house, but walls are rebuilt, so this is the oldest the walls
  are likely to be.
- **The dwelling is as old as the land's title or plan.** On a new subdivision
  both come shortly before the house. Infill gives an old house a young title
  and plan, and a house rebuilt on an old section, or a section that stood
  empty, gives a young house an old one.
- **A title issued on paper may be a reissue.** Before the electronic register
  (about 2002), a new certificate of title was often issued on a later dealing
  with the land, so an old house can sit on a title decades younger than it.
  The deposited plan (DP) the lot is on is not reissued, so it dates the lot.

The rules, applied in order by :func:`infer_claim_ages`:

1. A unit title takes its title's date, because the unit plan is created when
   the block is built.
2. Any other title, a cross-lease included, takes the date of its DP where it
   is a paper title more than :data:`REISSUE_MIN_GAP_YEARS` younger than the
   DP, and its own date otherwise. A cross-lease is created when a second flat
   is added, but the claim property is the whole lot, and its oldest building
   is usually the house that was there first.
3. Lot 1 of a plan of no more than :data:`INFILL_MAX_LOTS` lots, dated more
   than :data:`INFILL_MIN_GAP_YEARS` younger than its neighbours, takes their
   median date: an infill plan is usually drawn with the existing house on
   Lot 1, and the new section behind it.
4. A property with neither a dated title nor a dated plan takes its
   neighbours' median date.

Each rule and its numbers were set against Christchurch, the one city with an
open District Valuation Roll giving building age by decade; the comparison is
``src/scripts/landloss/exposure/rw/validations/table_rwt_age_christchurch.py``
and its findings are written beside it.
"""

import re
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.optimize import isotonic_regression
from scipy.spatial import cKDTree

# The four bins, oldest first, as named in choice-of-rwt-bin-ages.md and as the
# columns of the per-suburb table carry them (``p_<bin>``).
AGE_BINS = ("pre_1970", "1970_1991", "1992_2004", "2005_on")

# The decimal year each bin after the first opens: 1 January 1970, 1 July 1992
# (the Building Code in force under the Building Act 1991) and 1 January 2005
# (the first full year of NZS 1170.5:2004 and the Building Act 2004).
BIN_START_YEARS = (1970.0, 1992.5, 2005.0)

# The columns read off the NZ Property Boundaries layer and the NZ Property
# Titles List.
TITLE_NO_COLUMN = "title_no"
TITLE_TYPE_COLUMN = "title_type"
LEGAL_DESCRIPTION_COLUMN = "legal_description"
ISSUE_DATE_COLUMN = "issue_date"
LAND_DISTRICT_COLUMN = "land_district"

# The columns this module writes.
ISSUE_YEAR_COLUMN = "issue_year"
DP_COLUMN = "dp"
FIRST_TITLE_COLUMN = "first_title_no"
TITLE_YEAR_COLUMN = "title_year"
TITLE_COUNT_COLUMN = "title_count"
DP_YEAR_COLUMN = "dp_year"
NEIGHBOURHOOD_YEAR_COLUMN = "neighbourhood_year"
EST_YEAR_COLUMN = "est_year"
AGE_BIN_COLUMN = "age_bin"
AGE_BASIS_COLUMN = "age_basis"

# The rule that set each property's year, one per rule in the module docstring
# in the same order; the first two are both rule 1 or 2 with its outcome.
AGE_BASES = ("title", "dp", "infill_lot_1", "neighbourhood")
TITLE, DP, INFILL_LOT_1, NEIGHBOURHOOD = AGE_BASES

# The title types dated by their own title (rule 1). These are the values of
# the boundaries layer's title_type, not of the titles list's type. Over
# Christchurch, dating cross-leases by their own title as well scored worse:
# 0.732 of the bin against 0.747.
TITLE_DATED_TYPES = ("Unit",)

# How much younger than its DP a paper title has to be before it is read as a
# reissue (rule 2). Over Christchurch, 0 to 5 years score alike and 10 a little
# worse; 5 keeps a title issued in the years just after its plan was deposited,
# which is the normal lag, on its own date.
REISSUE_MIN_GAP_YEARS = 5.0

# The infill rule (rule 3): the most lots the plan can hold, how much younger
# than its neighbours Lot 1 has to be, and how many neighbours are asked. Over
# Christchurch, Lot 1 of a two-lot plan dated 25 years or more younger than
# its neighbours kept an older house over half the time, and Lot 2 about a
# quarter of the time; three- and four-lot plans scored worse, and 35 years
# gave the bin shares closest to the roll's.
INFILL_MAX_LOTS = 2
INFILL_MIN_GAP_YEARS = 35.0
NEIGHBOURS = 10

# How the DP number is read as a date. DP numbers rise with time within a land
# district (and nationally since about 2001), and no title on a lot can be
# issued before its plan, so the plan's date is near the earliest title issued
# on it. Reissues push most titles later, so a low quantile of the earliest
# titles over a run of neighbouring plan numbers is taken, then forced to rise
# with the number.
DP_FIT_WINDOW = 15
DP_FIT_QUANTILE = 0.25

# The days in a year, for turning a date into a decimal year.
DAYS_PER_YEAR = 365.25

# A deposited plan in a legal description, "Lot 2 DP 9789", and a legal
# description that is one whole lot on one plan and nothing else.
DP_PATTERN = r"\bDP\s*(\d+)"
SINGLE_LOT_PATTERN = r"^\s*Lot\s+(\d+)\s+DP\s*(\d+)\s*$"


def decimal_year(dates: pd.Series) -> pd.Series:
    """Return each date as a decimal year, 1 July 1992 being about 1992.5.

    Args:
        dates: Dates, or text a date parser reads; anything unreadable becomes
            null rather than raising.

    Returns:
        The decimal years, as floats, null where the date was missing.
    """
    parsed = pd.to_datetime(pd.Series(dates), errors="coerce", utc=True)
    return (parsed.dt.year + (parsed.dt.dayofyear - 1) / DAYS_PER_YEAR).astype(float)


def age_bin(years: pd.Series | np.ndarray) -> pd.Categorical:
    """Put each decimal year in its age bin.

    A year exactly on a bin's start belongs to that bin, so 1992.5 is
    ``1992_2004``.

    Args:
        years: Decimal years; null stays null.

    Returns:
        The bins, as a categorical over :data:`AGE_BINS` in age order.
    """
    values = np.asarray(years, dtype=float)
    index = np.searchsorted(BIN_START_YEARS, values, side="right")
    labels = np.array(AGE_BINS, dtype=object)[np.clip(index, 0, len(AGE_BINS) - 1)]
    labels[np.isnan(values)] = None
    return pd.Categorical(labels, categories=AGE_BINS, ordered=True)


def bin_shares_of_span(start: float, end: float) -> np.ndarray:
    """Return the share of a span of years falling in each bin.

    A source that dates a building only to a decade cannot say which side of
    the July 1992 or January 2005 break it falls. Spreading the decade over the
    bins in proportion to its years is the even-handed reading: the 1990s are a
    quarter ``1970_1991`` and three quarters ``1992_2004``.

    Args:
        start: The first decimal year of the span.
        end: The decimal year the span ends, exclusive.

    Returns:
        One share per bin in :data:`AGE_BINS` order, summing to one.

    Raises:
        ValueError: If the span is empty.
    """
    if not end > start:
        msg = f"the span must end after it starts: got {start} to {end}"
        raise ValueError(msg)
    edges = np.array([-np.inf, *BIN_START_YEARS, np.inf])
    overlap = np.clip(
        np.minimum(edges[1:], end) - np.maximum(edges[:-1], start), 0, None
    )
    return overlap / (end - start)


def split_title_numbers(
    frame: pd.DataFrame, id_column: str, title_column: str = TITLE_NO_COLUMN
) -> pd.DataFrame:
    """Return one row per title of each property.

    The NZ Property Boundaries layer carries every title a property is held on
    as one comma-separated text field, ``"WN10B/1141, WN446/40"``.

    Args:
        frame: The properties, carrying ``id_column`` and ``title_column``.
        id_column: The property identifier.
        title_column: The comma-separated titles.

    Returns:
        ``id_column`` and ``title_column``, one row per property and title.
        A property with no title is absent.
    """
    titles = frame[[id_column, title_column]].dropna(subset=[title_column])
    titles = titles.assign(
        **{title_column: titles[title_column].str.split(",")}
    ).explode(title_column)
    titles[title_column] = titles[title_column].str.strip()
    titles = titles[titles[title_column] != ""]
    return titles.drop_duplicates().reset_index(drop=True)


def is_paper_title(title_no: pd.Series) -> pd.Series:
    """Return whether each title is a volume and folio reference from the paper era.

    A paper certificate of title carried its register volume and folio,
    ``WN471/294``; a title first issued on the electronic register carries a
    plain number, ``1244058``. Converted paper titles kept their reference.

    Args:
        title_no: Title references.

    Returns:
        True for a volume and folio reference; False otherwise, null included.
    """
    return title_no.str.contains("/", regex=False, na=False)


def title_issue_years(titles: pd.DataFrame) -> pd.DataFrame:
    """Return the issue year and land district of every title.

    Args:
        titles: The NZ Property Titles List, carrying ``title_no``,
            ``issue_date`` and ``land_district``.

    Returns:
        Indexed by ``title_no``, carrying :data:`ISSUE_YEAR_COLUMN` and
        :data:`LAND_DISTRICT_COLUMN`. A title listed twice keeps its first row.
    """
    issued = titles[[TITLE_NO_COLUMN, LAND_DISTRICT_COLUMN]].assign(
        **{ISSUE_YEAR_COLUMN: decimal_year(titles[ISSUE_DATE_COLUMN]).to_numpy()}
    )
    return issued.drop_duplicates(subset=TITLE_NO_COLUMN).set_index(TITLE_NO_COLUMN)


def dp_numbers(legal_descriptions: pd.Series) -> pd.Series:
    """Return the deposited plan numbers each legal description names.

    Args:
        legal_descriptions: Legal descriptions, ``"Lot 4 DP 9789, Part Lot 1
            DP 9535"``.

    Returns:
        A sorted list of distinct plan numbers per description, empty where it
        names none (a Crown section, say, or a plan of another series).
    """
    found = legal_descriptions.fillna("").str.findall(DP_PATTERN, flags=re.IGNORECASE)
    return found.map(lambda numbers: sorted({int(number) for number in numbers}))


def single_lots(legal_descriptions: pd.Series) -> pd.DataFrame:
    """Return the lot and plan of each legal description that is one whole lot.

    Args:
        legal_descriptions: Legal descriptions.

    Returns:
        ``lot`` and ``dp`` per description, null where it is anything other
        than one whole ``Lot <n> DP <m>``.
    """
    parts = legal_descriptions.fillna("").str.extract(
        SINGLE_LOT_PATTERN, flags=re.IGNORECASE
    )
    return pd.DataFrame(
        {
            "lot": pd.to_numeric(parts[0]).to_numpy(),
            DP_COLUMN: pd.to_numeric(parts[1]).to_numpy(),
        },
        index=legal_descriptions.index,
    )


def fit_dp_years(boundaries: pd.DataFrame, issued: pd.DataFrame) -> pd.DataFrame:
    """Fit the date of each deposited plan from the titles issued on it.

    Only boundary rows held on exactly one title over exactly one plan are
    read, so that a title is never credited to a plan it does not stand on. The
    earliest title on each plan is a bound on the plan's date from above; the
    fit takes a low quantile of those bounds over neighbouring plan numbers and
    forces it to rise with the number, separately per land district, since
    each district numbered its own plans until about 2001.

    Args:
        boundaries: Property boundary rows, carrying ``title_no`` and
            ``legal_description``.
        issued: The title issue years, from :func:`title_issue_years`.

    Returns:
        One row per plan read, carrying :data:`LAND_DISTRICT_COLUMN`,
        :data:`DP_COLUMN` and :data:`DP_YEAR_COLUMN`, sorted by district and
        plan number.
    """
    rows = boundaries[[TITLE_NO_COLUMN, LEGAL_DESCRIPTION_COLUMN]].copy()
    rows[TITLE_NO_COLUMN] = rows[TITLE_NO_COLUMN].str.strip()
    plans = dp_numbers(rows[LEGAL_DESCRIPTION_COLUMN])
    one = ~rows[TITLE_NO_COLUMN].str.contains(",", na=True) & plans.map(len).eq(1)
    rows = rows[one].assign(**{DP_COLUMN: plans[one].str[0]})
    rows = rows.join(issued, on=TITLE_NO_COLUMN, how="inner").dropna(
        subset=[ISSUE_YEAR_COLUMN, LAND_DISTRICT_COLUMN]
    )

    earliest = (
        rows.groupby([LAND_DISTRICT_COLUMN, DP_COLUMN])[ISSUE_YEAR_COLUMN]
        .min()
        .reset_index()
        .sort_values([LAND_DISTRICT_COLUMN, DP_COLUMN])
    )
    fitted = []
    for _, plans_in_district in earliest.groupby(LAND_DISTRICT_COLUMN, sort=True):
        low = (
            plans_in_district[ISSUE_YEAR_COLUMN]
            .rolling(DP_FIT_WINDOW, center=True, min_periods=1)
            .quantile(DP_FIT_QUANTILE)
        )
        rising = isotonic_regression(low.to_numpy()).x
        fitted.append(plans_in_district.assign(**{DP_YEAR_COLUMN: rising}))
    if not fitted:
        return pd.DataFrame(columns=[LAND_DISTRICT_COLUMN, DP_COLUMN, DP_YEAR_COLUMN])
    return pd.concat(fitted, ignore_index=True)[
        [LAND_DISTRICT_COLUMN, DP_COLUMN, DP_YEAR_COLUMN]
    ]


def dp_years(
    land_districts: pd.Series, plans: pd.Series, fit: pd.DataFrame
) -> pd.Series:
    """Read the date of each plan off the fit for its land district.

    A plan number between two fitted plans is interpolated, and one beyond the
    fitted range takes the nearest end.

    Args:
        land_districts: The land district of each plan.
        plans: The plan numbers; null for a property on no plan.
        fit: The plan dates, from :func:`fit_dp_years`.

    Returns:
        The decimal year of each plan, null where the plan or its district has
        no fit.
    """
    years = pd.Series(np.nan, index=plans.index)
    for district, curve in fit.groupby(LAND_DISTRICT_COLUMN):
        here = land_districts.eq(district) & plans.notna()
        if here.any():
            years[here] = np.interp(
                plans[here].to_numpy(dtype=float),
                curve[DP_COLUMN].to_numpy(dtype=float),
                curve[DP_YEAR_COLUMN].to_numpy(dtype=float),
            )
    return years


def footprint_rows(
    boundaries: gpd.GeoDataFrame,
    claims: gpd.GeoDataFrame,
    id_column: str,
    columns: list[str],
) -> pd.DataFrame:
    """Return every boundary row standing on each claim's footprint.

    A claim property is one footprint, with the boundaries stacked on it
    dissolved into one row
    (:func:`landloss.exposure.land.extent.build_claim_properties`). The titles,
    and the rating units, of a cross-leased or unit-titled lot are spread over
    the rows dissolved away, so they are recovered here by matching the
    geometry exactly, as the dissolve did.

    Args:
        boundaries: The property boundaries the claims were built from.
        claims: The claim properties, carrying ``id_column``.
        id_column: The claim identifier.
        columns: The boundary columns to carry.

    Returns:
        ``id_column`` and ``columns``, one row per claim and boundary row on its
        footprint.
    """
    on_footprint = pd.DataFrame(
        {
            "_footprint": boundaries.geometry.to_wkb(),
            **{c: boundaries[c] for c in columns},
        }
    )
    keys = pd.DataFrame(
        {
            id_column: claims[id_column].to_numpy(),
            "_footprint": claims.geometry.to_wkb(),
        }
    )
    return keys.merge(on_footprint, on="_footprint", how="inner").drop(
        columns="_footprint"
    )


def claim_title_dates(
    claim_titles: pd.DataFrame, issued: pd.DataFrame, id_column: str
) -> pd.DataFrame:
    """Date each claim from the earliest of its titles.

    The earliest is taken, rather than the latest, because a property held on
    several titles has usually had one added to it; over Christchurch it scores
    better.

    Args:
        claim_titles: One row per claim and title, from
            :func:`split_title_numbers`.
        issued: The title issue years, from :func:`title_issue_years`.
        id_column: The claim identifier.

    Returns:
        Indexed by ``id_column``: :data:`FIRST_TITLE_COLUMN`,
        :data:`TITLE_YEAR_COLUMN`, :data:`LAND_DISTRICT_COLUMN` and
        :data:`TITLE_COUNT_COLUMN`. A claim none of whose titles is listed is
        absent.
    """
    dated = claim_titles.join(issued, on=TITLE_NO_COLUMN, how="inner").dropna(
        subset=[ISSUE_YEAR_COLUMN]
    )
    counts = dated.groupby(id_column).size().rename(TITLE_COUNT_COLUMN)
    first = (
        dated.sort_values([id_column, ISSUE_YEAR_COLUMN], kind="stable")
        .drop_duplicates(subset=id_column, keep="first")
        .set_index(id_column)
        .rename(
            columns={
                TITLE_NO_COLUMN: FIRST_TITLE_COLUMN,
                ISSUE_YEAR_COLUMN: TITLE_YEAR_COLUMN,
            }
        )
    )
    return first[[FIRST_TITLE_COLUMN, TITLE_YEAR_COLUMN, LAND_DISTRICT_COLUMN]].join(
        counts
    )


def claim_suburbs(
    claim_addresses: pd.DataFrame,
    addresses: pd.DataFrame,
    id_column: str,
    columns: tuple[str, ...] = ("territorial_authority", "suburb_locality"),
) -> pd.DataFrame:
    """Return the suburb most of each claim's addresses stand in.

    A property is reported in one suburb even where its addresses straddle a
    boundary. A tie goes to the first suburb in alphabetical order, so the
    answer does not depend on row order.

    Args:
        claim_addresses: One row per address and the claim it stands in, as
            :func:`landloss.exposure.land.extent.count_dwellings` returns.
        addresses: The address points, carrying ``address_id`` and
            ``columns``.
        id_column: The claim identifier.
        columns: The address columns that name the suburb.

    Returns:
        Indexed by ``id_column``, carrying ``columns``.
    """
    named = claim_addresses[[id_column, "address_id"]].merge(
        pd.DataFrame(addresses)[["address_id", *columns]], on="address_id"
    )
    counts = named.groupby([id_column, *columns], dropna=False).size().rename("n")
    ranked = counts.reset_index().sort_values(
        [id_column, "n", *columns], ascending=[True, False, *[True] * len(columns)]
    )
    return ranked.drop_duplicates(subset=id_column).set_index(id_column)[list(columns)]


def bin_shares(ages: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Return the share of properties in each age bin, per group.

    Args:
        ages: One row per property, carrying :data:`AGE_BIN_COLUMN` and ``by``.
        by: The columns to group on, such as the territorial authority and
            suburb.

    Returns:
        One row per group: ``by``, ``properties``, ``undated`` (those with no
        bin, left out of the shares) and one ``p_<bin>`` per bin, which sum to
        one over the dated properties.
    """
    columns = [f"p_{name}" for name in AGE_BINS]
    dated = ages.dropna(subset=[AGE_BIN_COLUMN])
    counts = dated.pivot_table(
        index=by,
        columns=AGE_BIN_COLUMN,
        aggfunc="size",
        fill_value=0,
        observed=False,
        dropna=False,
    ).reindex(columns=list(AGE_BINS), fill_value=0)
    shares = counts.div(counts.sum(axis=1).replace(0, np.nan), axis=0)
    shares.columns = columns
    totals = ages.groupby(by, dropna=False).agg(
        properties=(AGE_BIN_COLUMN, "size"),
        undated=(AGE_BIN_COLUMN, lambda bins: int(bins.isna().sum())),
    )
    table = totals.join(shares, how="left").reset_index()
    return table[table["properties"] > table["undated"]].reset_index(drop=True)


def neighbourhood_years(
    points: gpd.GeoSeries, years: pd.Series, neighbours: int = NEIGHBOURS
) -> pd.Series:
    """Return the median year of each property's nearest neighbours.

    Args:
        points: A point per property, in a projected coordinate system.
        years: Each property's year; a null neighbour is skipped.
        neighbours: How many nearest other properties to ask.

    Returns:
        The median, null where every neighbour is null or there are none.
    """
    if len(points) < 2:
        return pd.Series(np.nan, index=years.index)
    xy = np.column_stack([points.x.to_numpy(), points.y.to_numpy()])
    k = min(neighbours + 1, len(points))
    _, nearest = cKDTree(xy).query(xy, k=k)
    values = years.to_numpy(dtype=float)[nearest[:, 1:]]
    # A property whose neighbours are all undated has no median; that is the
    # answer, not a fault, so numpy's warning about it is not shown.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        medians = np.nanmedian(values, axis=1)
    return pd.Series(medians, index=years.index)


def infer_claim_ages(
    claims: gpd.GeoDataFrame,
    boundaries: gpd.GeoDataFrame,
    titles: pd.DataFrame,
    *,
    id_column: str,
    title_dated_types: tuple[str, ...] = TITLE_DATED_TYPES,
    reissue_min_gap_years: float = REISSUE_MIN_GAP_YEARS,
    infill_max_lots: int = INFILL_MAX_LOTS,
    infill_min_gap_years: float = INFILL_MIN_GAP_YEARS,
) -> pd.DataFrame:
    """Estimate when each claim property's walls were built, and bin it.

    Applies the four rules of the module docstring in order, recording which
    one set each year. The rule settings default to this module's constants and
    are arguments only so that a validation can switch a rule off: an infinite
    ``reissue_min_gap_years`` turns off rule 2, and an ``infill_max_lots`` of 0
    turns off rule 3.

    Args:
        claims: The claim properties, carrying ``id_column``,
            :data:`TITLE_TYPE_COLUMN` and :data:`LEGAL_DESCRIPTION_COLUMN`, in a
            projected coordinate system.
        boundaries: The property boundaries the claims were built from, which
            carry every title on a footprint and fit the plan dates.
        titles: The NZ Property Titles List.
        id_column: The claim identifier.
        title_dated_types: The title types rule 1 dates by their own title.
        reissue_min_gap_years: How much younger than its plan a paper title has
            to be for rule 2 to read it as a reissue.
        infill_max_lots: The most lots an infill plan holds under rule 3.
        infill_min_gap_years: How much younger than its neighbours Lot 1 has to
            be under rule 3.

    Returns:
        One row per claim, in the claims' order: ``id_column``,
        :data:`FIRST_TITLE_COLUMN`, :data:`TITLE_YEAR_COLUMN`,
        :data:`TITLE_COUNT_COLUMN`, :data:`DP_YEAR_COLUMN`,
        :data:`NEIGHBOURHOOD_YEAR_COLUMN`, :data:`EST_YEAR_COLUMN`,
        :data:`AGE_BIN_COLUMN` and :data:`AGE_BASIS_COLUMN`. The year and bin
        are null only where no neighbour is dated either.
    """
    issued = title_issue_years(titles)
    fit = fit_dp_years(boundaries, issued)

    on_footprint = footprint_rows(boundaries, claims, id_column, [TITLE_NO_COLUMN])
    dates = claim_title_dates(
        split_title_numbers(on_footprint, id_column), issued, id_column
    )
    ages = claims[[id_column]].join(dates, on=id_column).reset_index(drop=True)
    legal = claims[LEGAL_DESCRIPTION_COLUMN].reset_index(drop=True)
    title_type = claims[TITLE_TYPE_COLUMN].reset_index(drop=True)

    plans = dp_numbers(legal)
    oldest_plan = plans.map(lambda numbers: numbers[0] if numbers else np.nan)
    ages[DP_YEAR_COLUMN] = dp_years(ages[LAND_DISTRICT_COLUMN], oldest_plan, fit)

    # Rules 1 and 2: the title's own date, or its plan's where a paper title
    # is a reissue.
    title_year = ages[TITLE_YEAR_COLUMN]
    reissued = (
        ~title_type.isin(title_dated_types)
        & is_paper_title(ages[FIRST_TITLE_COLUMN])
        & (title_year - ages[DP_YEAR_COLUMN] > reissue_min_gap_years)
    )
    undated_title = title_year.isna() & ages[DP_YEAR_COLUMN].notna()
    use_plan = reissued | undated_title
    estimate = title_year.where(~use_plan, ages[DP_YEAR_COLUMN])
    basis = pd.Series(np.where(use_plan, DP, TITLE), dtype=object)

    # Rule 3: Lot 1 of a small infill plan keeps the neighbourhood's date.
    points = claims.geometry.representative_point().reset_index(drop=True)
    neighbourhood = neighbourhood_years(points, estimate)
    ages[NEIGHBOURHOOD_YEAR_COLUMN] = neighbourhood
    lots = single_lots(legal)
    lots_on_plan = plans.explode().dropna().astype(int).value_counts()
    plan_lots = lots[DP_COLUMN].map(lots_on_plan)
    infill = (
        ~title_type.isin(title_dated_types)
        & lots["lot"].eq(1)
        & plan_lots.le(infill_max_lots)
        & (estimate - neighbourhood > infill_min_gap_years)
    )
    estimate = estimate.where(~infill, neighbourhood)
    basis[infill] = INFILL_LOT_1

    # Rule 4: nothing dated on the property, so its neighbours' date.
    undated = estimate.isna() & neighbourhood.notna()
    estimate = estimate.where(~undated, neighbourhood)
    basis[undated] = NEIGHBOURHOOD
    basis[estimate.isna()] = None

    ages[EST_YEAR_COLUMN] = estimate
    ages[AGE_BIN_COLUMN] = age_bin(estimate)
    ages[AGE_BASIS_COLUMN] = pd.Categorical(basis, categories=AGE_BASES)
    return ages[
        [
            id_column,
            FIRST_TITLE_COLUMN,
            TITLE_YEAR_COLUMN,
            TITLE_COUNT_COLUMN,
            DP_YEAR_COLUMN,
            NEIGHBOURHOOD_YEAR_COLUMN,
            EST_YEAR_COLUMN,
            AGE_BIN_COLUMN,
            AGE_BASIS_COLUMN,
        ]
    ]
