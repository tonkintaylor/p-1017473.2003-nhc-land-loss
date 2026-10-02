"""Write the settlement calculation as a spreadsheet, for review off the code.

    uv run --frozen python src/scripts/landloss/loss/validations/gen_calc_walkthrough.py

Three tabs, for two different questions.

**Overview** answers "what does this model do to the portfolio" -- histograms of
settlement, repair cost and the cap across **every** claim, and what the repair
cost is made of. **Calculation** answers "how did this claim get that number",
on twenty claims chosen to show one of each interesting case. **Repair cost**
breaks that down line by line, with the assumption behind each one numbered so a
meeting can take them in turn.

The policy settings sit on both of the first two tabs, so whichever one is open
the numbers that drive everything are in front of the reader.

The twenty claims are **not a random sample**. Twenty rows drawn at random from
this population would be twenty ordinary liquefaction claims, so they are picked
to include a damaged wall, a landslide, several dwellings, and the claims where
the cap actually binds. The sheet says so on its face.

Every cell is a value rather than a formula, apart from row totals: openpyxl
cannot write a formula's result, and a formula with no cached result reads as
empty to everything except Excel. The arithmetic behind each worked column is
written under the headings instead.

It reads step 1's output, so `gen_loss.py` runs first.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LIQ_LD_AREA_COLUMN,
    LIQ_LD_STATE_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
    RW_SIZE_COLUMN,
    TOTAL_INSURED_LAND_AREA_COLUMN,
)
from landloss.loss import claims as loss_claims
from landloss.loss.policy import PolicySettings
from landloss.loss.pricing import (
    BETA_SIZE_CLASS_HEIGHT_M,
    beta_wall_height_m,
    beta_wall_rate_excl_gst_nzd_per_m2,
)
from scripts.landloss.loss.steps.s1_settlement import config
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    CROSSING_REPAIR_COLUMN,
    FEES_COLUMN,
    LAND_REPAIR_COLUMN,
    LANDSLIDE_REPAIR_AREA_COLUMN,
    LIQ_REPAIR_COLUMN,
    NEW_WALL_HEIGHT_COLUMN,
    NEW_WALL_LENGTH_COLUMN,
    NEW_WALL_SIZE_COLUMN,
    REPLACEMENT_WALL_LENGTH_COLUMN,
    REPLACEMENT_WALL_RATE_COLUMN,
    REPLACEMENT_WALL_SIZE_COLUMN,
    RW_UDV_COLUMN,
    SPOIL_REPAIR_COLUMN,
    SPOIL_VOLUME_COLUMN,
    SYNTHETIC_WALL_COLUMN,
    WALL_REPAIR_COLUMN,
    settlement_path,
)
from scripts.landloss.paths import REPORT_DIR
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    loss_input_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = REPORT_DIR / "loss" / "calc-walkthrough"
OUT_NAME = "loss-calculation-walkthrough.xlsx"

CLAIMS = 20
FONT = "Arial"

# The claim types the distributions are split by. Exhaustive and mutually
# exclusive on this data: no claim carries a damaged crossing, and none has
# spoil without a wall, so these three account for every claim that is paid.
LIQ_ONLY = "Liquefaction only"
WALL_ONLY = "Retaining wall only"
BOTH = "Both"
CLAIM_TYPES = (LIQ_ONLY, WALL_ONLY, BOTH)

# Categorical hues in fixed order, one per claim type, from the reference
# palette's categorical theme. Validated for colour-blind separation rather
# than chosen by eye: worst adjacent pair is deutan dE 9.2, normal-vision 27.6.
# The aqua sits at 2.74:1 against a white surface, under the 3:1 bar, which the
# band tables beside each chart and the labels on the axis are the relief for.
TYPE_FILL = {LIQ_ONLY: "2A78D6", WALL_ONLY: "EB6834", BOTH: "1BAF7A"}

# One hue for the single-series chart, where there is nothing to tell apart.
SERIES_FILL = "3B6E8F"

INPUT = Font(name=FONT, size=10, color="0000FF")
WORKED = Font(name=FONT, size=10, color="000000")
TEXT = Font(name=FONT, size=10)
HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
TITLE = Font(name=FONT, size=12, bold=True)
SECTION = Font(name=FONT, size=10, bold=True)
BIG = Font(name=FONT, size=14, bold=True)
NOTE = Font(name=FONT, size=9, italic=True)
HEAD_FILL = PatternFill("solid", fgColor="44546A")
SETTING_FILL = PatternFill("solid", fgColor="FFFF00")
EDGE = Border(bottom=Side(style="thin", color="BFBFBF"))

MONEY = "$#,##0;($#,##0);-"
AREA = "#,##0.0"
RATE = "$#,##0.00"
COUNT = "#,##0"

# The settings block, repeated at the top of the first two tabs.
SETTINGS_ROW = {
    "area_cap": 3,
    "rw_sub_cap": 4,
    "excess_each": 5,
    "excess_max": 6,
    "gst": 7,
}
HEADER_ROW = 12
FIRST_DATA_ROW = HEADER_ROW + 2

# The calculation table: column, where its value comes from, format, width. A
# source of None means the column is worked rather than read. A wall's own size,
# height, length and rate live on the Repair cost tab, which is where a reader
# goes to see how a wall was priced.
COLUMNS = [
    ("Claim", "claim_id", None, 40),
    ("Dwellings", "dwelling_count", COUNT, 11),
    ("Damaged land, for the cap (m2)", "damaged_area_m2", AREA, 19),
    ("Land rate incl GST ($/m2)", "land_rate_incl_gst_nzd_per_m2", RATE, 20),
    ("Land value ($)", None, MONEY, 15),
    ("Wall UDV ($)", RW_UDV_COLUMN, MONEY, 14),
    ("Wall to cap ($)", None, MONEY, 15),
    ("Land cover cap ($)", None, MONEY, 17),
    ("Repair cost ($)", "repair_cost_incl_gst_nzd", MONEY, 15),
    ("Payable before excess ($)", None, MONEY, 16),
    ("Excess ($)", None, MONEY, 12),
    ("Settlement ($)", None, MONEY, 15),
]

# The live formula behind every worked column, by column number; `{r}` is the
# row. These are the point of the tab rather than decoration: they are what a
# change to a yellow setting flows through.
COLUMN_FORMULA = {
    5: "=MIN(C{r},$B$3)*D{r}",
    7: "=MIN(F{r},$B$4*B{r})",
    8: "=E{r}+G{r}",
    10: "=MIN(I{r},H{r})",
    # So much per dwelling, capped -- but a claim paid nothing is charged
    # nothing, which the trailing comparison does without a nested IF. Excel
    # reads a comparison as 1 or 0 when it is multiplied.
    11: "=MIN(B{r}*$B$5,$B$6)*(J{r}>0)",
    12: "=MAX(0,J{r}-K{r})",
}

WORKED_FORMULA = {
    3: "MAX(liquefied land, the slip)",
    5: "MIN(damaged land, area cap) x land rate",
    6: "face area x wall rate x GST; see the Repair cost tab",
    7: "MIN(wall UDV, sub-cap x dwellings)",
    8: "land value + wall to cap",
    10: "MIN(repair cost, cap) -- the Act pays the lesser",
    11: "so much per dwelling, capped; nothing if nothing is payable",
    12: "payable less the excess, never below zero",
}

# Histogram bands. Money here is heavily skewed -- a median settlement near
# $1,200 against a maximum over $200,000 -- so the bands widen as they rise and
# the last is open ended. Equal bands would put nearly every claim in the first.
MONEY_BANDS = [500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000]
CAP_BANDS = [100_000, 250_000, 500_000, 750_000, 1_000_000, 2_000_000]

# Where the band tables the charts read are written. On the sheet rather than
# hidden, so a reader can check a bar against its count -- which is also what
# makes the aqua's contrast acceptable.
DATA_LABEL_COL = 18
DATA_VALUE_COL = 19


def pick_claims(claims: pd.DataFrame) -> pd.DataFrame:
    """Return the twenty claims the Calculation tab shows.

    One of each case a reviewer should see, then filled out with the most
    ordinary claims there are. Taken in a fixed order so two runs of this script
    produce the same sheet.

    Args:
        claims: Step 1's settlements, one row per claim.

    Returns:
        Up to :data:`CLAIMS` rows, with a ``case`` column saying why each is in.
    """
    wanted = {
        "the cap binds": claims["capped"] & (claims["damaged_area_m2"] > 0),
        "landslide, new wall built": claims[SYNTHETIC_WALL_COLUMN],
        "damaged wall": claims[WALL_REPAIR_COLUMN] > 0,
        "liquefaction only": (claims[LIQ_REPAIR_COLUMN] > 0)
        & (claims[WALL_REPAIR_COLUMN] == 0),
        "several dwellings": claims["dwelling_count"] > 1,
        "paid nothing, excess took it": (claims["repair_cost_incl_gst_nzd"] > 0)
        & (claims["settlement_incl_gst_nzd"] == 0),
    }
    taken: list[str] = []
    labels: dict[str, str] = {}
    for label, mask in wanted.items():
        for claim_id in claims.loc[mask].index[:4]:
            if claim_id not in taken:
                taken.append(claim_id)
                labels[claim_id] = label
    for claim_id in claims.index:
        if len(taken) >= CLAIMS:
            break
        if claim_id not in taken:
            taken.append(claim_id)
            labels.setdefault(claim_id, "ordinary claim")
    chosen = claims.loc[taken[:CLAIMS]].copy()
    chosen["case"] = [labels[claim_id] for claim_id in chosen.index]
    return chosen


# Where a band label switches from thousands to millions. Past this a label in
# thousands stops being read at a glance -- "1000-2000k" has to be counted
# rather than seen.
MILLION = 1_000_000


def _scaled(amount: float) -> str:
    """Return an amount as ``750k`` or ``1.5m``, whichever reads shorter."""
    if amount >= MILLION:
        return f"{amount / MILLION:g}m"
    return f"{amount / 1000:g}k"


def band_label(lower: float, upper: float) -> str:
    """Return the label for one band, in thousands or millions.

    Both edges carry a unit only where they differ, so a band inside one scale
    reads ``250-500k`` and one that crosses reads ``750k-1m``.

    Args:
        lower: The band's lower edge.
        upper: Its upper edge.

    Returns:
        The label.
    """
    if (lower >= MILLION) == (upper >= MILLION):
        scale = MILLION if upper >= MILLION else 1000
        unit = "m" if upper >= MILLION else "k"
        return f"{lower / scale:g}-{upper / scale:g}{unit}"
    return f"{_scaled(lower)}-{_scaled(upper)}"


def claim_types(claims: pd.DataFrame) -> pd.Series:
    """Return what kind of damage each claim carries.

    Three kinds, by which costs a claim attracts: a Canterbury liquefaction
    cost, a wall cost -- whether replacing one that failed or building one to
    reinstate landslide ground -- or both. On this data they are exhaustive
    over every claim that is paid anything.

    Args:
        claims: Step 1's settlements.

    Returns:
        One of :data:`CLAIM_TYPES` per claim, or the empty string for a claim
        with neither.
    """
    liquefied = claims[LIQ_REPAIR_COLUMN] > 0
    walled = (claims[WALL_REPAIR_COLUMN] > 0) | (claims[LAND_REPAIR_COLUMN] > 0)
    return pd.Series(
        np.select(
            [liquefied & walled, liquefied & ~walled, walled & ~liquefied],
            [BOTH, LIQ_ONLY, WALL_ONLY],
            default="",
        ),
        index=claims.index,
    )


def banded(values: pd.Series, kinds: pd.Series, bands: list[int]) -> pd.DataFrame:
    """Return how many claims of each kind fall in each band.

    Args:
        values: The amounts to count, one per claim.
        kinds: The claim type of each, from :func:`claim_types`.
        bands: Ascending upper bounds; anything above the last is its own band.

    Returns:
        A frame of counts, bands down and :data:`CLAIM_TYPES` across.
    """
    edges = [0.0, *[float(band) for band in bands], float("inf")]
    labels = []
    for index, upper in enumerate(bands):
        lower = 0 if index == 0 else bands[index - 1]
        labels.append(band_label(lower, upper))
    labels.append(f"over {_scaled(bands[-1])}")
    cut = pd.cut(values, bins=edges, labels=labels, right=True, include_lowest=True)
    table = pd.crosstab(cut, kinds.reindex(values.index))
    return table.reindex(index=labels, columns=list(CLAIM_TYPES)).fillna(0).astype(int)


def write_settings(sheet, policy: PolicySettings, *, subtitle: str) -> None:
    """Write the title and the policy block at the top of a tab."""
    sheet["A1"] = "Loss calculation walkthrough"
    sheet["A1"].font = TITLE
    sheet["A2"] = subtitle
    sheet["A2"].font = NOTE

    rows = [
        (SETTINGS_ROW["area_cap"], "Area cap (m2)", policy.area_cap_m2, COUNT),
        (
            SETTINGS_ROW["rw_sub_cap"],
            "Retaining wall sub-cap per dwelling, incl GST ($)",
            round(policy.retaining_wall_sub_cap_nzd * (1.0 + policy.gst_rate), 2),
            MONEY,
        ),
        (
            SETTINGS_ROW["excess_each"],
            "Land excess per dwelling ($)",
            policy.excess_per_dwelling_nzd,
            MONEY,
        ),
        (
            SETTINGS_ROW["excess_max"],
            "Land excess ceiling ($)",
            policy.excess_max_nzd,
            MONEY,
        ),
        (SETTINGS_ROW["gst"], "GST rate", policy.gst_rate, "0.0%"),
    ]
    for row, label, value, fmt in rows:
        sheet.cell(row=row, column=1, value=label).font = TEXT
        cell = sheet.cell(row=row, column=2, value=value)
        cell.font = INPUT
        cell.fill = SETTING_FILL
        cell.number_format = fmt


def add_chart(
    sheet,
    anchor: str,
    *,
    title: str,
    first_row: int,
    rows: int,
    last_col: int = DATA_VALUE_COL,
    stacked: bool = False,
) -> None:
    """Anchor one single-series column chart over a band table on the sheet.

    Args:
        sheet: The sheet to place it on.
        anchor: The top-left cell the chart sits at.
        title: The chart title. It names both what is counted and what it is
            counted by, which is why neither axis carries a title: one series
            needs no legend, the band labels name themselves along the bottom,
            and a rotated title down the left collides with them.
        first_row: Row of the band table's header.
        rows: How many bands.
        last_col: Last column of the table's values; one column past
            :data:`DATA_VALUE_COL` for each extra series.
        stacked: Whether the series stack into one bar per band.
    """
    chart = BarChart()
    chart.type = "col"
    chart.title = title
    # Keep the title above the plot. Left to itself Excel floats it over the
    # bars, which costs the tallest band its top.
    chart.title.overlay = False
    chart.height = 9.0
    chart.width = 15.5
    data = Reference(
        sheet,
        min_col=DATA_VALUE_COL,
        max_col=last_col,
        min_row=first_row,
        max_row=first_row + rows,
    )
    cats = Reference(
        sheet,
        min_col=DATA_LABEL_COL,
        min_row=first_row + 1,
        max_row=first_row + rows,
    )
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)

    # openpyxl leaves `delete` unset, and Excel reads that as "hide this axis" --
    # which takes the tick labels with it and draws a chart with no bands named.
    # Both axes have to be turned on explicitly.
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.x_axis.tickLblPos = "low"
    chart.y_axis.tickLblPos = "nextTo"
    chart.y_axis.majorTickMark = "out"
    chart.x_axis.majorTickMark = "out"

    # A histogram's bars touch; a gap would read as separate categories.
    chart.gapWidth = 8

    if stacked:
        chart.grouping = "stacked"
        chart.overlap = 100
        # Identity is never colour alone: a legend names every series, and the
        # band table beside the chart gives the numbers.
        chart.legend.position = "b"
        chart.legend.overlay = False
        for series, kind in zip(chart.series, CLAIM_TYPES, strict=True):
            series.graphicalProperties.solidFill = TYPE_FILL[kind]
            # A thin surface-coloured edge keeps two segments of a stack from
            # reading as one block where their hues are close.
            series.graphicalProperties.line.solidFill = "FFFFFF"
            series.graphicalProperties.line.width = 12700
    else:
        # The count on each bar. Six bars is few enough that labelling all of
        # them reads as a table rather than as clutter.
        chart.dataLabels = DataLabelList()
        chart.dataLabels.showVal = True
        chart.dataLabels.showSerName = False
        chart.dataLabels.showCatName = False
        chart.dataLabels.showLegendKey = False
        chart.legend = None
        chart.series[0].graphicalProperties.solidFill = SERIES_FILL
        chart.series[0].graphicalProperties.line.noFill = True
    sheet.add_chart(chart, anchor)


def write_band_table(
    sheet, at: int, title: str, counts, fmt: str, measure: str
) -> None:
    """Write one band table the charts read from.

    A frame writes one column per claim type and a total; a series writes one
    column headed by ``measure``.

    Args:
        sheet: The sheet to write on.
        at: Row of the table's header.
        title: What the table counts, written over the labels.
        counts: A Series or a DataFrame of counts, bands down.
        fmt: Number format for the values.
        measure: Header over a Series' one value column.
    """
    sheet.cell(row=at, column=DATA_LABEL_COL, value=title).font = SECTION
    frame = counts.to_frame(measure) if isinstance(counts, pd.Series) else counts
    for index, column in enumerate(frame.columns):
        sheet.cell(
            row=at, column=DATA_VALUE_COL + index, value=str(column)
        ).font = SECTION
    if len(frame.columns) > 1:
        sheet.cell(
            row=at, column=DATA_VALUE_COL + len(frame.columns), value="Total"
        ).font = SECTION
    for offset, (label, row) in enumerate(frame.iterrows(), start=1):
        sheet.cell(row=at + offset, column=DATA_LABEL_COL, value=str(label)).font = TEXT
        for index, value in enumerate(row):
            cell = sheet.cell(
                row=at + offset, column=DATA_VALUE_COL + index, value=float(value)
            )
            cell.font = TEXT
            cell.number_format = fmt
        if len(frame.columns) > 1:
            cell = sheet.cell(
                row=at + offset,
                column=DATA_VALUE_COL + len(frame.columns),
                value=float(row.sum()),
            )
            cell.font = SECTION
            cell.number_format = fmt


def write_overview(sheet, claims: pd.DataFrame, policy: PolicySettings) -> None:
    """Write the portfolio tab: settings, headline numbers and the charts."""
    write_settings(
        sheet,
        policy,
        subtitle=(
            "Every claim in the run. The Calculation tab works twenty of them "
            "through line by line."
        ),
    )
    sheet.column_dimensions["A"].width = 46
    sheet.column_dimensions["B"].width = 18
    sheet.column_dimensions[get_column_letter(DATA_LABEL_COL)].width = 24
    sheet.column_dimensions[get_column_letter(DATA_VALUE_COL)].width = 14

    paid = claims[claims["settlement_incl_gst_nzd"] > 0]
    with_repair = claims[claims["repair_cost_incl_gst_nzd"] > 0]
    with_cap = claims[claims["land_cover_cap_incl_gst_nzd"] > 0]
    binding = claims["capped"] & (claims["damaged_area_m2"] > 0)

    sheet["A10"] = "Across the whole run"
    sheet["A10"].font = SECTION
    headline = [
        ("Claims", float(len(claims)), COUNT, True),
        ("Claims paid anything", float(len(paid)), COUNT, True),
        ("Total settlement ($)", claims["settlement_incl_gst_nzd"].sum(), MONEY, True),
        (
            "Median settlement, of those paid ($)",
            paid["settlement_incl_gst_nzd"].median(),
            MONEY,
            False,
        ),
        (
            "Total repair cost ($)",
            claims["repair_cost_incl_gst_nzd"].sum(),
            MONEY,
            False,
        ),
        (
            "Claims where the cap binds and there is damaged land",
            float(binding.sum()),
            COUNT,
            False,
        ),
    ]
    for offset, (label, value, fmt, big) in enumerate(headline):
        row = 11 + offset
        sheet.cell(row=row, column=1, value=label).font = TEXT
        cell = sheet.cell(row=row, column=2, value=float(value))
        cell.font = BIG if big else TEXT
        cell.number_format = fmt
    sheet.cell(
        row=18,
        column=1,
        value=(
            "The cap binds on many more claims than that, but only these have "
            "damaged land. On the rest the cap is the wall's value and the "
            "repair is that value plus the allowances, so it caps by arithmetic "
            "rather than as a result."
        ),
    ).font = NOTE

    sheet.cell(row=1, column=DATA_LABEL_COL, value="Chart data").font = SECTION

    kinds = claim_types(claims)
    tables = [
        (
            "Claims by settlement ($)",
            banded(paid["settlement_incl_gst_nzd"], kinds, MONEY_BANDS),
            "A20",
        ),
        (
            "Claims by repair cost ($)",
            banded(with_repair["repair_cost_incl_gst_nzd"], kinds, MONEY_BANDS),
            "G20",
        ),
        (
            "Claims by land cover cap ($)",
            banded(with_cap["land_cover_cap_incl_gst_nzd"], kinds, CAP_BANDS),
            "A38",
        ),
    ]
    at = 3
    for title, counts, anchor in tables:
        write_band_table(sheet, at, title, counts, COUNT, "Claims")
        add_chart(
            sheet,
            anchor,
            title=title,
            first_row=at,
            rows=len(counts),
            last_col=DATA_VALUE_COL + len(CLAIM_TYPES) - 1,
            stacked=True,
        )
        at += len(counts) + 3

    components = pd.Series(
        {
            "Walls replaced": claims[WALL_REPAIR_COLUMN].sum(),
            "New walls": claims[LAND_REPAIR_COLUMN].sum(),
            "Spoil cleared": claims[SPOIL_REPAIR_COLUMN].sum(),
            "Fees": claims[FEES_COLUMN].sum(),
            "Liquefaction": claims[LIQ_REPAIR_COLUMN].sum(),
            "Crossings": claims[CROSSING_REPAIR_COLUMN].sum(),
        }
    )
    write_band_table(
        sheet, at, "Repair cost by line ($)", components, MONEY, "Total ($)"
    )
    add_chart(
        sheet,
        "G38",
        title="Repair cost by line ($)",
        first_row=at,
        rows=len(components),
    )


def worked_values(claim: pd.Series, policy: PolicySettings) -> dict[int, float]:
    """Return what the sheet's formulas should come to, for one claim.

    **A mirror of :data:`COLUMN_FORMULA` in Python**, and the reason it exists
    is that those formulas are a second implementation of the Act's arithmetic.
    Nothing stops `landloss.loss.settlement` changing and the spreadsheet going
    on quietly computing the old rule -- which nearly happened when the excess
    stopped being per dwelling. :func:`check_formulas_against_the_model` runs
    this against what the module settled and refuses to stay silent if they
    have parted company.

    Args:
        claim: One row of step 1's settlements.
        policy: The settings this scenario runs under.

    Returns:
        Column number to value, for the columns that carry a formula.
    """
    dwellings = float(claim["dwelling_count"])
    land_value = min(float(claim["damaged_area_m2"]), policy.area_cap_m2) * float(
        claim["land_rate_incl_gst_nzd_per_m2"]
    )
    udv = float(claim[RW_UDV_COLUMN])
    to_cap = min(
        udv, policy.retaining_wall_sub_cap_nzd * (1.0 + policy.gst_rate) * dwellings
    )
    cap = land_value + to_cap
    payable = min(float(claim["repair_cost_incl_gst_nzd"]), cap)
    excess = float(policy.excess_nzd(payable, dwellings))
    settlement = max(0.0, payable - excess)
    return {
        5: land_value,
        7: to_cap,
        8: cap,
        10: payable,
        11: excess,
        12: settlement,
    }


def check_formulas_against_the_model(chosen: pd.DataFrame, policy: PolicySettings):
    """Print whether the sheet's formulas still agree with what was settled.

    The formulas cannot be evaluated here -- openpyxl writes them as text and
    Excel computes them on open -- so what is checked is the arithmetic they
    encode, mirrored by :func:`worked_values`, against the cap, excess and
    settlement the module itself produced.

    Args:
        chosen: The claims the sheet shows.
        policy: The settings this scenario runs under.

    Returns:
        The worst disagreement in dollars.
    """
    against = {
        8: "land_cover_cap_incl_gst_nzd",
        11: "excess_nzd",
        12: "settlement_incl_gst_nzd",
    }
    worst = 0.0
    for _, claim in chosen.iterrows():
        worked = worked_values(claim, policy)
        for column, settled in against.items():
            worst = max(worst, abs(worked[column] - float(claim[settled])))
    if worst > 0.01:
        print(
            f"  WARNING: the sheet's formulas and the settlement module differ "
            f"by up to ${worst:,.2f}. COLUMN_FORMULA is out of date."
        )
    else:
        print(f"  Formulas agree with the model to ${worst:,.6f} at worst")
    return worst


def write_calculation(sheet, chosen: pd.DataFrame, policy: PolicySettings) -> None:
    """Write the twenty-claim table, under its own copy of the settings."""
    write_settings(
        sheet,
        policy,
        subtitle=(
            "Twenty claims chosen to show one of each case, not sampled at "
            "random. Yellow cells are the policy settings the run used."
        ),
    )

    for index, (label, _, _, width) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=HEADER_ROW, column=index, value=label)
        cell.font = HEAD
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.column_dimensions[get_column_letter(index)].width = width
    note = sheet.cell(row=HEADER_ROW, column=len(COLUMNS) + 1, value="Why this claim")
    note.font = HEAD
    note.fill = HEAD_FILL
    sheet.column_dimensions[get_column_letter(len(COLUMNS) + 1)].width = 28
    sheet.row_dimensions[HEADER_ROW].height = 30

    for index in range(1, len(COLUMNS) + 1):
        cell = sheet.cell(
            row=HEADER_ROW + 1, column=index, value=WORKED_FORMULA.get(index, "")
        )
        cell.font = Font(name=FONT, size=8, italic=True, color="808080")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[HEADER_ROW + 1].height = 26

    for offset, (claim_id, claim) in enumerate(chosen.iterrows()):
        row = FIRST_DATA_ROW + offset
        for index, (_, source, fmt, _width) in enumerate(COLUMNS, start=1):
            if index in COLUMN_FORMULA:
                cell = sheet.cell(
                    row=row, column=index, value=COLUMN_FORMULA[index].format(r=row)
                )
                cell.font = WORKED
            elif source == "claim_id":
                cell = sheet.cell(row=row, column=index, value=str(claim_id))
                cell.font = TEXT
            else:
                cell = sheet.cell(row=row, column=index, value=float(claim[source]))
                cell.font = INPUT
            if fmt:
                cell.number_format = fmt
            cell.border = EDGE
        case = sheet.cell(row=row, column=len(COLUMNS) + 1, value=claim["case"])
        case.font = NOTE
        case.border = EDGE

    total = FIRST_DATA_ROW + len(chosen)
    sheet.cell(row=total, column=1, value="Total, these 20 claims").font = SECTION
    for index in (5, 6, 8, 9, 10, 11, 12):
        letter = get_column_letter(index)
        cell = sheet.cell(
            row=total,
            column=index,
            value=f"=SUM({letter}{FIRST_DATA_ROW}:{letter}{total - 1})",
        )
        cell.font = SECTION
        cell.number_format = MONEY
    sheet.cell(
        row=total + 2,
        column=1,
        value=(
            "Black cells are live formulas and blue ones are inputs. Change a "
            "yellow setting above -- the excess per dwelling, its ceiling, the "
            "area cap "
            "-- and every row and the totals follow. How a wall was priced is "
            "on the Repair cost tab."
        ),
    ).font = NOTE
    sheet.freeze_panes = sheet.cell(row=FIRST_DATA_ROW, column=2)


# ---------------------------------------------------------------------------
# The Repair cost tab.
#
# Four blocks, in the order a reader works through a claim. Each asks the same
# four questions about one asset -- **what is it, what is it worth, what would
# repairing it cost, and what does it contribute** -- and the last turns the
# three answers into one settlement.
#
# **Every dollar is GST-exclusive** until the settlement block, which is the
# one place GST is added. Two things are deliberately not divided by 1.15: the
# land values, because a market value is not a GST-bearing price and dividing
# one would invent a figure nobody quoted; and the crossing sub-cap, which is a
# limit rather than a priced repair.
# ---------------------------------------------------------------------------

# Where the policy settings live. The Repair cost tab is wide enough without
# its own copy of them, so its formulas reach across to the Calculation tab.
AREA_CAP_REF = f"Calculation!$B${SETTINGS_ROW['area_cap']}"
SUB_CAP_REF = f"Calculation!$B${SETTINGS_ROW['rw_sub_cap']}"
EXCESS_EACH_REF = f"Calculation!$B${SETTINGS_ROW['excess_each']}"
EXCESS_CEIL_REF = f"Calculation!$B${SETTINGS_ROW['excess_max']}"
GST_REF = f"Calculation!$B${SETTINGS_ROW['gst']}"


class Formula(str):
    """A cell the sheet works out for itself.

    The text is a template: ``{key}`` is replaced by the column letter that
    key ended up in and ``{r}`` by the row, so a column can be moved without
    rewriting every formula that points at it.
    """

    __slots__ = ()


LAND_BLOCK = "A. Landslide land damage"
RW_BLOCK = "B. Retaining wall damage"
LIQ_BLOCK = "C. Liquefaction damage"
PAID_BLOCK = "D. What is paid"

# Columns `vul` does not send yet. They are on the sheet because the workflow
# asks for them, and their being empty is the finding rather than an oversight.
PENDING_LAND = "imminent damage is not modelled yet"

# Two figures the sheet needs that the settlement table does not carry: the
# worst liquefaction state on the claim, and the insured ground that state
# damages. Liquefaction arrives without an extent, so the ground it damages is
# the whole of a liquefied polygon -- the scope the Canterbury rates are
# per-property against.
WALL_CAUSE_COLUMN = "wall_damage_cause"
LIQ_STATE_COLUMN = "liq_state_worst"
LIQ_DAMAGED_AREA_COLUMN = "liquefied_insured_area_m2"
PENDING_LIQ = "vul sends liquefaction as a damage state, with no extent"

# key, heading, source, number format, column width. The source is a column of
# the settlement table, a Formula, or None for a column nothing fills yet.
BLOCKS = [
    (None, [("claim", "Claim", CLAIM_ID_COLUMN, None, 38)]),
    (
        LAND_BLOCK,
        [
            ("ls_evac", "Evacuated land (m2)", EVACUATED_AREA_COLUMN, AREA, 13),
            ("ls_inun", "Inundated land (m2)", INUNDATED_AREA_COLUMN, AREA, 13),
            ("ls_imm", "Imminent damage (m2) - not modelled yet", None, AREA, 14),
            (
                "ls_area",
                "Total damaged land (m2)",
                LANDSLIDE_REPAIR_AREA_COLUMN,
                AREA,
                14,
            ),
            ("rate", "Land rate ($/m2)", "land_rate_incl_gst_nzd_per_m2", RATE, 12),
            (
                "ls_value",
                "Value of damaged land ($)",
                Formula("=MIN({ls_area}{r}," + AREA_CAP_REF + ")*{rate}{r}"),
                MONEY,
                13,
            ),
            ("nw_size", "New RTW size", NEW_WALL_SIZE_COLUMN, None, 11),
            ("nw_height", "New RTW height (m)", NEW_WALL_HEIGHT_COLUMN, "0.00", 12),
            ("nw_length", "New RTW length (m)", NEW_WALL_LENGTH_COLUMN, AREA, 12),
            ("nw_cost", "New RTW to hold it ($)", LAND_REPAIR_COLUMN, MONEY, 14),
            ("spoil_m3", "Spoil to clear (m3)", SPOIL_VOLUME_COLUMN, AREA, 12),
            ("spoil_cost", "Spoil removal ($)", SPOIL_REPAIR_COLUMN, MONEY, 13),
            (
                "ls_repair",
                "A. Landslide repair ($)",
                Formula("={nw_cost}{r}+{spoil_cost}{r}"),
                MONEY,
                15,
            ),
        ],
    ),
    (
        RW_BLOCK,
        [
            ("rw_cause", "What damaged it", WALL_CAUSE_COLUMN, None, 18),
            ("rw_size", "RTW size", "wall_size", None, 11),
            ("rw_height", "RTW height (m)", "wall_height_m", "0.00", 12),
            ("rw_length", "RTW length (m)", "wall_length_m", AREA, 12),
            ("rw_rate", "RTW rate ($/m2)", "wall_rate_excl_gst", RATE, 12),
            ("rw_udv", "RTW undepreciated value ($)", None, MONEY, 16),
            (
                "rw_udv_incl",
                "RTW undepreciated value, incl GST ($)",
                Formula("={rw_udv}{r}*(1+" + GST_REF + ")"),
                MONEY,
                17,
            ),
            (
                "rw_new_size",
                "Replacement RTW size, enlarged for a slip",
                REPLACEMENT_WALL_SIZE_COLUMN,
                None,
                14,
            ),
            (
                "rw_new_length",
                "Replacement RTW length (m)",
                REPLACEMENT_WALL_LENGTH_COLUMN,
                AREA,
                13,
            ),
            (
                "rw_new_rate",
                "Replacement RTW rate ($/m2)",
                REPLACEMENT_WALL_RATE_COLUMN,
                RATE,
                13,
            ),
            ("rw_repair", "B. RTW replacement ($)", None, MONEY, 15),
        ],
    ),
    (
        LIQ_BLOCK,
        [
            ("liq_inun", "Inundated land (m2) - not sent", None, AREA, 14),
            (
                "liq_evac",
                "Evacuated land, with lateral spreading (m2) - not sent",
                None,
                AREA,
                17,
            ),
            ("liq_area", "Liquefied land (m2)", LIQ_DAMAGED_AREA_COLUMN, AREA, 13),
            (
                "liq_insured",
                "Total insured land (m2)",
                TOTAL_INSURED_LAND_AREA_COLUMN,
                AREA,
                14,
            ),
            ("liq_state", "Damage state", LIQ_STATE_COLUMN, "0", 10),
            (
                "liq_value",
                "Value of liquefied land ($)",
                Formula("=MIN({liq_area}{r}," + AREA_CAP_REF + ")*{rate}{r}"),
                MONEY,
                13,
            ),
            ("liq_repair", "C. Liquefaction repair ($)", None, MONEY, 16),
        ],
    ),
    (
        PAID_BLOCK,
        [
            ("dwellings", "Dwellings", "dwelling_count", COUNT, 10),
            ("fees", "Professional fees ($)", None, MONEY, 13),
            (
                "repair_excl",
                "Total repair, excl GST ($)",
                Formula("={ls_repair}{r}+{rw_repair}{r}+{liq_repair}{r}+{fees}{r}"),
                MONEY,
                15,
            ),
            ("gst", "GST ($)", Formula("={repair_excl}{r}*" + GST_REF), MONEY, 12),
            (
                "crossing",
                "Culvert or bridge at its sub-cap ($)",
                CROSSING_REPAIR_COLUMN,
                MONEY,
                16,
            ),
            (
                "repair_incl",
                "Total repair, incl GST ($)",
                Formula("={repair_excl}{r}+{gst}{r}+{crossing}{r}"),
                MONEY,
                15,
            ),
            (
                "cap_land",
                "Cap: land value ($)",
                Formula("=MAX({ls_value}{r},{liq_value}{r})"),
                MONEY,
                13,
            ),
            (
                "cap_rw",
                "Cap: RTW value ($)",
                Formula("=MIN({rw_udv_incl}{r}," + SUB_CAP_REF + "*{dwellings}{r})"),
                MONEY,
                13,
            ),
            (
                "cap",
                "Land cover cap ($)",
                Formula("={cap_land}{r}+{cap_rw}{r}+{crossing}{r}"),
                MONEY,
                14,
            ),
            (
                "payable",
                "Cost to pay ($)",
                Formula("=MIN({repair_incl}{r},{cap}{r})"),
                MONEY,
                13,
            ),
            (
                "excess",
                "Excess ($)",
                Formula(
                    "=MIN({dwellings}{r}*"
                    + EXCESS_EACH_REF
                    + ","
                    + EXCESS_CEIL_REF
                    + ")*({payable}{r}>0)"
                ),
                MONEY,
                12,
            ),
            (
                "settle_incl",
                "Settlement, incl GST ($)",
                Formula("=MAX(0,{payable}{r}-{excess}{r})"),
                MONEY,
                15,
            ),
            (
                "settle_excl",
                "Settlement, excl GST ($)",
                Formula("={settle_incl}{r}/(1+" + GST_REF + ")"),
                MONEY,
                15,
            ),
        ],
    ),
]

# One band per block, light enough to read black text on.
BLOCK_FILL = {
    LAND_BLOCK: PatternFill("solid", fgColor="D9E2F3"),
    RW_BLOCK: PatternFill("solid", fgColor="FBE2D5"),
    LIQ_BLOCK: PatternFill("solid", fgColor="D9EDE3"),
    PAID_BLOCK: PatternFill("solid", fgColor="E7E6E6"),
}

# The model carries its money GST-inclusive; the sheet shows it GST-exclusive.
# These are the columns divided on the way out. The division is exact, because
# each was built as an exclusive figure multiplied by the same rate.
DIVIDE_BY_GST = {
    "rw_udv": RW_UDV_COLUMN,
    "rw_repair": WALL_REPAIR_COLUMN,
    "liq_repair": LIQ_REPAIR_COLUMN,
    "fees": FEES_COLUMN,
    "nw_cost": LAND_REPAIR_COLUMN,
    "spoil_cost": SPOIL_REPAIR_COLUMN,
}

BLOCK_HEADER_ROW = 4
REPAIR_HEADER_ROW = 5
REPAIR_FIRST_ROW = 6


def repair_columns() -> dict[str, int]:
    """Return each column's key mapped to the column number it is written in.

    Raises:
        ValueError: If two columns share a heading. The tab is forty columns
            wide and two of them once read "Total damaged land (m2)", one in
            block A and one in block C -- which is long enough to scroll past
            the coloured band that tells them apart, and duly misled the first
            person to read it.
    """
    index = {}
    headings: dict[str, str] = {}
    number = 1
    for _, columns in BLOCKS:
        for key, heading, *_ in columns:
            if heading in headings:
                msg = (
                    f"two columns are both headed {heading!r}: {headings[heading]!r} "
                    f"and {key!r}. A heading has to say which block it belongs to."
                )
                raise ValueError(msg)
            headings[heading] = key
            index[key] = number
            number += 1
    return index


def repair_letters() -> dict[str, str]:
    """Return each column's key mapped to its spreadsheet letter."""
    return {key: get_column_letter(number) for key, number in repair_columns().items()}


