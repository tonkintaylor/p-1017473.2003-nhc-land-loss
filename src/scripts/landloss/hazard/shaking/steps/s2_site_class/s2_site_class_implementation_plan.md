# Step 2 — Site class: implementation plan

**Status:** Phases 1 and 2 complete. Site class is from Vs30 alone (**L-38**).

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

## Phase 3 — PGA on the same grid

- [ ] Move step 1's PGA onto this grid, taking each cell's class rather than
      the single site class 5 field and `BETA_SITE_CLASS`.

## Potential future improvements

- Use the Vs30 sigma layer for the multiple site classes of clause 3.1.3.4:
  either the envelope of the classes a Vs30 range spans, or one class drawn per
  realisation.
- Check the site class against mapped geology where Table 3.3's profile
  criteria matter, for example Class I against rock with thin cover, and Class
  V/VI against the soft-soil thickness criteria.
- A figure of its own for the site class, if it comes to be read without PGV
  beside it; for now it is the left panel of step 3's `fig_pgv.py`.
