# Step 2 — Site class: implementation plan

**Status:** Phases 1 to 5 complete. Site class is from Vs30 alone (**L-38**).

The design is in `.agents/plans/pgv-from-vs30-site-class.md`. The grid this
step writes is the one the shaking demand steps put their demand on: PGV
(step 3) now, and PGA next.

## Phase 1 — Vs30 in (complete)

- [x] Read the Foster et al. (2019) Vs30 model, v18.12, and its ln-standard
      deviation from the data library, windowed to the extent so the ~740 MB
      national layers are never loaded whole.

## Phase 2 — Site class per cell (complete)

- [x] Assign the TS1170.5:2025 Table 3.3 site class per cell from Vs30, with
      Class VII taken as VI.
- [x] Write it on the Vs30 model's own 100 m grid, over the pilot and the four
      territorial authorities.
- [x] Record the Vs30-only classification as a limitation in the docstring, the
      method file and the project register (L-38).

## Phase 3 — PGA on the same grid (complete)

- [x] Put PGA on this grid, taking each cell's class rather than step 1's
      single site class 5 field and `BETA_SITE_CLASS` (step 4). The extent
      (`resolve_extent`) and the reader for this grid (`read_site_class`) now
      live here, for the steps after it.

## Phase 4 — Cells without a Vs30 value (complete)

- [x] Give cells without a Foster Vs30 value the class of the nearest
      classed cell within 200 m, and write a mask of the cells filled.
      Decided 2026-09-30, over leaving them empty or assuming one soft
      class.

## Phase 5 — Cells too far from a classed cell (complete)

- [x] Give the cells still unclassed after the 200 m fill a default Vs30 for
      their majority landslide ground map material
      (`BETA_GROUND_MAP_DEFAULT_VS30_M_S`), and the class of it. Decided by
      the lead 2026-10-06, after a 300 m fill still left reclaimed fill on
      the harbour edge unclassed.
- [x] Replace the filled-cell mask with a source code raster: Foster, nearest
      cell, ground map default, none.
- [x] Run landslide step 4 before the shaking steps in `gen_hazard.main`, and
      stop step 2 with a clear message when the ground map is missing.

## Potential future improvements

- Replace the per-material default Vs30 with mapped or measured values where
  they exist (for example the GNS Wellington site class or CPT-derived Vs30
  on the reclamation), and check the 200 m/s fill value against them.

- Use the Vs30 sigma layer for the multiple site classes of clause 3.1.3.4:
  either the envelope of the classes a Vs30 range spans, or one class drawn per
  realisation.
- Check the site class against mapped geology where Table 3.3's profile
  criteria matter, for example Class I against rock with thin cover, and Class
  V/VI against the soft-soil thickness criteria.
- A figure of its own for the site class, if it comes to be read without PGV
  beside it; for now it is the left panel of step 3's `fig_pgv.py`.
