r"""Build the Canterbury observed land damage database.

Joins NHC's Canterbury earthquake sequence loss records to the National
Liquefaction Model's mapped land damage observations, giving one row per insured
property per event carrying the land damage settled and the land damage state,
1 to 6, surveyed on the ground.

    uv run --frozen python src/scripts/landloss/vul/liquefaction/land/steps/s1_ces_observed_damage/gen_observed_damage_db.py

Requires ``TNT_KOORDINATES_API_KEY`` in ``.env`` for the flatland layer the mask
is cut from.

The properties are masked to
``landloss.exposure.land.landform.CHCH_FLAT_ONLY`` -- the flat land inside the
Christchurch extent, as the National Liquefaction Model draws it -- so what is
in the database is decided by an extent that is written down rather than by how
far some other model's grid happened to reach. The Canterbury sequence is a flat
land liquefaction dataset (limitation L-09), and the mask is what makes that
explicit instead of incidental.

This is the only New Zealand dataset holding both settled land claims and mapped
land damage, so it is what the Wellington land damage relationships are
calibrated against.

Run ``gen_ces_loss_data.py`` in ``../../static_data_gen`` first; this step reads
the GeoPackage that script writes rather than the source CSV.

The loss GeoPackage is fetched from T:'s SourceMaterial via
``tdrive_sync.get_source_mat``, which caches it locally. The National
Liquefaction Model release paths and the output are not CLI-configurable --
there is nothing to point elsewhere at, so this just runs.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import is_empty, is_missing

import tdrive_sync as ts
from landloss.domain import constants
from landloss.exposure.land.landform import CHCH_FLAT_ONLY
from landloss.io import versioned_store

# The loss data NHC supplied, geocoded by ../../static_data_gen/gen_ces_loss_data.py,
# fetched from T:'s SourceMaterial via tdrive_sync.get_source_mat (see main()).
LOSS_MAT_PATH = "CHC-loss-data-from-NHC/ces_loss_data_with_geometry.gpkg"

# The National Liquefaction Model's versioned core releases. The observations are
# read at constants.CORE_NLM_VERSION, the one release this study pins the NLM at.
# If a release ever ships without the buffered observations -- they are survey
# data that does not change when the model is re-run, so they are not necessarily
# carried forward -- name the release that has them here, as a member of
# constants.NlmRelease, rather than reintroducing a second project-wide pin.
NLM_CORE_DIR = Path(
    r"T:\Auckland\Projects\1017473\WorkingMaterial\new_versioned_releases\core"
)
OBS_DIR = (
    NLM_CORE_DIR
    / constants.CORE_NLM_VERSION
    / "fragility"
    / "event_obs_buffered_no_map"
)

# Where the database is written: this project's own versioned data store
# (see landloss.io.versioned_store), not a hardcoded T: path. Derived data,
# and large, so it lives with the project's working material rather than in
# the repository.
OUT_SUB_DIRS = ["ces_observed_damage"]
OUT_NAME = "observed_damage_db.parquet"

# The NHC loss columns, Title Case in the source, mapped to snake_case. Taken
# from COLUMN_MAPPINGS in the National Liquefaction Model loss repository so the
# two studies name the same field the same way.
COLUMN_MAPPINGS = {
    "Event Name": "event_name",
    "Event Date": "event_date",
    "Loss Date": "loss_date",
    "qpid": "qpid",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "BuildingExposure": "building_exposure",
    "LandExposure": "land_exposure",
    "BuildingApportionment": "building_apportionment",
    "BuildingAssessment": "building_assessment",
    "LandAssessment": "land_assessment",
    "BuildingPaid": "building_paid",
    "RepairPaid": "repair_paid",
    "LandPaid": "land_paid",
    "BuildingSource": "building_source",
    "LandSource": "land_source",
    "BestBuildingLossEstimateForClaim": "best_building_loss_estimate_for_claim",
}

# Dollar amounts, which arrive as strings carrying "$", thousands separators and
# a bare "-" for nil. Summed when several claims share a property and an event.
MONEY_COLUMNS = (
    "building_assessment",
    "land_assessment",
    "building_paid",
    "repair_paid",
    "land_paid",
    "best_building_loss_estimate_for_claim",
)

# The six land damage states, worst last. The number is the state as the
# observation layers code it in ``dissolve_col``, so it is carried through as the
# state rather than folded into coarser bands: the band can always be recovered
# from the state, but the state cannot be recovered from the band.
DAMAGE_STATES = {
    1: "None observed",
    2: "Minor",
    3: "Moderate",
    4: "Major",
    5: "Severe",
    6: "Very severe",
}

# A polygon the mapping team could not grade. It is deliberately not a state:
# "surveyed, could not tell" and "never surveyed" are different answers, and
# collapsing the first into a null would make them indistinguishable. It sorts
# below every state so a graded observation always wins where the two overlap.
UNKNOWN = "Unknown"
UNKNOWN_RANK = -1

# The observation layers were mapped by several teams over six years and their
# ``dissolve_col`` vocabularies never converged: numeric severity codes for one
# event, damage descriptions for another, liquefaction classes for the third.
# Derived from OBS_HAZ_MAP in the National Liquefaction Model loss repository,
# including its "Unkown" typo key, which is a real value in the source, but
# resolved onto the six states rather than onto that map's five bands.
#
# Two judgements sit in here. "Lateral Spreading" names a mechanism rather than a
# grade, and is read as state 5: it is the damage that wrote Canterbury
# properties off, so it belongs above a graded "Major" without displacing an
# explicit "Very Severe". "Liquefaction" and "Liquefaction Ejecta" likewise name
# what was seen rather than how bad it was, and are read as state 3.
#
# One deliberate difference from the National Liquefaction Model's map: that map
# sends a raw "Minor" to its "None Observed" band while sending the numeric code
# "2" to "Minor", so the same damage is reported differently depending on which
# event mapped it. Here "Minor" is state 2 either way.
OBS_HAZ_MAP = {
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "None Observed": 1,
    "Minor": 2,
    "Moderate": 3,
    "Major": 4,
    "Severe": 5,
    "Very Severe": 6,
    "noliq_cov": 1,
    "No Visible Damage Observed": 1,
    "Observed Water": 1,
    "No Liquefaction": 1,
    "RoadWorks": 1,
    "Liquefaction Ejecta": 3,
    "Liquefaction": 3,
    "Lateral Spreading": 5,
    "Unknown": UNKNOWN_RANK,
    "Unkown": UNKNOWN_RANK,
    "borderline": UNKNOWN_RANK,
}

# Columns the layers are expected to carry, checked before any join so a renamed
# source fails with a readable message rather than deep inside geopandas.
OBS_CATEGORY_COLUMN = "dissolve_col"
OBS_LIQ_COLUMN = "liq_cats"

# The February 2016 observations hold classes beyond liquefaction presence, which
# the National Liquefaction Model excludes. Kept out for the same reason here:
# the rest describe something other than land damage.
CHCH16_LIQ_CLASSES = frozenset({"Liquefaction", "No Liquefaction"})

# The observation files are named for the event as the mapping teams knew it, and
# the correspondence is not guessable: CESSept is Darfield, CESFeb is February
# 2011, CHCH16 is February 2016.
EVENTS = {
    "darfield": {
        "loss_name": "Christchurch 30km W, 10km, 7.1",
        "obs": "CESSept_buffered.parquet",
        "label": "Darfield, September 2010",
    },
    "chch_feb_2011": {
        "loss_name": "Christchurch 10km SE, 5km, 6.3",
        "obs": "CESFeb_buffered.parquet",
        "label": "Christchurch, February 2011",
    },
    "chch_feb_2016": {
        "loss_name": "Christchurch 15km E, 15km, 5.7",
        "obs": "CHCH16_buffered.parquet",
        "label": "Christchurch, February 2016",
    },
}

OUTPUT_COLUMNS = [
    "qpid",
    "simple_event_name",
    "observed_land_damage_state",
    "observed_land_damage_category",
    "land_assessment",
    "land_paid",
    "building_assessment",
    "building_paid",
    "repair_paid",
    "best_building_loss_estimate_for_claim",
    "n_claims",
    "geometry",
]

RULE = "-" * 72


def require_columns(frame, columns, source):
    """Fail early, and by name, when a source layer is not what was expected.

    Args:
        frame: The layer just read.
        columns: The column names the rest of the script relies on.
        source: What to call the layer in the error message.

    Raises:
        ValueError: If any of the columns is absent.
    """
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        msg = (
            f"{source} is missing {', '.join(missing)}. "
            f"It carries: {', '.join(str(column) for column in frame.columns)}"
        )
        raise ValueError(msg)


def to_money(values):
    """Turn the source's dollar strings into floats.

    The amounts come through as text carrying a currency symbol, thousands
    separators and a bare "-" where the amount is nil. Values already numeric --
    which is what a GeoPackage round trip can give back -- are passed through.

    Args:
        values: One dollar column.

    Returns:
        The same column as floats, with nil and blank as NaN.
    """
    if pd.api.types.is_numeric_dtype(values):
        return values.astype("float64")

    cleaned = values.astype("string").str.replace(r"[$,]", "", regex=True).str.strip()
    # A lone "-" means nil, but a leading minus on a number is a real credit, so
    # only the bare dash is blanked.
    cleaned = cleaned.replace({"-": None, "": None})
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def get_losses(path):
    """Read the geocoded loss records and reduce them to one row per property-event.

    Args:
        path: The GeoPackage written by ``gen_ces_loss_data.py``.

    Returns:
        One row per ``(qpid, simple_event_name)``, dollar columns summed, with an
        ``n_claims`` count of how many records went into each.
    """
    losses = gpd.read_file(path)
    print(f"Read {len(losses):,} loss records from {path.name}")

    # Some headers in the source CSV carry stray whitespace, which survives into
    # the GeoPackage.
    losses.columns = [str(column).strip() for column in losses.columns]
    require_columns(losses, ["Event Name", "qpid"], str(path))
    losses = losses.rename(columns=COLUMN_MAPPINGS)

    event_names = {event["loss_name"]: name for name, event in EVENTS.items()}
    losses["simple_event_name"] = losses["event_name"].map(event_names)
    unmatched = int(losses["simple_event_name"].isna().sum())
    losses = losses.loc[losses["simple_event_name"].notna()]
    print(f"  dropped {unmatched:,} records outside the three modelled events")

    for column in MONEY_COLUMNS:
        if column in losses.columns:
            losses[column] = to_money(losses[column])

    # A QPID is NHC's property identifier. Null and non-positive values are
    # placeholders rather than properties, and cannot be aggregated on.
    qpid = pd.to_numeric(losses["qpid"], errors="coerce")
    valid_qpid = qpid.notna() & qpid.gt(0)
    print(f"  dropped {int((~valid_qpid).sum()):,} records with no usable QPID")
    losses = losses.loc[valid_qpid]
    losses["qpid"] = qpid.loc[valid_qpid].astype("int64")

    # Tested at the shapely level rather than with GeoSeries.notna, which warns
    # when the series holds empty geometry -- and that is one of the cases being
    # looked for here.
    geometries = losses.geometry.to_numpy()
    located = ~is_missing(geometries) & ~is_empty(geometries)
    print(f"  dropped {int((~located).sum()):,} records with no usable location")
    losses = losses.loc[located]

    # Aggregate before joining, so a property with forty claims is joined once
    # rather than forty times. Its claims all sit at the same point, so taking
    # the first geometry loses nothing.
    money = [column for column in MONEY_COLUMNS if column in losses.columns]
    aggregated = losses.groupby(["qpid", "simple_event_name"], as_index=False).agg(
        **{column: (column, "sum") for column in money},
        n_claims=("qpid", "size"),
        geometry=("geometry", "first"),
    )
    properties = gpd.GeoDataFrame(aggregated, geometry="geometry", crs=losses.crs)
    print(f"  aggregated to {len(properties):,} property-event rows")
    return properties.to_crs(constants.DEFAULT_CRS)


def get_observed_damage(path):
    """Read one event's buffered land damage observations.

    Args:
        path: The buffered observation parquet for the event.

    Returns:
        The observation polygons carrying a single ``damage_rank`` column -- a
        state from :data:`DAMAGE_STATES`, or :data:`UNKNOWN_RANK` -- in NZTM.
    """
    observations = gpd.read_parquet(path)
    require_columns(observations, [OBS_CATEGORY_COLUMN], str(path))

    # February 2016 was mapped as liquefaction presence rather than as damage
    # severity, alongside classes describing something else entirely.
    if OBS_LIQ_COLUMN in observations.columns:
        observations = observations.loc[
            observations[OBS_LIQ_COLUMN].isin(CHCH16_LIQ_CLASSES)
        ]

    ranks = observations[OBS_CATEGORY_COLUMN].astype("string").map(OBS_HAZ_MAP)
    unmapped = sorted(
        set(observations.loc[ranks.isna(), OBS_CATEGORY_COLUMN].dropna().unique())
    )
    if unmapped:
        # Not fatal: an unrecognised class is better reported and left out than
        # silently given a state it was never graded at.
        print(f"  {len(unmapped)} unmapped observation classes: {', '.join(unmapped)}")

    observations = observations.assign(damage_rank=ranks)
    observations = observations.loc[ranks.notna()]
    return observations[["damage_rank", "geometry"]].to_crs(constants.DEFAULT_CRS)


def assign_observed_damage(properties, observations):
    """Attach the observed land damage state to each property.

    Where a property falls inside several observation polygons the worst state
    wins, which on a numeric scale is simply the highest. The alternative --
    keeping whichever match happens to come last, which is what the National
    Liquefaction Model's build does -- reports a property inside both a state 1
    and a lateral spreading polygon as undamaged about half the time.

    Args:
        properties: One row per property-event, points in NZTM.
        observations: Observation polygons carrying ``damage_rank``.

    Returns:
        A copy of ``properties`` with ``observed_land_damage_state`` and
        ``observed_land_damage_category`` added. A property no polygon covered
        is null in both; one covered only by ungraded polygons has a null state
        and a category of :data:`UNKNOWN`.
    """
    matches = gpd.sjoin(
        properties[["geometry"]], observations, how="left", predicate="intersects"
    )
    worst = matches["damage_rank"].groupby(level=0).max().reindex(properties.index)

    # Int64 rather than float, so a state reads as 3 and not 3.0 everywhere
    # downstream, and so a property with no observation stays null rather than
    # becoming NaN in an otherwise integer column.
    states = worst.where(worst != UNKNOWN_RANK).astype("Int64")
    categories = states.map(DAMAGE_STATES).astype("string")
    return properties.assign(
        observed_land_damage_state=states,
        observed_land_damage_category=categories.mask(worst == UNKNOWN_RANK, UNKNOWN),
    )


def mask_to_flat_land(properties):
    """Cut the properties back to the flat land inside the Christchurch extent.

    The mask is :data:`landloss.exposure.land.landform.CHCH_FLAT_ONLY`, the
    National Liquefaction Model flatland layer clipped to the Christchurch
    rectangle. It is what decides the reach of this database: the extent is
    named and written down rather than inherited from whatever other layer the
    step happens to join to.

    Two things follow from the mask that are worth being explicit about. The
    Canterbury sequence is a flat land liquefaction dataset -- limitation L-09 --
    and clipping to flat land says so rather than leaving it as an assertion.
    And the flatland layer is a national-scale generalisation, limitation L-16,
    so a property on a small terrace inside a flat suburb may be kept or dropped
    on a boundary the layer draws coarsely.

    Args:
        properties: One row per property-event, points in NZTM.

    Returns:
        The rows falling on flat land, with their columns intact.
    """
    flat = CHCH_FLAT_ONLY.clip(properties)
    dropped = len(properties) - len(flat)
    share = len(flat) / len(properties) if len(properties) else 0.0
    print(f"  dropped {dropped:,} off {CHCH_FLAT_ONLY.name}, keeping {share:.0%}")
    return flat


def build_observed_damage_db(loss_fp, obs_dir):
    """Join the loss records to the observations, event by event.

    Args:
        loss_fp: The geocoded loss GeoPackage.
        obs_dir: Directory holding the buffered observation parquets.

    Returns:
        One row per property-event, carrying :data:`OUTPUT_COLUMNS`.
    """
    properties = get_losses(loss_fp)
    properties = mask_to_flat_land(properties)

    joined = []
    for name, event in EVENTS.items():
        print(f"\n{event['label']}")
        subset = properties.loc[properties["simple_event_name"] == name].copy()
        print(f"  {len(subset):,} properties with a loss record")
        if subset.empty:
            continue

        observations = get_observed_damage(obs_dir / event["obs"])
        subset = assign_observed_damage(subset, observations)
        matched = int(subset["observed_land_damage_category"].notna().sum())
        share = matched / len(subset)
        print(f"  {matched:,} matched an observation polygon ({share:.0%})")

        joined.append(subset)

    database = pd.concat(joined, ignore_index=True)
    database = gpd.GeoDataFrame(database, geometry="geometry", crs=properties.crs)
    return database[[column for column in OUTPUT_COLUMNS if column in database.columns]]


def describe(database):
    """Print what came out, so the joins can be sanity checked before plotting."""
    print(RULE)
    print(f"{len(database):,} property-event rows")

    print("\nObserved land damage state:")
    counts = database["observed_land_damage_state"].value_counts(dropna=False)
    for state, label in DAMAGE_STATES.items():
        print(f"  {state}  {label:<15} {counts.get(state, 0):>9,}")

    categories = database["observed_land_damage_category"]
    print(f"  -  {UNKNOWN:<15} {int((categories == UNKNOWN).sum()):>9,}")
    print(f"  -  {'No observation':<15} {int(categories.isna().sum()):>9,}")

    print("\nBy event:")
    print(f"  {'Event':<28} {'Rows':>9} {'Observed':>9} {'Land $ sum':>16}")
    for name, event in EVENTS.items():
        subset = database.loc[database["simple_event_name"] == name]
        if subset.empty:
            continue
        observed = int(subset["observed_land_damage_category"].notna().sum())
        print(
            f"  {event['label']:<28} {len(subset):>9,}"
            f" {observed:>9,}"
            f" {subset['land_assessment'].sum():>16,.0f}"
        )


def main():
    loss_fp = ts.get_source_mat(LOSS_MAT_PATH)

    print(f"NLM release  : {constants.CORE_NLM_VERSION}")
    print(f"Mask         : {CHCH_FLAT_ONLY.name}")
    print(RULE)

    database = build_observed_damage_db(loss_fp=loss_fp, obs_dir=OBS_DIR)
    describe(database)

    versioned_store.save_vul(database, fname=OUT_NAME, sub_dirs=OUT_SUB_DIRS)

    print(RULE)
    print(f"Wrote {OUT_NAME} to the vul versioned data store ({OUT_SUB_DIRS[0]})")


if __name__ == "__main__":
    main()