def land_areas_by_claim(realisation_id: int, *, pilot: bool) -> pd.DataFrame:
    """Return the landslide extents `vul` sends, summed onto the claim.

    The evacuated and inundated footprints **overlap**, so they are carried
    beside the landslide total rather than being added to make one: the total
    is the union `vul` has already taken, and showing all three is what makes
    the overlap visible instead of implied.

    Args:
        realisation_id: The modelled earthquake.
        pilot: Whether the run is over the small Wellington pilot box.

    Returns:
        The evacuated, inundated and total insured areas per claim.
    """
    land = gpd.read_parquet(loss_input_path("land", realisation_id, pilot=pilot))
    state = land[LIQ_LD_STATE_COLUMN]
    # vul's liquefied area per polygon, summed over the claim, which is what
    # `claims.damaged_area_m2` takes for liquefaction, one polygon at a time.
    land = land.assign(
        **{
            LIQ_DAMAGED_AREA_COLUMN: land[LIQ_LD_AREA_COLUMN].fillna(0.0),
            LIQ_STATE_COLUMN: state.fillna(0.0),
        }
    )
    wanted = [
        EVACUATED_AREA_COLUMN,
        INUNDATED_AREA_COLUMN,
        TOTAL_INSURED_LAND_AREA_COLUMN,
        LIQ_DAMAGED_AREA_COLUMN,
    ]
    by_claim = land.groupby(CLAIM_ID_COLUMN)
    return by_claim[wanted].sum().join(by_claim[LIQ_STATE_COLUMN].max())


