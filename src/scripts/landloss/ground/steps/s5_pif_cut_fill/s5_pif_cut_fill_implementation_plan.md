# Ground step 5 — Pif cut and fill: implementation plan

**Status:** Phases 1 and 2 complete; phase 3 built (2026-10-06): the
wall units (now exposure rw step 6) read the class into their prior and each
pif's wall height from the pip table. Reporting the drawn walls by class is left.

The step classes every pif of ground step 4 as cut, fill, cut and fill,
uncertain or natural ground, so that the wall probability can read it. It was
landslide step 13 until 2026-10-08, when it moved into the ground module; it
runs after ground step 4 and before the wall units and their prior (exposure rw
step 6, `.agents/plans/placing-retaining-walls-on-pifs.md`). The method was
chosen in `research/cut_fill/pif_cut_fill.md` (the lead,
2026-10-05).

## Phase 1 — Class every pif

- [x] `landloss.hazard.landslide.pif_cut_fill`: the walk to the foot of each
      face, the face mask, the robust anchor fit and the class, as pure
      functions, with unit tests on synthetic slopes (a cut platform, a fill
      pad, a wall, the class rules).
- [x] `gen_pif_cut_fill.py`: reads ground step 4's siz table and ground step 3's DEM, writes the pif
      and pip tables.
- [x] `table_pif_cut_fill_checks.py`: class counts, agreement with the SLIDE cut
      slopes and fill bodies, and the class by ground group.
- [x] Results recorded in the method file.

## Phase 2 — Fast enough for the full extent

- [x] Optimise the research code: the anchor fit fell from about 45 s to under
      10 s over the pilot, with the same classes.
- [ ] Run per territorial authority with ground step 3, tiled, once the per-TA plan
      lands (`.agents/plans/running-per-territorial-authority.md`). The fit
      reads 20 m past each pif, so a tile needs a 35 m margin (the 15 m walk and
      the 20 m fit).
- [x] Read the DEM a block of pifs at a time rather than whole, and take each
      pip's fall direction from the siz table rather than finding the pips
      again (2026-10-09, before the Upper Hutt run); identical classes over
      Porirua.
- [ ] If a full run is too slow, run the blocks over worker processes; each
      needs only its DEM window.

## Phase 3 — Feed the wall probability

The rules are the lead's (2026-10-06), built in
`landloss.hazard.landslide.wall_units.gen_wall_prior`. Every number is a
`BETA_` constant in `landloss.domain.constants` until **T-50** calibrates it.

- [x] A wall unit takes the class of its longest member pif (as it takes its
      ground and height band); where pifs tie for the longest, the tied class
      most of its pifs hold. A GNS-only unit is `unknown`.
- [x] Apply the rock reduction (`BETA_ROCK_CUT_FACTOR`, 0.3) only to class
      `cut` on a rock material taller than the soil cover (over 2.5 m), not to
      every face in rock. Wellington greywacke cuts often stand unsupported at
      55 to 75° [nzgs_2025_torlesse]. A cut in soil keeps its prior.
- [x] Raise the prior on fill and on cut and fill, the front and back of a
      platform [monteith_2020] (`BETA_FILL_WALL_FACTOR`, 1.3), in place of the
      ground map's fill.
- [x] Lower the prior on `natural` (`BETA_NATURAL_WALL_FACTOR`, 0.5); leave
      `uncertain` and `unknown` at the prior from siz and height band alone.
- [x] Each pif's wall height is the 80th percentile of its pips' drops to
      the foot of the face (`gen_pif_wall_heights`, ground step 3's
      `WALL_HEIGHT_QUANTILE`), not its largest pip drop. Superseded
      2026-10-06: the foot walk overstated the height on long batters, and
      ground step 3 now reads each pip's near drop onto the siz
      table (`near_drop_p80_m`); the wall units read only the class from this
      step.
- [ ] Report the drawn walls by class in exposure rw step 6's checks.

## Phase 4 — Improvements

- [ ] A classifier trained on the SLIDE cut slope and fill body polygons
      (research note, "Worth trying next", 2).
- [ ] The GNS 1938 and 1945 surface models, if GNS releases them, for a direct
      sign test on faces taller than their 2.5 m error.
- [ ] Test whether the walk's stop on the next platform biases the class towards
      cut (research note, finding 7).
- [ ] Tune the 1 m natural threshold, the 2σ band and the 20 m radius against
      held-out claims once **T-50** lands.
