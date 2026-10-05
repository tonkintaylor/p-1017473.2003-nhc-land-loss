# Step 13 — Pif cut and fill: implementation plan

**Status:** Phases 1 and 2 complete; phase 3, reading the class into the wall
probability, is next.

The step classes every pif of step 12 as cut, fill, cut and fill, uncertain or
natural ground, so that the wall probability can read it. It runs after step 12
and before the wall units and their prior (step 12 phase 4,
`.agents/plans/placing-retaining-walls-on-pifs.md`; exposure rw step 6, phase
2e). The method was chosen in `research/cut_fill/pif_cut_fill.md` (the lead,
2026-10-05).

## Phase 1 — Class every pif

- [x] `landloss.hazard.landslide.pif_cut_fill`: the walk to the foot of each
      face, the face mask, the robust anchor fit and the class, as pure
      functions, with unit tests on synthetic slopes (a cut platform, a fill
      pad, a wall, the class rules).
- [x] `gen_pif_cut_fill.py`: reads step 12's siz table and DEM, writes the pif
      and pip tables.
- [x] `table_pif_cut_fill_checks.py`: class counts, agreement with the SLIDE cut
      slopes and fill bodies, and the class by ground group.
- [x] Results recorded in the method file.

## Phase 2 — Fast enough for the full extent

- [x] Optimise the research code: the anchor fit fell from about 45 s to under
      10 s over the pilot, with the same classes.
- [ ] Run per territorial authority with step 12, tiled, once the per-TA plan
      lands (`.agents/plans/running-per-territorial-authority.md`). The fit
      reads 20 m past each pif, so a tile needs a 35 m margin (the 15 m walk and
      the 20 m fit).
- [ ] If a full run is too slow, split the pifs into spatial chunks over worker
      processes; each chunk needs only its DEM window and face mask.

## Phase 3 — Feed the wall probability

These are for the lead to set. Every number is a `BETA_` constant in
`landloss.domain.constants` until **T-50** calibrates it.

- [ ] A wall unit takes the class of its longest member pif (as it takes its
      ground and height band), or the class covering most of its pips.
- [ ] Lower the prior on a cut, and lower it further on a cut in rock (step 12's
      `ground_group` weak rock). Wellington greywacke cuts often stand
      unsupported at 55 to 75° [nzgs_2025_torlesse], and the engineering advice
      is that most walls hold fill and soil. This sits with the existing rock
      reduction for cuts taller than the soil cover (band 4 and up, over
      2.5 m), not on top of it twice.
- [ ] Keep or raise the prior on fill and on cut and fill, the front and back of
      a platform [monteith_2020].
- [ ] Leave `uncertain`, `natural` and `unknown` at the prior from height and
      ground alone.
- [ ] Report the drawn walls by class in the step 6 checks.

## Phase 4 — Improvements

- [ ] A classifier trained on the SLIDE cut slope and fill body polygons
      (research note, "Worth trying next", 2).
- [ ] The GNS 1938 and 1945 surface models, if GNS releases them, for a direct
      sign test on faces taller than their 2.5 m error.
- [ ] Test whether the walk's stop on the next platform biases the class towards
      cut (research note, finding 7).
- [ ] Tune the 1 m natural threshold, the 2σ band and the 20 m radius against
      held-out claims once **T-50** lands.