REPAIR_NOTES = [
    "",
    "How to read this tab",
    (
        "Each of the first three blocks is one asset, and asks the same four "
        "questions about it: what is it, what is it worth, what would "
        "repairing it cost, and what does it contribute. Block D turns the "
        "three answers into one settlement. Every dollar is GST-exclusive "
        "until block D adds GST once, on the row marked 'GST'."
    ),
    (
        "The land values are the exception and are not GST-exclusive, because "
        "a market value is not a GST-bearing price. The Act caps cover at the "
        "market value of the damaged land, and the repair bill NHC pays "
        "carries GST, so the two sides of MIN(repair, cap) are compared on "
        "the GST-inclusive basis. Whether that is the intended reading is "
        "still open (Q-14)."
    ),
    "",
    "Empty columns, and why",
    (
        "Imminent damage (block A) is not modelled yet. The agreed method is "
        "a second polygon of similar size centred on the same failure, its "
        "extra ground taken upslope to a new headscarp, with only the newly "
        "evacuated area counting. It belongs to vul and is calibrated off the "
        "claims reports."
    ),
    (
        "The three liquefaction extents (block C) are empty because vul sends "
        "liquefaction as a damage state with no footprint at all. Lateral "
        "spreading is being modelled as a magnification of the probability of "
        "states 4 to 6 near waterways, which moves a property's state rather "
        "than drawing an area -- so these columns may never be fillable in "
        "the form the heading implies."
    ),
    "",
    "Assumptions behind each figure, to be confirmed",
    (
        "A1. One wall stands on a property, so a claim is charged for one "
        "wall. Where a retaining wall is already there it is taken to be "
        "damaged and is replaced, and that replacement in block B is the whole "
        "of the wall cost -- block A is empty. Where there is no wall, one is "
        "invented to hold the ground and block B is empty. The two never both "
        "appear (decided 2026-09-29)."
    ),
    (
        "A2. An invented wall is sized on the total damaged land -- the union "
        "of the evacuated and inundated footprints -- and on the deposit "
        "volume where an inundated depth gives one. Its length is twice the "
        "failure's depth plus 2 m at each end, never under 5 m. It is a "
        "remediation cost, not an asset, so it never reaches the cap: a wall "
        "that did not exist has no undepreciated value to contribute."
    ),
    (
        "A3. Spoil is cleared at the costing tool's own rate, 'Clear site: "
        "Load, cart and tip material', $150 per cubic metre excluding GST. The "
        "same volume also sets the earthworks rating, which is worth watching "
        "for a double count."
    ),
    (
        "B1. A wall already on the property is replaced rather than repaired: "
        "partial repair is about 1% of cases and is not modelled. Where the "
        "claim also has landslide ground, this replacement holds it, and no "
        "second wall is priced in block A."
    ),
    (
        "B2. Nothing says which of the tool's 29 construction types a wall is, "
        "so 30% are priced as Reinforced Concrete and the rest take one of "
        "four timber pole rates, drawn by hashing the wall id. The replacement "
        "carries the site multiplier and a 20% allowance for being built to a "
        "better standard than the one that failed; the undepreciated value "
        "carries neither, which is the whole of the difference between them."
    ),
    (
        "C1. Canterbury settled costs per property, $200 to $4,000 by damage "
        "state, in 2010/2011 dollars and NOT yet inflated. They exclude ILV "
        "and IFV, so they are the minor-damage tier only. The cap the state "
        "is compared against is the land rate over the liquefied land: "
        "evacuated plus inundated, less the share of the evacuated assumed "
        "to overlap (L-44), no more than the insured area."
    ),
    (
        "D1. The six professional fees from the tool's fee table, $5,100 "
        "excluding GST, charged once on a claim that involves a wall and added "
        "before the site multiplier, so a difficult site costs more to design "
        "as well as to build. Mileage is excluded, and they never reach the "
        "undepreciated value."
    ),
    (
        "D2. The retaining wall's contribution is the LESSER of its "
        "undepreciated value and the sub-cap, and the Act states that sub-cap "
        "as $50,000 plus GST per dwelling -- $57,500 for one. So this is the "
        "one place the cap carries GST, and the undepreciated value is grossed "
        "up in block B to be compared on the same basis. The land value beside "
        "it is a market value and carries none, which is why the cap is a sum "
        "of two different bases: that is the Act's construction, not a choice "
        "made here."
    ),
    (
        "D3. Nothing prices a culvert or bridge, so a damaged one is assumed "
        "to exceed its sub-cap and is settled at the limit -- which is why it "
        "appears on both sides and carries no GST line of its own."
    ),
    (
        "D4. The cap's land value is the LARGER of block A's and block C's, "
        "not their sum. A section that both liquefied and was buried is one "
        "piece of damaged ground, and adding the two would value some of it "
        "twice."
    ),
    (
        "D5. MIN(repair, cap) is taken once, at claim level, over every asset "
        "together. The excess is $500 per dwelling, capped at $5,000, and a "
        "claim paid nothing is charged nothing."
    ),
    "",
    (
        "The three site ratings that mark up a wall's cost -- construction "
        "access, earthworks and constructability -- are proxied off driveway "
        "length, inundated volume and ground slope. All bands are invented. "
        "Together they can move a wall cost by at most 30%."
    ),
]


