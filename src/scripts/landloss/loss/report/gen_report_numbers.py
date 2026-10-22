"""Write the numbers the land value appendix quotes.

    TTDRIVE_SYNC_LOCAL_MODE=True uv run --frozen python src/scripts/landloss/loss/report/gen_report_numbers.py

Every number the appendix states comes from here, so each can be traced to the
code or the run it came from rather than typed in. The YAML has five parts:

- ``meta``: when and from which commit it was written, and the extents read.
- ``settings``: the tier ratios, the cap on the outer tier, the common
  valuation date, each council's index to it and the GST rate, read from the
  constants and the committed asset that set them.
- ``sources``: over the four territorial authorities, how many claims take
  their land value from the roll, from their suburb's median, or from the
  run's median, decided as loss step 0 decides it; and how many are on the
  roll only as non-residential units, which step 0 drops and are not counted
  among the claims. Each authority's run covers its bounding
  box, so a claim is counted only in the authority its insured land lies in.
- ``rates``: medians over the claims that take their land value from the roll
  -- the same claims ``sources`` counts as such, so the appendix's counts agree
  -- of the average rate, the three tier rates and the two correction factors,
  overall and per area band, as ``validations/gen_qv_average_rate.py`` computes
  them. That script's own table also holds the properties valued as though off
  the roll (non-residential) and assigns an authority by address rather than by
  insured land, so it is cut to these claims here.
- ``examples``: the valuer's example and the typical section, worked through
  the tiers.

It also lists which of the appendix's figures exist, so the appendix can show a
placeholder rather than fail when one has not been drawn. Written to
``report/loss/qv-land-value/tab/report-numbers.yaml``.

Sensitive:
    The QV rating roll is supplied by QV as sensitive data
    (:mod:`landloss.io.qv_rating_roll`). Only counts, medians and the two
    worked examples are written, never a property's value. Run with
    ``TTDRIVE_SYNC_LOCAL_MODE=True`` to read the roll from the local cache.
"""

import datetime as dt
import sys

import pandas as pd
import yaml

from landloss.domain.gst import GST_RATE
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    LAND_ID_COLUMN,
    LAND_PROPERTY_AREA_COLUMN,
    LAND_SUBURB_COLUMN,
)
from landloss.exposure.land.land_value import COMMON_VALUATION_DATE, load_base_rates
from landloss.io.area_of_interest import get_area_of_interest
from landloss.io.qv_rating_roll import get_qv_rating_roll
from landloss.loss.qv_land_value import (
    FROM_ROLL,
    INSURED_RATIO,
    MAX_UNINSURED_M2,
    UNINSURED_RATIO,
    VALUE_SOURCE_COLUMN,
    claim_land_values,
    non_residential_claims,
    qv_land_value_by_claim,
    residential_land_values,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    valuation_links_path,
)
from scripts.landloss.hazard.liquefaction.report.gen_report_numbers import git_commit
from scripts.landloss.loss.validations import config
from scripts.landloss.loss.validations.gen_qv_average_rate import (
    AREA_BAND_COLUMN,
    FIG_DIR,
    FOOTPRINT_FACTOR,
    FOOTPRINT_RATE_COLUMN,
    INSURED_RATE_COLUMN,
    LIQUEFACTION_FACTOR,
    RATE_COLUMN,
    RING_RATE_COLUMN,
    VALUER_EXAMPLE,
    load_properties,
    typical_section,
)
from scripts.landloss.paths import REPO_ROOT, REPORT_DIR
from scripts.landloss.vul.liquefaction.land.report.gen_report_numbers import (
    within_authority,
)
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    world_loss_input_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = REPORT_DIR / "loss" / "qv-land-value" / "tab" / "report-numbers.yaml"
# The figures the appendix shows, by the key it refers to them by.
FIGURES = {
    "valuer": FIG_DIR / "qv-tier-example-valuer.png",
    "typical": FIG_DIR / "qv-tier-example-typical.png",
}
WORLD_ID = 0
REALISATION_ID = 0
# The medians reported, by the key the appendix reads them by.
MEDIANS = {
    "average_rate": RATE_COLUMN,
    "footprint_rate": FOOTPRINT_RATE_COLUMN,
    "ring_rate": RING_RATE_COLUMN,
    "insured_rate": INSURED_RATE_COLUMN,
    "liquefaction_factor": LIQUEFACTION_FACTOR,
    "footprint_factor": FOOTPRINT_FACTOR,
}


