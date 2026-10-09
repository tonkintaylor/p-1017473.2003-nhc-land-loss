"""Escalate the Canterbury liquefaction land costs to the study's dollars.

    uv run --frozen python src/scripts/landloss/vul/static_data_gen/gen_escalated_liq_land_costs.py

Reads the packaged 2010/2011 rates, multiplies every cost column by one named
factor, and writes a second asset beside the first. **Run once and committed**,
not part of the pipeline: escalating a six-row table on every run would be
arithmetic pretending to be modelling, and it would put the factor somewhere a
reader has to go looking for it. The numbers are read directly thereafter.

The 2011 file is left exactly as it is. Two assets, one original and one
escalated, means the escalation can be checked by dividing them, and a change of
index is a re-run rather than an edit to source data.

**The factor is not set.** :data:`ESCALATION_FACTOR` is ``None`` and the script
refuses to run until somebody puts a number in it, because there is no index in
this repository that fits: the only one here is the QV House Price Index, which
prices residential land rather than the cost of repairing it. See the notes on
:data:`ESCALATION_FACTOR` for what the number has to be, and what it has to be
sourced from.

Closes the escalation half of **L-23**; the GST half is already done at the loss
boundary.
"""

import sys

import pandas as pd

from landloss.vul.liquefaction.costs import COSTS_PATH, PERCENTILE_COLUMNS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The cost year the packaged rates are in, and the year they are being brought
# to. Both are written down rather than implied by a file name, because the
# file name is the first thing to go stale.
SOURCE_COST_YEAR = 2011
TARGET_COST_YEAR = 2026

# ---------------------------------------------------------------------------
# **SET THIS BEFORE RUNNING.**
#
# What one 2011 dollar of Canterbury land repair costs in 2026. Whoever fills it
# in should also fill in the two lines under it, because a factor without a
# source is indistinguishable from a guess six months from now.
#
# It must come from a **construction cost** index, not a property price one.
# Statistics NZ's Capital Goods Price Index is the usual New Zealand choice for
# this; CPI measures household consumption and would understate construction
# over this period. The QV House Price Index already in this repository is the
# wrong instrument twice over -- it prices land rather than works, and it is
# regional rather than national.
#
# Maxim Millen's expectation on 2026-09-24 was "maybe four times ... two, three
# times", so a factor far outside 2.0 to 4.0 is worth a second look before it is
# accepted.
ESCALATION_FACTOR: float | None = None
ESCALATION_INDEX = ""  # e.g. "Statistics NZ CGPI, residential building"
ESCALATION_SOURCE = ""  # e.g. the table id and the date it was read
# ---------------------------------------------------------------------------

OUT_PATH = COSTS_PATH.with_name(
    COSTS_PATH.name.replace(str(SOURCE_COST_YEAR), str(TARGET_COST_YEAR))
)
README_PATH = OUT_PATH.with_name(f"{OUT_PATH.stem}_README.md")


def escalated(costs: pd.DataFrame, factor: float) -> pd.DataFrame:
    """Return the cost table with every percentile column multiplied.

    The state, its name and the source band are carried across untouched: they
    identify a row rather than price it.

    Args:
        costs: The packaged rates, as read from :data:`COSTS_PATH`.
        factor: What one source-year dollar is worth in the target year.

    Returns:
        The same table, escalated, with the costs rounded to whole dollars --
        the source is round hundreds and a long decimal would imply a precision
        the escalation does not have.

    Raises:
        ValueError: If the factor is not positive.
    """
    if not factor > 0:
        msg = f"the escalation factor must be positive, got {factor!r}"
        raise ValueError(msg)
    out = costs.copy()
    for column in PERCENTILE_COLUMNS.values():
        out[column] = (out[column] * factor).round(0).astype(int)
    return out


def readme(factor: float, costs: pd.DataFrame, out: pd.DataFrame) -> str:
    """Return the note that ships beside the escalated asset."""
    rows = "\n".join(
        f"| {state} | {name} | "
        + " | ".join(
            f"{costs.loc[state, column]:,} -> {out.loc[state, column]:,}"
            for column in PERCENTILE_COLUMNS.values()
        )
        + " |"
        for state, name in out["state_name"].items()
    )
    return f"""# Canterbury liquefaction land costs, escalated to {TARGET_COST_YEAR}

**Generated. Do not edit by hand** -- rerun
`src/scripts/landloss/vul/static_data_gen/gen_escalated_liq_land_costs.py`.

Every cost in `{COSTS_PATH.name}` multiplied by **{factor}**, which is what one
{SOURCE_COST_YEAR} dollar of Canterbury land repair is taken to cost in
{TARGET_COST_YEAR}.

- **Index:** {ESCALATION_INDEX or "NOT RECORDED"}
- **Source:** {ESCALATION_SOURCE or "NOT RECORDED"}

Everything true of the source file is still true here, and is **not** fixed by
escalating: the rates are per property rather than per square metre, they
exclude GST, they cover categories 1 to 7 and so exclude ILV and IFV
(**L-25**), they apply to flat land only and must not be used for hill land or
landslide damage, and states 5 and 6 carry one estimate between them.

| State | Name | 15th | 50th | 85th |
| --- | --- | --- | --- | --- |
{rows}
"""


def main() -> int:
    """Write the escalated asset and its note, or explain why it cannot."""
    if ESCALATION_FACTOR is None:
        print(
            "ESCALATION_FACTOR is not set, so nothing was written.\n"
            "\n"
            f"Set it to what one {SOURCE_COST_YEAR} dollar of Canterbury land "
            f"repair costs in {TARGET_COST_YEAR}, off a construction cost "
            "index -- Statistics NZ's CGPI rather than CPI, and not the QV "
            "House Price Index, which prices land rather than works. Record "
            "the index and where it was read in ESCALATION_INDEX and "
            "ESCALATION_SOURCE beside it.\n"
            "\n"
            "Until then the loss module compares 2011 repair costs against "
            "present-day land values, which understates the repair side."
        )
        return 1

    costs = pd.read_csv(COSTS_PATH, keep_default_na=False).set_index("LD_refined_state")
    out = escalated(costs, ESCALATION_FACTOR)
    out.reset_index().to_csv(OUT_PATH, index=False)
    README_PATH.write_text(readme(ESCALATION_FACTOR, costs, out), encoding="utf-8")

    print(f"Escalated {len(out)} states by {ESCALATION_FACTOR} :")
    for state, name in out["state_name"].items():
        before = costs.loc[state, PERCENTILE_COLUMNS[50]]
        after = out.loc[state, PERCENTILE_COLUMNS[50]]
        print(f"  {name:<12} {before:>7,} -> {after:>8,}  (50th percentile)")
    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {README_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