def write_repair_cell(cell, claim, *, key, source, fmt, row, letters, gross):
    """Write one cell of the Repair cost tab, whatever kind of column it is.

    Four kinds. A :class:`Formula` is written as text for Excel to work out. A
    source of ``None`` leaves the cell empty, which is what a column `vul` does
    not fill yet looks like. A money column the model carries GST-inclusive is
    divided on the way out. Anything else is written as it is read.

    Args:
        cell: The cell to write.
        claim: The claim's row of the settlement table.
        key: The column's key, which formulas refer to it by.
        source: Where the value comes from, or None for a column nothing fills.
        fmt: The number format, or None for a text column.
        row: The sheet row, for a formula that refers to its own.
        letters: Every column key mapped to its spreadsheet letter.
        gross: One plus the GST rate.
    """
    if isinstance(source, Formula):
        cell.value = source.format(r=row, **letters)
        cell.font = WORKED
    elif key in DIVIDE_BY_GST:
        # The model carries these GST-inclusive and the sheet shows them
        # without it. DIVIDE_BY_GST names the source, so these pass None above
        # -- and this branch has to come first, or they are written empty.
        cell.value = float(claim[DIVIDE_BY_GST[key]]) / gross
        cell.font = INPUT
    elif source is None:
        cell.font = INPUT
    elif fmt is None:
        value = claim.name if key == "claim" else claim[source]
        cell.value = "" if pd.isna(value) else str(value)
        cell.font = TEXT
    else:
        value = claim[source]
        cell.value = None if pd.isna(value) else float(value)
        cell.font = INPUT
    if fmt:
        cell.number_format = fmt


