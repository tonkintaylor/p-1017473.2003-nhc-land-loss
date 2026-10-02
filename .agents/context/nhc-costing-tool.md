# The NHC costing tool

How NHC prices the repair of damaged land and land structures, captured from the
"Costing tool demo" meeting on 21 September 2026, where Chris Ewens walked the
team through the spreadsheet he assesses claims with. Chris is a cost assessor at
NHC and maintains the rates; John Leeves, Maxim Millen, Virginie Lacrosse and
Perrie Gilbert were on the call.

This is the tool this study's cost model is meant to be compatible with, so the
rates below are the ones our own pricing should reproduce. The spreadsheet itself
had not been released to T+T at the time of the meeting (**T-37**), so everything
here is from Chris's narration of it on screen rather than from the file.

## The three land sheets

Chris described three sheets that "work hand in hand" and between them cover
everything to do with land:

| Sheet | What it does |
| --- | --- |
| Land valuation | Values the land itself. |
| Under-depreciated value | Values a land structure, to identify the land cover cap. |
| Land SOW | The scope of works: builds the repair cost up from scratch. |

**Land SOW is the one that matters most to this study**, because it is where a
repair cost is assembled rather than looked up. Its build-up runs:

- Removing inundation.
- Enabling works — getting machinery and people onto the site.
- Constructing the land structure recommended as the remedial solution, whether
  to prevent imminent damage or to reinstate evacuated land.
- Reinstatement — tidying the site up on the way out.

What goes into it depends on the geotech report.

## Enabling works and reinstatement

These are the site-specific part, and they are **not** built into the retaining
wall rates as a baseline — Chris was explicit that the wall rates carry no
enabling works allowance.

They are priced from the assessor's judgement on site. Chris described his own
method: take a photo from the street, then walk in as if about to do the repair
and note what has to go — a stretch of hedge, a garden shed, a deck — until the
machinery can reach the work. Reinstatement is the same in reverse. Traffic
management is currently the largest single driver, and at the extreme some sites
have needed small diggers helicoptered in and out.

For a Wellington hillside job John asked what the three bands are worth. Chris
gave **nothing for easy, about 15 for moderate and about 30 for difficult** —
but whether those are dollar amounts in thousands or percentage multipliers on
the base cost is **unresolved** (**Q-03**). Maxim asked whether they were
multipliers and Chris agreed they were, while John had been proposing dollar
figures in the same exchange. Nothing should be built on these numbers until the
units are confirmed.

## Excess earthworks and constructability

Two multipliers applied to the Land SOW subtotal, each rated **easy, moderate or
difficult**. The ratings come from a table in the geotech report, near the
geotech fees — John confirmed T+T already supply all three ratings in the duty
report, so this study can generate them rather than having to source them.

The percentages behind the ratings are **unresolved** (**Q-04**). Chris first
described 15% for each of the three, giving 30% or 45% on the subtotal for a
difficult site, then revised it to something closer to 0%, 5% and 10%, and
separately said individual line items in the rates sheet cap out at 30%. The
mechanism is clear; the numbers are not.

Where the ratings themselves come from, once the tool is running at scale, is
flyover or satellite imagery of the property rather than a site visit.

## The `lists` sheet is the rate source

The rates live on a sheet Chris called `lists`, one row per line item with its
rate and its unit — lineal metre, square metre or cubic metre. It holds:

- Retaining wall square-metre rates.
- The components behind them: excavation for various pile types, DCD piles,
  concrete encasement, timber lagging, drain coil, drainage metals, anchors.
- Building rates — ring foundations, labour, plant hire.
- Land rates, which Chris noted are comparatively few.

Rates shaded brown and beige are the ones **Chris updates every four months**;
they are QS-derived, and they are what feeds the costing sheets.

Chris's own suggestion was that T+T pull the rates out of `lists` and build our
own spreadsheet around them — "as long as you're using those rates, that would be
pretty compatible pricing". Maxim agreed to rebuild rather than extend the
existing file (**T-38**), partly on that advice and partly because the workbook
is fragile: it crashes readily, it is easy to break, and the person who built it
took redundancy last year, leaving Chris — a carpenter by trade — as the only
person in NHC who works on it. Chris asked that untouched master copies be kept
when it arrives.

## Two retaining wall calculators, and which one to use

The tool carries both a detailed build-up and a simple square-metre-rate
calculator. **The team agreed to use the simple one**: John said it is
realistically what will be used, and Maxim agreed. The simple calculator already
carries the hazard and the site access, and takes the excess earthworks and
constructability multipliers on top.

The reason is that the study will not know wall dimensions well enough to justify
the detail. John's framing was that with so many unknowns — half the time not
knowing whether a site has a retaining wall at all, let alone its size — there is
no point costing to decimal places. Maxim confirmed the model will run three wall
types with simple numbers.

## Under-depreciated value is not the same as replacement cost

Maxim asked whether the under-depreciated value tables and the Land SOW would
give the same price for the same wall. They will not, and the direction is known:
**under-depreciated value comes out lower.**

- Under the **EQC Act**, a valuer took the structure's condition — a 50 year
  working life, 25 years old — and reverse-engineered a depreciated value.
- Under the **NHC Act**, it is the cost to build from new, but *without* the
  additional items the square-metre rates build into the Land SOW. There are set
  fees for under-depreciated value and the Act leaves it rigid about what is
  allowable.

So the two tables are answering different questions, and the gap between them is
the extras carried by the m² rates rather than depreciation. See
`nhc-land-cover-and-settlement.md` for how each is settled.

## Repair versus replace, for retaining walls

- A **partially damaged wall that would be repaired rather than replaced is
  about 1% of cases** (John), and is not worth modelling (**L-31**).
- A wall **tilted by shaking goes straight to replacement** — once it has tilted,
  it is a replacement job.
- Some walls in the study area will already have been tilted before the modelled
  event, and the study has no way to know which (**L-32**).

## Compliance items on a replacement

Two items get added because current legislation requires them even where the
original wall had neither:

- **Council stormwater connection** — any drainage has to be terminated by the
  contractor at a council connection. In a rural setting it is instead diverted
  away with 50 to 60 metres of drain coil.
- **Fall-from-height barrier** — Chris explicitly grouped the stormwater
  connection with this: there may be no barrier on the existing wall, but one has
  to be installed to comply.

Chris judged the stormwater connection "not so much" a real cost driver, but said
it always has to be considered. What either adds is not known (**Q-05**).

## What this file does not settle

- The units and values of the enabling works bands (**Q-03**) and of the excess
  earthworks and constructability multipliers (**Q-04**).
- What the compliance items add (**Q-05**).
- The actual rates, which arrive with the spreadsheet (**T-37**).
