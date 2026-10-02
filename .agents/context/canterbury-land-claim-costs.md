# Canterbury land claim costs

The cost side of the land damage model is anchored on what NHC actually paid out
for land damage after the Canterbury earthquake sequence. This note records what
that dataset is, what it excludes, and the category system behind it, because
the category numbering is not what it looks like and cost the team time on the
call it came from.

Source: the "Land loss model logic" meeting, 21 September 2026, where Virginie
Lacrosse walked through the data. The transcript is heavily truncated, so
anything below that turns on an exact figure should be confirmed before it is
relied on.

## What the dataset is

- Canterbury earthquake sequence land claims, one row per claim number, carrying
  the amount paid out and the type of damage it was paid out for.
- It covers the **2010 and 2011 events**. It does **not** include the February
  2016 event.
- Amounts are in **2010 and 2011 dollars**, so they need escalating to the study
  date (**L-23**).
- The rates table the team works from is the **December 2016 land liability**
  workbook, summary sheet, columns H to K. Access is restricted and password
  controlled; the team's right to use it for this study still has to be
  confirmed in writing (**T-29**).

## Two different numbering schemes, and they are not the same thing

This is the part that misleads, and it is worth getting the words right because
the team corrected each other on it twice.

**Categories 1 to 7** are **seven forms of visible land damage**, not seven
levels of severity: category 1 is cracking, category 2 is ponding, and so on.
"CUP" in the same data means cracking, undulation and ponding. One property can
carry several categories at once. Categories 8 and 9 are increased liquefaction
vulnerability and increased flooding vulnerability, and the rates exclude them.

**Land damage states 1 to 6** are the severity scale — none through to very
severe — and are what this study predicts. They are *not* categories, and
calling them "category 1 to 6" is the mistake to avoid.

## How the rates were built, and what that costs

The rates come from correlating two datasets that were collected entirely
independently of each other:

- A **per-property field survey** after the Canterbury earthquakes. Surveyors
  recorded what was visible on each property — so many sand boils, cracks with
  their length and width — and NHC settled against those records. A property
  might carry categories 3 and 6 at once.
- A **separate T+T exercise** mapping evidence of liquefaction ejecta street by
  street, grading the severity of what could be seen.

Neither was designed to line up with the other. Correlating them is a judgement
the team made to get a cost per damage state, and the summary table is the
result of that judgement (**L-27**). Anything built on these rates inherits it.

Whether a category 7 genuinely exists is open (**T-28**): the table is titled
"Cat 1 to 7" but its bands stop at 5 or 6.

## What the costs exclude

- **GST.** If results are presented on that basis it has to be stated to NHC
  (**L-24**).
- **ILV and IFV payments** — increased liquefaction vulnerability and its
  predecessor, increased flooding vulnerability. The figures are observed land
  damage only (**L-25**).

Whether they also exclude damage to retaining walls, culverts and bridges is
being confirmed (**T-27**). The call's expectation was that any retaining wall
component bundled into them is small. For retaining walls the project lead
ruled on 2026-10-02 that a wall replaced by shaking on flat land and the
liquefaction land damage on the same claim are not a double count; culverts and
bridges are still open.

## How they are used, and the retaining wall problem

Predicted land damage states are joined to these rates to give a cost per
property on flat land.

Retaining walls are the complication. A property with a wall costs
significantly more to repair, and the Canterbury averages already have that
cost smeared across every property. The team chose to **model retaining walls
separately** and state their additional cost, rather than leave them averaged in
(**T-30**), because averaging hides exactly the thing this study is trying to
size.

## Standing

These rates are **placeholders**. Revalidating them for this study was agreed as
time-permitting rather than planned (**L-26**), so anything built on them
inherits that.