def write_repair(sheet, chosen: pd.DataFrame, policy: PolicySettings) -> None:
    """Write each claim's repair cost as four blocks, one per asset.

    Args:
        sheet: The worksheet to write into.
        chosen: The claims the sheet shows, with the land extents joined on.
        policy: The settings this scenario runs under.
    """
    sheet["A1"] = "What is damaged, what it is worth, what repairing it costs"
    sheet["A1"].font = TITLE
    sheet["A2"] = (
        "One asset per block. Every dollar excludes GST until block D adds it "
        "once; the land values are market values, to which GST does not apply."
    )
    sheet["A2"].font = NOTE

    letters = repair_letters()
    gross = 1.0 + policy.gst_rate

    number = 1
    for title, columns in BLOCKS:
        first = number
        for key, heading, source, fmt, width in columns:
            cell = sheet.cell(row=REPAIR_HEADER_ROW, column=number, value=heading)
            cell.font = HEAD
            cell.fill = HEAD_FILL
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            sheet.column_dimensions[get_column_letter(number)].width = width

            for offset in range(len(chosen)):
                row = REPAIR_FIRST_ROW + offset
                write_repair_cell(
                    sheet.cell(row=row, column=number),
                    chosen.iloc[offset],
                    key=key,
                    source=source,
                    fmt=fmt,
                    row=row,
                    letters=letters,
                    gross=gross,
                )
            number += 1

        if title:
            sheet.merge_cells(
                start_row=BLOCK_HEADER_ROW,
                start_column=first,
                end_row=BLOCK_HEADER_ROW,
                end_column=number - 1,
            )
            band = sheet.cell(row=BLOCK_HEADER_ROW, column=first, value=title)
            band.font = SECTION
            band.fill = BLOCK_FILL[title]
            band.alignment = Alignment(horizontal="center", vertical="center")

    sheet.row_dimensions[BLOCK_HEADER_ROW].height = 18
    sheet.row_dimensions[REPAIR_HEADER_ROW].height = 52
    sheet.freeze_panes = sheet.cell(row=REPAIR_FIRST_ROW, column=2)

    start = REPAIR_FIRST_ROW + len(chosen) + 2
    for offset, text in enumerate(REPAIR_NOTES):
        cell = sheet.cell(row=start + offset, column=1, value=text)
        bold = text in {
            "How to read this tab",
            "Empty columns, and why",
            "Assumptions behind each figure, to be confirmed",
        }
        cell.font = Font(name=FONT, size=9, bold=bold)
        cell.alignment = Alignment(wrap_text=True, vertical="top")


