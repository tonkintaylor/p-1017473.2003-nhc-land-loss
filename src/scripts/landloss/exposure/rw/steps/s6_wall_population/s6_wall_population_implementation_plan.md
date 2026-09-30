# Step 6 — Retaining wall population: implementation plan

**Status:** Phases 1, 1b and 1c complete. The probabilities are partly a beta
stand-in; phase 2 replaces them.

## Phase 1 — A population of the right shape (complete)

- [x] Draw at most one wall per insured property, against a slope-driven
      prevalence (`beta_wall_prevalence`).
- [x] Size each wall by retained height and classify it small, medium or large
      on the agreed 1 m and 2.5 m boundaries (`classify_wall_size`).
- [x] Give each wall an initial condition, modern or poor.
- [x] Place each wall as a line along the contour (`wall_lines`).
- [x] Seed the draw from the project realisation stream so it reproduces and
      pairs with the hazards.
- [x] Write one file per realisation with the columns the vulnerability work
      reads.

## Phase 1b — Coverage filter and wall id for the loss contract (complete)

- [x] Keep only the walls that intersect their own claim's insured land
      buffered by 2 m (`keep_walls_on_insured_land`), and print the counts kept
      and dropped (`describe_coverage`).
- [x] Give each kept wall a stable `rw_id`, minted after the filter on walls
      sorted by location (`sort_by_location`, `mint_asset_ids`).
- [ ] Rerun over the pilot box and record the kept and dropped counts in the
      method file.

## Phase 1c — A probabilistic output, then a realisation from it (complete)

The step is split in two so the evidence is read once and any number of
realisations are drawn cheaply from it. `gen_wall_probability.py` writes a
probability per property; `gen_wall_population.py` draws a realisation.

- [x] Write a probability per property: `p_wall`, the retained height as a
      lognormal (`height_median_m`, `height_log_sd`), the probability of each
      size class given a wall (`p_small`, `p_medium`, `p_large`), `p_poor` and
      `length_m` (`wall_probability_table`).
- [x] Read the GNS SLIDE mapped retaining walls as direct evidence of a wall
      (`mapped_wall_length_m`, from `get_gns_slide_morphology`). The mapping is
      one-sided, so it raises a probability and never lowers one.
- [x] Read the GNS SLIDE cut slopes and fill bodies as a lift on prevalence
      (`engineered_share`, from `get_slide_genesis`).
- [x] Read the NLM landform class as a cap on plains and coastal lowlands
      (`landform_at`, from `get_nlm_geomorphology`).
- [x] Draw a realisation from the probability table (`draw_walls`), height from
      the lognormal and class from the height, replacing the deterministic
      height.
- [ ] Rerun over the four territorial authorities, not only the pilot box, and
      record the counts in the method file.
- [ ] Check the expected walls per suburb against the SME estimate once it
      arrives (**T-19**); the combining numbers in `wall_probability.py` are
      judgement until then.

## Phase 2 — Replace the stand-in with the real inference

- [ ] Obtain the SME estimate of wall prevalence by suburb (**T-19**) and
      calibrate prevalence against it, per suburb rather than per slope.
- [ ] Bring the manual mapping study and the remote sensing pilot into the
      repository and train against them.
- [ ] Obtain the ICNZ database and fit the size distribution to it, rather than
      ramping height linearly with slope.
- [ ] Attach a dwelling age attribute to the address spine and set the initial
      condition from it, replacing the even split.
- [ ] Read the Wellington City Council cut-and-fill models and road batter
      geometry, which is where a large share of the walls actually are
      (**T-11**, **T-20**). The GNS SLIDE cut slopes and fill bodies stand in
      for them over Wellington City until then.
- [ ] Fit the mapped-wall probability. The GNS mapping is a subset of the walls
      visible from above, so the fraction of real walls it captures can be
      measured against the manual mapping study rather than fixed at 0.9.
- [ ] Use the GNS 1:50,000 geology (`get_wellington_urban_geology`) as a further
      predictor. Not read yet: nothing says which units carry walls.
- [ ] Allow more than one wall per property. A steep section commonly has
      several, and the sub-cap is per dwelling, so the count matters to the
      settlement.

## Phase 3 — Placement

- [ ] Place a wall on the GNS-mapped line where one is mapped, clipped to the
      property buffer, instead of a synthetic line. The probability already knows
      which properties have one; the geometry does not use it yet.
- [ ] Place a wall where one would actually be — along a cut face, a boundary or
      a driveway edge — rather than centred on the property's own point. The
      current placement gets the orientation right and the position wrong, which
      matters once a wall is intersected against a landslide footprint.

## Potential future improvements

- Name the six wall classes and attach a published fragility curve to each cell
  of the class, size and condition grid. The classes are still unnamed, which is
  the open decision in `../../status.md`.
- Take a wall's length from the mapped length where one is mapped, rather than
  from the area of the section.
- Vary wall length with the frontage of the section rather than with the square
  root of its area.