def settings():
    """Return the values the land is valued with."""
    base_rates = load_base_rates()
    return {
        "insured_ratio": INSURED_RATIO,
        "uninsured_ratio": UNINSURED_RATIO,
        "max_uninsured_m2": MAX_UNINSURED_M2,
        "valuation_date": pd.Timestamp(COMMON_VALUATION_DATE).date().isoformat(),
        "gst_rate": GST_RATE,
        "councils": {
            str(row.ta_name): {
                "valuation_date": pd.Timestamp(row.valuation_date).date().isoformat(),
                "index": float(row.index_to_2025_09),
            }
            for row in base_rates.itertuples()
        },
    }


def sources(roll, base_rates, extents):
    """Return how many claims take their land value from each source.

    Returns:
        ``(numbers, from_roll)``: the counts for the YAML, and the ids of the
        claims that take their value from the roll, which the rates are taken
        over.
    """
    counts = {}
    non_residential = 0
    from_roll = set()
    for extent in extents:
        land = pd.read_parquet(
            world_loss_input_path("land", WORLD_ID, REALISATION_ID, extent=extent),
            columns=[
                LAND_ID_COLUMN,
                CLAIM_ID_COLUMN,
                LAND_PROPERTY_AREA_COLUMN,
                LAND_SUBURB_COLUMN,
            ],
        )
        land = within_authority(land, extent)
        by_claim = qv_land_value_by_claim(
            roll, pd.read_parquet(valuation_links_path(extent=extent)), base_rates
        )
        dropped = non_residential_claims(by_claim)
        non_residential += int(
            land.loc[land[CLAIM_ID_COLUMN].isin(dropped), CLAIM_ID_COLUMN].nunique()
        )
        land = land[~land[CLAIM_ID_COLUMN].isin(dropped)]
        values = claim_land_values(land, residential_land_values(by_claim))
        for source, count in values[VALUE_SOURCE_COLUMN].value_counts().items():
            counts[str(source)] = counts.get(str(source), 0) + int(count)
        from_roll |= set(values.index[values[VALUE_SOURCE_COLUMN] == FROM_ROLL])
    numbers = {
        "claims": sum(counts.values()),
        "by_source": counts,
        "non_residential": non_residential,
    }
    return numbers, from_roll


def medians(table):
    """Return the median of each rate and factor."""
    return {key: float(table[column].median()) for key, column in MEDIANS.items()}


def rates(table):
    """Return the medians overall and per area band."""
    return {
        "properties": len(table),
        "overall": medians(table),
        "by_area": {
            str(band): {"properties": len(rows), **medians(rows)}
            for band, rows in table.groupby(AREA_BAND_COLUMN, observed=True)
        },
    }


def worked(example):
    """Return an example's tiers: their areas, rates and values."""
    value, area = example["value"], example["area"]
    footprint, insured = example["footprint"], example["insured"]
    ring, outer = insured - footprint, area - insured
    counted = min(outer, MAX_UNINSURED_M2)
    full = value / (footprint + INSURED_RATIO * ring + UNINSURED_RATIO * counted)
    return {
        "value": float(value),
        "area_m2": float(area),
        "footprint_m2": float(footprint),
        "ring_m2": float(ring),
        "outer_m2": float(outer),
        "footprint_rate": float(full),
        "ring_rate": float(INSURED_RATIO * full),
        "outer_rate": float(UNINSURED_RATIO * full),
        "insured_rate": float(full * (footprint + INSURED_RATIO * ring) / insured),
        "average_rate": float(value / area),
        "footprint_value": float(full * footprint),
    }


def main(*, extents):
    """Compute the numbers and write the YAML."""
    table = load_properties(extents)
    print("Reading the QV rating roll again for the value sources ...", flush=True)
    by_source, from_roll = sources(get_qv_rating_roll(), load_base_rates(), extents)
    # The rates over the same claims the text counts as valued from the roll.
    table = table[table.index.isin(from_roll)]
    if len(table) != by_source["by_source"].get(FROM_ROLL, 0):
        msg = (
            f"the rates cover {len(table):,} claims but "
            f"{by_source['by_source'].get(FROM_ROLL, 0):,} are valued from the roll"
        )
        raise ValueError(msg)
    numbers = {
        "meta": {
            "written": dt.datetime.now().astimezone().date().isoformat(),
            "commit": git_commit(),
            "extents": [get_area_of_interest(extent).name for extent in extents],
        },
        "settings": settings(),
        "sources": by_source,
        "rates": rates(table),
        "examples": {
            "valuer": worked(VALUER_EXAMPLE),
            "typical": worked(typical_section(table)),
        },
        "figures": {
            key: path.relative_to(REPO_ROOT).as_posix() if path.exists() else None
            for key, path in FIGURES.items()
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        yaml.safe_dump(numbers, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(
        yaml.safe_dump({k: numbers[k] for k in ("sources", "rates")}, sort_keys=False)
    )
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main(extents=config.QV_RATE_EXTENTS)