def check_repair_against_the_model(chosen: pd.DataFrame, policy: PolicySettings):
    """Print whether the Repair cost tab's formulas still settle as the module does.

    The tab is a third implementation of the Act's arithmetic, after the module
    and the Calculation tab, and it reaches the settlement by a different route
    -- building the repair cost up from four blocks rather than reading it
    whole. That makes it worth checking on its own.

    Args:
        chosen: The claims the sheet shows.
        policy: The settings this scenario runs under.

    Returns:
        The worst disagreement in dollars.
    """
    gross = 1.0 + policy.gst_rate
    worst = 0.0
    for _, claim in chosen.iterrows():
        excl = (
            float(claim[LAND_REPAIR_COLUMN])
            + float(claim[SPOIL_REPAIR_COLUMN])
            + float(claim[WALL_REPAIR_COLUMN])
            + float(claim[LIQ_REPAIR_COLUMN])
            + float(claim[FEES_COLUMN])
        ) / gross
        repair = excl * gross + float(claim[CROSSING_REPAIR_COLUMN])

        area_cap = policy.area_cap_m2
        rate = float(claim["land_rate_incl_gst_nzd_per_m2"])
        ls_value = min(float(claim[LANDSLIDE_REPAIR_AREA_COLUMN]), area_cap) * rate
        liq_value = min(float(claim[LIQ_DAMAGED_AREA_COLUMN]), area_cap) * rate
        cap = (
            max(ls_value, liq_value)
            + min(
                float(claim[RW_UDV_COLUMN]),
                policy.retaining_wall_sub_cap_nzd
                * gross
                * float(claim["dwelling_count"]),
            )
            + float(claim[CROSSING_REPAIR_COLUMN])
        )
        payable = min(repair, cap)
        excess = float(policy.excess_nzd(payable, float(claim["dwelling_count"])))
        worst = max(
            worst,
            abs(repair - float(claim["repair_cost_incl_gst_nzd"])),
            abs(cap - float(claim["land_cover_cap_incl_gst_nzd"])),
            abs(max(0.0, payable - excess) - float(claim["settlement_incl_gst_nzd"])),
        )
    if worst > 0.01:
        print(
            f"  WARNING: the Repair cost tab and the settlement module differ "
            f"by up to ${worst:,.2f}. BLOCKS is out of date."
        )
    else:
        print(f"  Repair cost blocks agree with the model to ${worst:,.6f} at worst")
    return worst


