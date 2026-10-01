"""What the extracted claim reports say about landslide land damage and walls.

    uv run --frozen python src/scripts/landloss/vul/research/analyse_claim_reports.py

Reads the CSVs ``extract_claim_reports.py --claims-list`` writes under
``src/landloss/common/assets/claim_reports/extracted/`` -- local only, since
the claim report data is gitignored -- and answers the questions the reports
were fetched for (Maxim Millen, 2026-09-25):

- how much land is at imminent risk against how much was evacuated;
- how often evacuation and inundation occur together, and in what proportion;
- how big the failures are;
- how many retaining walls a claim has, how many are damaged, and how much of
  each;

and checks the loss module's placeholders against them: the site ratings, the
design and consent fee, the share of concrete walls, and how a replacement
compares with the wall it replaces.

**Which claims count.** Accepted claims only (``claim_accepted``) and land
reports only (not structural assessments). Each is labelled by trigger --
earthquake, rain, or unknown where the report does not say -- and the tables
are given for each. A report revised after several inspections gives one
column per inspection, and summing those can double count, so the land-area
tables leave out every report with more than one summary column and say how
many that was. A 2013 report with one column per landslip is left out with
them, which costs little.

**Nothing here is a fitted parameter.** These are descriptive statistics of a
sample shaped by who claimed, which insurer sent the work to T+T, and which
reports survive as Word files (PDF-only reports are not read). Read them as
evidence for a choice, not as the choice.

Writes ``claim_report_findings.md`` and one CSV per table to
``research/vul/claim_reports/``, which is gitignored with the data it comes
from.
"""

import re
import sys

import numpy as np
import pandas as pd

from landloss.loss.pricing import (
    BETA_CONCRETE_SHARE,
    PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD,
)
from scripts.landloss.paths import CLAIM_REPORTS_ASSETS_DIR, RESEARCH_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXTRACTED_DIR = CLAIM_REPORTS_ASSETS_DIR / "extracted"
OUT_DIR = RESEARCH_DIR / "vul" / "claim_reports"
LISTS = ("iag-1502000", "suncorp-1501000", "kaikoura-2016", "seddon-2013")

# What the loss module charges in design and consent fees per claim.
MODEL_FEES_EXCL_GST = PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD

# Wall constructions, matched in this order against a wall's description so
# that "Metal pole timber lagged wall" reads as timber and "Concrete crib" as
# crib.
CONSTRUCTIONS = (
    ("crib", r"crib"),
    ("gabion", r"gabion"),
    ("timber", r"timber|\bpole|\bpost|sleeper|lagg"),
    ("steel", r"steel|metal|universal beam|\bub\b|pfc|sheet pil|h[- ]?pile"),
    ("masonry/block", r"masonry|block"),
    ("concrete", r"concrete|shotcrete|sprayed|gunite"),
    ("brick", r"brick"),
    ("stone/rock", r"stone|rock|boulder"),
)
TRIGGERS = ("earthquake", "rain", "unknown")

# A retained height over this is a typo in the report, not a wall:
# one report gives "Approx. 600 m" for a wall 600 mm in the ground.
MAX_RETAINED_HEIGHT_M = 20.0

# The older templates rate a site "hard" or "moderate", often with a note
# marker ("hard*", "hard1", "moderate (note 1)"), where the newer ones use
# E, M and D.
RATING = (
    ("D", r"^(?:d|hard|difficult)"),
    ("M", r"^(?:m|moderate)"),
    ("E", r"^(?:e|easy)"),
)

AREAS = (
    "total_evacuated_m2",
    "total_inundated_m2",
    "total_imminent_evacuation_m2",
    "total_imminent_new_inundation_m2",
    "total_imminent_reinundation_m2",
)


