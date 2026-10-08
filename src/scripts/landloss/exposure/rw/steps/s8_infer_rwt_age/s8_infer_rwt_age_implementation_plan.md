# Step 8 — Infer retaining wall age: implementation plan

**Status:** Phases 1 to 4 complete; phase 5 not started.

The step puts a construction age on the retaining walls of every claim property,
in the four bins set out in
`src/landloss/exposure/rw/assets/choice-of-rwt-bin-ages.md`. The age of the
dwelling stands in for the age of its walls, and the dates of the land's title
and survey plan stand in for the age of the dwelling, corrected by rules for
the cases where they are younger or older than the house on them. The rules
are set against Christchurch, the one city with an open District Valuation
Roll giving building age by decade.

## Phase 1 — Sources (complete)

- [x] Read the LINZ NZ Property Titles List table (51567) for `issue_date`,
      through a reader for Koordinates tables, which ttpy does not download
      (`get_koordinates_table`, `get_nz_property_titles_list`). The table is
      read rather than the NZ Property Titles layer (50804): the same titles,
      without the geometry, and with the survey plan reference.
- [x] Read the open District Valuation Roll (114085) for Christchurch's
      `building_age_indicator` (`get_nz_district_valuation_roll`).
- [x] Join titles to claim properties on the comma-separated `title_no` of the
      NZ Property Boundaries layer, over every boundary row on the claim's
      footprint (`footprint_rows`).

## Phase 2 — A first estimate from the title (complete)

- [x] Date each property from its earliest title's issue date, and bin it.
- [x] Measure that first estimate against the Christchurch roll. It put 63% of
      rating units in the right decade, but more than half the pre-1950 houses
      sat on titles issued in 1970 or later: paper titles reissued on a later
      dealing, and infill.

## Phase 3 — Rules for the infill problem and others found (complete)

- [x] Date the deposited plan each lot is on from its number, per land
      district (`fit_dp_years`), and use it for a paper title more than five
      years younger than its plan, read as a reissue.
- [x] Keep a unit title on its own date, where the plan date does worse.
      Cross-leases were first kept on their own date too, and moved onto the
      reissue rule once the check ran on whole claim properties, where the
      lot's oldest building is the house that was there before the flats.
- [x] Date Lot 1 of a two-lot infill plan by its neighbours where it is more
      than 35 years younger than them. A blanket infill rule, every young lot
      among older neighbours taking their date, made the estimate worse in
      every setting tried and was not kept: most such lots carry a new house.
- [x] Date a property with nothing to date it by from its neighbours.
- [ ] Correct a title or plan older than the house on it, where a section stood
      empty or a house was rebuilt. No rule was found: nothing in the titles
      distinguishes a rebuilt house from the original. Over Christchurch this
      is dominated by the post-2010 rebuild (about 6% of claims), which
      Wellington has no equivalent of.
- Dropped: a build lag of one to four years added to a title's date. It
  improved the Christchurch shares only by standing in for the rebuilds, and
  without them even one year made the shares worse
  (`exposure/rw/validations/rwt_age_christchurch.md`).

## Phase 4 — Outputs (complete)

- [x] Write the age per claim property (`gen_rwt_age.py`).
- [x] Tabulate the share of properties in each bin per suburb and per
      territorial authority for the report (`table_rwt_age_by_suburb.py`).
- [x] Check the estimate against Christchurch in
      `exposure/rw/validations/table_rwt_age_christchurch.py`, with its
      findings written beside it.

## Phase 5 — Into the wall model

- [ ] Read the per-property bin onto the candidate wall lines (since
      2026-10-08, step 12's wall units) in place of the
      empty `dwelling_age_decade`, and set `p_poor` from four bins rather than
      the single split at `BUILDING_ACT_DECADE`.

## Potential future improvements

- Replace the title proxy with the District Valuation Roll building age for the
  study area, if NHC or QV can supply it, keeping the same output columns.
- Carry a probability per bin rather than one bin per property. The ambiguous
  cases (a young title on an old plan, a two-lot infill plan) are split rather
  than decided, which would bring the suburb shares closer still.
- Building age is taken as wall age. A wall rebuilt after the house is younger
  than the bin says.
- The plan dates for Wellington are fitted from Wellington's own titles, the
  same way as Canterbury's, but nothing checks them against a known date. A
  handful of subdivisions with documented dates (Churton Park, Whitby) would.