def wall_damage_cause(damaged: pd.DataFrame) -> pd.Series:
    """Return what damaged each wall, as words rather than three flags.

    **A retaining wall is most often damaged by shaking alone**, with no
    landslide anywhere near it: on the pilot that is 530 of the 532 damaged
    walls. Without this column the tab shows a claim with no landslide ground
    being charged for a wall and gives no hint why, which reads as an error and
    is not one.

    Args:
        damaged: The damaged rows of the contract's retaining wall table.

    Returns:
        A cause per row, in the order given.
    """
    named = {
        IS_DAMAGED_BY_SHAKING_COLUMN: "shaking",
        IS_EVACUATED_COLUMN: "evacuated",
        IS_INUNDATED_COLUMN: "inundated",
    }
    causes = pd.Series("", index=damaged.index, dtype=object)
    for column, label in named.items():
        flagged = damaged[column].to_numpy(dtype=bool)
        causes = causes.where(
            ~flagged, causes.str.cat([label] * len(causes), sep=" + ").str.strip(" +")
        )
    return causes


def wall_shape(realisation_id: int, *, pilot: bool) -> pd.DataFrame:
    """Return the size, length and rate of each claim's damaged walls.

    One wall per property today, so these are that wall's. Where a claim carries
    several, the lengths add and the size and rate shown are the largest, which
    makes the Repair cost tab's wall figures an approximation on that claim.

    Args:
        realisation_id: The modelled earthquake.
        pilot: Whether the run is over the small Wellington pilot box.

    Returns:
        A frame indexed by ``claim_id``.
    """
    rw = gpd.read_parquet(loss_input_path("rw", realisation_id, pilot=pilot))
    damaged = loss_claims.damaged_walls(rw)
    order = pd.Categorical(
        damaged[RW_SIZE_COLUMN], categories=list(BETA_SIZE_CLASS_HEIGHT_M), ordered=True
    )
    damaged = damaged.assign(
        _order=order,
        _rate=beta_wall_rate_excl_gst_nzd_per_m2(
            damaged[RW_ID_COLUMN].to_numpy(),
            beta_wall_height_m(damaged[RW_SIZE_COLUMN].to_numpy()),
        ),
        _cause=wall_damage_cause(damaged),
    )
    grouped = damaged.groupby(CLAIM_ID_COLUMN)
    out = pd.DataFrame(
        {
            "wall_size": grouped["_order"].max().astype(str),
            "wall_length_m": grouped[RW_LENGTH_COLUMN].sum(),
            "wall_rate_excl_gst": grouped["_rate"].max(),
            WALL_CAUSE_COLUMN: grouped["_cause"].agg(
                lambda causes: ", ".join(sorted(set(causes)))
            ),
        }
    ).reindex(pd.Index(rw[CLAIM_ID_COLUMN].unique(), name=CLAIM_ID_COLUMN))
    # A property can own a wall that vul finds undamaged. It is not replaced,
    # and its ground -- if any slipped -- gets a wall of its own, so the tab
    # has to tell that apart from a property with no wall at all.
    out[WALL_CAUSE_COLUMN] = out[WALL_CAUSE_COLUMN].fillna("wall present, undamaged")
    return out


