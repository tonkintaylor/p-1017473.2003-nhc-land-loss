# Step 8 — Infer retaining wall age: method

- The step puts every claim property with a dwelling in one of four
  construction-age bins, coded in `landloss.exposure.rw.age` (`AGE_BINS`,
  `BIN_START_YEARS`) and justified in
  `src/landloss/exposure/rw/assets/choice-of-rwt-bin-ages.md`. The age of the
  oldest dwelling stands in for the age of the walls. It is run by
  `gen_rwt_age.py`, with the extent set in `config.py`.
- The claim properties are rebuilt from the LINZ NZ Property Boundaries over
  the extent exposure step 3 used, with
  `landloss.exposure.land.extent.build_claim_properties`, so that each carries
  its legal description, title type and footprint. Every claim in the extent is
  dated; only those step 3 counted a dwelling on
  (`dwellings-per-property.parquet`) are written.
- Each title's issue date comes from the LINZ NZ Property Titles List (table
  51567), the same titles as the NZ Property Titles layer (50804) without the
  geometry, read by `landloss.io.readers.get_nz_property_titles_list`. Tables
  are exported through the Koordinates exports API
  (`get_koordinates_table`), because ttpy downloads only layers.
- A claim is dated by the earliest title on its footprint
  (`claim_title_dates`). The titles of a cross-leased or unit-titled lot are
  spread over the boundary rows `build_claim_properties` dissolves, and are
  recovered by matching the footprint (`footprint_rows`).
- The deposited plan a lot is on is dated from its number. `fit_dp_years` fits
  the plan dates per land district from the earliest title on each plan, read
  only off boundaries held on one title over one plan, as a low quantile over
  neighbouring plan numbers forced to rise with the number; `dp_years` reads a
  claim's oldest plan off the fit. The run prints the fitted date of a few plan
  numbers as a check.
- `infer_claim_ages` applies four rules in order, and records the one that set
  each year in `age_basis`. The reasoning and the numbers are in the module
  docstring and constants of `landloss.exposure.rw.age`:
  1. A unit title takes its title's date (`title`).
  2. Any other title, cross-leases included, takes its plan's date where it is
     a paper title more than `REISSUE_MIN_GAP_YEARS` younger than the plan, as
     a reissue (`dp`), and its own date otherwise (`title`).
  3. Lot 1 of a plan of at most `INFILL_MAX_LOTS` lots, dated more than
     `INFILL_MIN_GAP_YEARS` younger than its `NEIGHBOURS` nearest claims, takes
     their median date, as the lot an infill plan leaves the old house on
     (`infill_lot_1`).
  4. A claim with neither a dated title nor a dated plan takes its neighbours'
     median date (`neighbourhood`).
- Each claim is reported in the suburb most of its addresses stand in
  (`claim_suburbs`), read from the address-to-claim mapping step 3 wrote and
  the valued addresses of land value step 2.
- One file is written, `temp/exposure/rwt-age[-pilot].geoparquet`: one row per
  claim with a dwelling, carrying `claim_id`, `dwelling_count`, `title_type`,
  `territorial_authority`, `suburb_locality`, `first_title_no`, `title_year`,
  `title_count`, `dp_year`, `neighbourhood_year`, `est_year`, `age_bin`,
  `age_basis` and the footprint.
- `table_rwt_age_by_suburb.py` writes the report tables
  `rwt-age-by-suburb.csv` and `rwt-age-by-ta.csv` under
  `report/exposure/rw/rwt-age/tab/`: the share of claim properties, not of
  dwellings, in each bin (`bin_shares`), with the undated left out of the
  shares and counted.
- The rules and their numbers were set against Christchurch's open District
  Valuation Roll by `exposure/rw/validations/table_rwt_age_christchurch.py`,
  which scores the coded rules, and each rule switched off, on Christchurch
  claims built the same way. Its findings are in `rwt_age_christchurch.md`
  beside it: without the post-earthquake rebuilds, a property lands in the
  right bin about 78% of the time against a ceiling of about 92%, and a typical
  suburb's share of a bin is within 2 to 3 points of the roll's.
- Over the study area (run 2026-10-02): 132,645 claim properties with a
  dwelling, 91,705 dated by their title, 36,635 by their plan as a reissue,
  3,909 as infill Lot 1s, 387 by their neighbours and 9 not at all. The
  Wellington plan dates fitted from 26,734 plans put DP 10,000 at about 1931,
  DP 30,000 at 1969, DP 60,000 at 1987 and DP 90,000 at 2001. The shares are
  0.52 `pre_1970`, 0.20 `1970_1991`, 0.10 `1992_2004` and 0.19 `2005_on`; per
  territorial authority they are in `rwt-age-by-ta.csv`.

Potential future improvements: see `s8_infer_rwt_age_implementation_plan.md`.