def markdown(frame: pd.DataFrame, digits: int) -> str:
    """Return a frame as a Markdown table, numbers rounded to ``digits``."""

    def cell(value: object) -> str:
        if isinstance(value, float):
            return "" if np.isnan(value) else f"{value:,.{digits}f}"
        return str(value)

    header = ["", *map(str, frame.columns)]
    rows = [
        [str(index), *map(cell, row)] for index, row in zip(frame.index, frame.values)
    ]
    rule = ["---"] * len(header)
    return "\n".join("| " + " | ".join(row) + " |" for row in (header, rule, *rows))


def number(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a column as numbers, blank where it is not one."""
    return pd.to_numeric(frame[column], errors="coerce")


def construction_class(text: str) -> str:
    """Return the construction a wall's description names, or "other"."""
    for name, pattern in CONSTRUCTIONS:
        if isinstance(text, str) and re.search(pattern, text, re.IGNORECASE):
            return name
    return "other"


def rating(text: object) -> str | float:
    """Return a site rating as E, M or D, or blank where there is none."""
    if not isinstance(text, str) or not text.strip():
        return np.nan
    for name, pattern in RATING:
        if re.match(pattern, text.strip(), re.IGNORECASE):
            return name
    return text.strip()


def load(name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return one list's reports, walls and remedial walls."""
    folder = EXTRACTED_DIR / name
    read = lambda stem: pd.read_csv(folder / f"{stem}.csv", dtype=str)  # noqa: E731
    reports, walls, remedial = read("reports"), read("walls"), read("remedial_walls")
    for frame in (reports, walls, remedial):
        frame["list"] = name
    return reports, walls, remedial


def describe(values: pd.Series) -> dict[str, float]:
    """Return the count, mean and quartiles of the known values."""
    known = values.dropna()
    if known.empty:
        return {"n": 0}
    return {
        "n": int(known.size),
        "mean": known.mean(),
        "p10": known.quantile(0.10),
        "p25": known.quantile(0.25),
        "median": known.median(),
        "p75": known.quantile(0.75),
        "p90": known.quantile(0.90),
        "max": known.max(),
    }


def by_trigger(frame: pd.DataFrame, values: pd.Series) -> pd.DataFrame:
    """Return :func:`describe` of some values, for all claims and per trigger."""
    rows = {"all": describe(values)}
    for trigger in TRIGGERS:
        rows[trigger] = describe(values[frame["trigger"] == trigger])
    return pd.DataFrame(rows).T


def share(mask: pd.Series) -> str:
    """Return a share as "n of N (p%)"."""
    total = int(mask.notna().sum())
    hits = int(mask.fillna(value=False).sum())
    return f"{hits:,} of {total:,} ({hits / total:.0%})" if total else "none"


def main() -> int:
    """Read the extracted lists, write the findings."""
    loaded = [load(name) for name in LISTS if (EXTRACTED_DIR / name).exists()]
    if not loaded:
        print(f"No extracted lists under {EXTRACTED_DIR}; run step two first.")
        return 1
    reports = pd.concat([part[0] for part in loaded], ignore_index=True)
    reports = reports.drop_duplicates("subproject").reset_index(drop=True)
    walls = pd.concat([part[1] for part in loaded], ignore_index=True)
    walls = walls.drop_duplicates(["subproject", "wall_number", "description"])
    remedial = pd.concat([part[2] for part in loaded], ignore_index=True)

    cause = reports["event_cause"].fillna("")
    reports["trigger"] = np.where(
        cause == "earthquake",
        "earthquake",
        np.where(cause == "rain", "rain", "unknown"),
    )
    accepted = reports[
        (reports["claim_accepted"] == "True")
        & (reports["report_kind"].fillna("land") != "structural")
    ].reset_index(drop=True)
    claims = set(accepted["subproject"])
    walls = walls[walls["subproject"].isin(claims)].copy()
    remedial = remedial[remedial["subproject"].isin(claims)].copy()
    walls = walls.merge(accepted[["subproject", "trigger"]], on="subproject")
    height = number(walls, "retained_height_m")
    walls["retained_height_m"] = height.where(height <= MAX_RETAINED_HEIGHT_M)
    remedial = remedial.merge(accepted[["subproject", "trigger"]], on="subproject")

    one_column = number(accepted, "summary_columns").fillna(1) <= 1
    land = accepted[one_column].reset_index(drop=True)
    for column in AREAS:
        land[column] = number(land, column)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# Claim reports: findings", ""]
    tables: dict[str, pd.DataFrame] = {}

    def section(title: str) -> None:
        lines.extend(["", f"## {title}", ""])

    def table(name: str, frame: pd.DataFrame, *, digits: int = 1) -> None:
        tables[name] = frame
        lines.append(markdown(frame, digits))
        lines.append("")

    # --- the sample --------------------------------------------------------
    section("The sample")
    lines.append(
        f"{len(reports):,} reports read; {len(accepted):,} accepted land claims; "
        f"{len(land):,} of those with one summary column, used for the land "
        f"areas ({len(accepted) - len(land):,} multi-column reports left out)."
    )
    lines.append("")
    table(
        "sample",
        pd.crosstab(accepted["list"], accepted["trigger"], margins=True),
        digits=0,
    )

    # --- land areas --------------------------------------------------------
    section("Damaged land per claim (m2, land within 8 m and main access way)")
    for column in AREAS:
        lines.append(f"**{column}**")
        lines.append("")
        table(f"area_{column}", by_trigger(land, land[column]))

    section("Evacuation and inundation together")
    evac = land["total_evacuated_m2"].fillna(0) > 0
    inund = land["total_inundated_m2"].fillna(0) > 0
    for label_, mask in (
        ("evacuated only", evac & ~inund),
        ("inundated only", ~evac & inund),
        ("both", evac & inund),
        ("neither", ~evac & ~inund),
    ):
        lines.append(f"- {label_}: {share(mask)}")
    both = land[evac & inund]
    ratio = both["total_inundated_m2"] / both["total_evacuated_m2"]
    lines.append("")
    lines.append(
        "Inundated over evacuated area, where both occur (the extents' "
        "geometry is not in the reports, so this is a ratio of areas, not an "
        "overlap):"
    )
    lines.append("")
    table("inundated_over_evacuated", by_trigger(both, ratio), digits=2)

    # --- imminent risk ------------------------------------------------------
    section("Imminent evacuation against evacuation")
    with_evac = land[evac]
    imminent = with_evac["total_imminent_evacuation_m2"]
    lines.append(f"- any imminent evacuation: {share(imminent.fillna(0) > 0)}")
    pooled = imminent.sum() / with_evac["total_evacuated_m2"].sum()
    lines.append(f"- pooled ratio (sum over sum): {pooled:.2f}")
    lines.append("")
    table(
        "imminent_over_evacuated",
        by_trigger(with_evac, imminent / with_evac["total_evacuated_m2"]),
        digits=2,
    )

    # --- failure size -------------------------------------------------------
    section("Failure size")
    widths = accepted["landslip_widths_m"].fillna("").str.split(";").explode()
    widths = pd.to_numeric(widths, errors="coerce")
    lines.append("Landslip width (m), one value per landslip described:")
    lines.append("")
    table("landslip_width", pd.DataFrame({"all": describe(widths)}).T)
    depth = number(land, "inundated_volume_m3") / land["total_inundated_m2"]
    lines.append(
        "Inundated depth (m), from the volume the NHI Act template gives beside "
        "the area:"
    )
    lines.append("")
    table("inundated_depth", by_trigger(land, depth.where(depth > 0)), digits=2)

    # --- retaining walls -----------------------------------------------------
    section("Retaining walls")
    n_walls = number(accepted, "n_walls").fillna(0)
    lines.append(f"- claims with at least one wall listed: {share(n_walls > 0)}")
    lines.append(f"- of those, with more than one: {share(n_walls[n_walls > 0] > 1)}")
    lines.append(
        "- the reports list damaged walls far more than undamaged ones, so "
        "these are counts of walls reported, not of walls present."
    )
    lines.append("")
    walls["class"] = walls["description"].map(construction_class)
    counts = walls["class"].value_counts()
    table(
        "wall_construction",
        pd.DataFrame({"walls": counts, "share": counts / counts.sum()}),
        digits=2,
    )
    concrete = counts.reindex(["concrete", "masonry/block", "crib"]).fillna(0).sum()
    lines.append(
        f"The loss module prices {BETA_CONCRETE_SHARE:.0%} of walls as concrete; "
        f"concrete, block and crib walls are {concrete / counts.sum():.0%} of the "
        "walls reported here."
    )
    lines.append("")
    for column, title in (
        ("retained_height_m", "Retained height (m)"),
        ("whole_length_m", "Whole length (m)"),
        ("damaged_length_m", "Damaged length (m), from the damage bullets"),
    ):
        lines.append(f"**{title}**")
        lines.append("")
        table(f"wall_{column}", by_trigger(walls, number(walls, column)))
    fraction = number(walls, "damaged_length_m") / number(walls, "whole_length_m")
    lines.append("**Share of a wall's length damaged**")
    lines.append("")
    table(
        "wall_damaged_fraction",
        by_trigger(walls, fraction.where(fraction <= 1)),
        digits=2,
    )

    # --- remedial works ------------------------------------------------------
    section("Replacement walls")
    remedial["class"] = remedial["construction"].map(construction_class)
    rcounts = remedial["class"].value_counts()
    table(
        "remedial_construction",
        pd.DataFrame({"walls": rcounts, "share": rcounts / rcounts.sum()}),
        digits=2,
    )
    old = walls.assign(h=number(walls, "retained_height_m")).groupby("subproject")
    new = remedial.assign(h=number(remedial, "max_retained_height_m")).groupby(
        "subproject"
    )
    heights = pd.DataFrame({"old": old["h"].max(), "new": new["h"].max()}).dropna()
    lines.append(
        f"- claims with both an existing and a replacement height: {len(heights):,}"
    )
    lines.append(
        f"- replacement taller than the tallest existing wall: "
        f"{share(heights['new'] > heights['old'] + 0.05)}"
    )
    lines.append(
        f"- median replacement over existing height: "
        f"{(heights['new'] / heights['old']).median():.2f}"
    )
    first_old = walls.groupby("subproject")["class"].first()
    first_new = remedial.groupby("subproject")["class"].first()
    paired = pd.DataFrame({"old": first_old, "new": first_new}).dropna()
    lines.append(
        f"- replacement in a different construction from the first wall it "
        f"replaces: {share(paired['old'] != paired['new'])}"
    )
    lines.append("")
    table("construction_change", pd.crosstab(paired["old"], paired["new"]), digits=0)

    # --- site ratings and fees ----------------------------------------------
    section("Site ratings (the costing tool's construction issues)")
    ratings = {
        column: accepted[column].map(rating).value_counts()
        for column in (
            "construction_access",
            "earthworks_required",
            "constructability_reinstatement",
        )
    }
    table("site_ratings", pd.DataFrame(ratings).fillna(0).astype(int), digits=0)

    section("Design and consent fees (excl GST)")
    design_only = accepted[accepted["estimate_includes_construction"] != "True"]
    fees = number(design_only, "design_consent_cost_excl_gst_nzd")
    lines.append(
        f"The loss module charges ${MODEL_FEES_EXCL_GST:,.0f} per claim with a wall. "
        "Reports that price design and consent only (not the 2013 ones, which "
        "include construction), excluding $0:"
    )
    lines.append("")
    table("design_fees", by_trigger(design_only, fees.where(fees > 0)), digits=0)

    out = OUT_DIR / "claim_report_findings.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name, frame in tables.items():
        frame.to_csv(OUT_DIR / f"{name}.csv")
    print("\n".join(lines))
    print(f"\nWrote {out} and {len(tables)} tables beside it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