def main(*, pilot, realisation_ids):
    """Write the walkthrough for the first realisation asked for."""
    policy = PolicySettings()
    realisation_id = realisation_ids[0]
    claims = pd.read_parquet(settlement_path(realisation_id, pilot=pilot))
    claims = claims.set_index("claim_id")

    walls = wall_shape(realisation_id, pilot=pilot).reindex(claims.index)
    claims["wall_size"] = walls["wall_size"].fillna("none")
    claims["wall_length_m"] = walls["wall_length_m"].fillna(0.0)
    claims["wall_rate_excl_gst"] = walls["wall_rate_excl_gst"].fillna(0.0)
    claims[WALL_CAUSE_COLUMN] = walls[WALL_CAUSE_COLUMN].fillna(
        "no wall on the property"
    )
    claims["wall_height_m"] = (
        claims["wall_size"].map(BETA_SIZE_CLASS_HEIGHT_M).fillna(0.0)
    )
    areas = land_areas_by_claim(realisation_id, pilot=pilot).reindex(claims.index)
    for column in areas.columns:
        claims[column] = areas[column].fillna(0.0)
    chosen = pick_claims(claims)

    book = Workbook()
    # openpyxl writes formulas with no cached result, so a reader that trusts
    # the cache -- Excel included, on first open -- sees nothing in them. This
    # tells Excel to recompute the whole workbook as it loads, which is what
    # makes live formulas usable without a LibreOffice pass over the file.
    book.calculation.fullCalcOnLoad = True
    # Name the tab before writing it. A chart's Reference bakes the sheet title
    # in when it is built, and renaming afterwards leaves every chart pointing
    # at a sheet called "Sheet" that no longer exists -- which draws an empty
    # chart rather than an error.
    overview = book.active
    overview.title = "Overview"
    write_overview(overview, claims, policy)
    write_calculation(book.create_sheet("Calculation"), chosen, policy)
    write_repair(book.create_sheet("Repair cost"), chosen, policy)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / OUT_NAME
    book.save(out_path)
    print(f"Picked {len(chosen)} claims from {len(claims):,}:")
    for case, count in chosen["case"].value_counts().items():
        print(f"  {count:>2} {case}")
    check_formulas_against_the_model(chosen, policy)
    check_repair_against_the_model(chosen, policy)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    main(pilot=config.PILOT, realisation_ids=config.REALISATION_IDS)
