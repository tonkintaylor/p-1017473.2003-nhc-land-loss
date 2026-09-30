# Step 6 — Retaining wall population: implementation plan

**Status:** Phases 1, 1b and 1c complete, but they put a probability on each
*property*. That is an interim shape: the target is **candidate wall lines, each
with its own probability** (phase 2). The per-property table stays until the
line model replaces it.

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

## Phase 1c — Interim: a probability per property, then a realisation (complete)

**Superseded in shape by phase 2.** A property-level probability cannot say where
a wall is, cannot give a property more than one wall, and places every wall at
the property's own point. It is kept because it carries the structure the
vulnerability work reads, and because its evidence readers are reused.

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

## Phase 2 — Candidate wall lines with a probability on each line

**Identify where walls are, as lines, and give each line a probability.** Nothing
is decided per property. A wall is a located line, so the same line is what the
coverage filter, the landslide footprint intersection and the settlement read.
A property with two or three walls is simply a property with two or three
candidate lines that drew, each with its own height and condition.

Candidate lines come from geometry that marks where a wall could be:

- [ ] The GNS SLIDE mapped retaining walls (`get_gns_slide_morphology`), as
      lines. They are the only observed walls, so they carry the highest
      probability. The mapping is one-sided (visible from above, Wellington City
      only), so it raises a line's probability and never lowers another's.
- [ ] The edges of GNS SLIDE cut slopes and fill bodies and the cut/fill lines in
      the morphology layer (`get_slide_genesis`), where a wall holds the toe or
      crest of the earthwork.
- [ ] Sharp breaks in slope from the GNS morphology, and steps in the DEM, within
      and beside the insured land, for ground the SLIDE mapping does not reach.
- [ ] Section boundaries and road-frontage edges on sloping ground, and driveway
      edges, which is where Wellington walls are usually found: at the edge of
      the section, not the middle of it.
- [ ] Cut-and-fill model and road batter geometry from the councils
      (**T-11**, **T-20**) once obtained.
- [ ] Segment and de-duplicate the candidates so one wall is one line, and record
      which source each line came from.

Each line then takes a probability and a height distribution from the evidence
around it:

- [ ] Start from slope across the line and on the land it would hold up.
- [ ] Read the GNS 1:50,000 geology (`get_wellington_urban_geology`, confirmed
      separate from the QMAP layer). **Steep ground on greywacke at or near the
      surface lowers a line's probability and height**: a rock cut stands
      unsupported and is claimed for spalling or slides, not wall failure (Oriental
      Bay and Evans Bay are the worked examples). Colluvium, fan and fill units
      raise it, because walls there stabilise soil rather than rock. The SLIDE
      interpreted materials layer is the finer statement where it reaches.
- [ ] Cluster retained height just under 1.5 m, the consent threshold, rather than
      a smooth lognormal.
- [ ] Give a property several lines of independent height and construction. A
      property with several walls is not all small or all large.
- [ ] Mark lines on new subdivisions as very likely to have walls.
- [ ] Draw each line independently in the realisation, apart from a property's
      shared initial condition, and write the drawn lines in the shape the
      contract already reads.

And be checked and calibrated against:

- [ ] Obtain the SME estimate of wall prevalence by suburb (**T-19**) and
      calibrate the expected walls per suburb against it.
- [ ] Bring the manual mapping study and the remote sensing pilot into the
      repository, measure the fraction of real walls the GNS mapping captures
      (replacing the fixed 0.9), and train against them.
- [ ] Scan the Wellington NHC claims reports for wall mentions in the site
      description, to estimate how many properties have walls (Perrie's
      extraction).
- [ ] Obtain the ICNZ database and fit the size distribution to it.

## Phase 3 — Initial condition from age

- [ ] Attach a dwelling age attribute to the address spine. Candidate sources are
      the trig-point or aerial-photo route and the building-age dataset the
      vulnerability model was trained on.
- [ ] Set `p_poor` from it, replacing the even split: pre-1990 walls (cast in situ
      concrete gravity walls from the 1970s and 80s) are more likely to be poor
      and replaced, and post-1991 Building Act walls, more often timber anchored,
      tend to be larger.

## Phase 4 — Costing reads the line

- [ ] Take a wall's length from the line. A drawn line has its own length, so
      `length_m` no longer comes from the area of the section.
- [ ] Confirm with the loss team that size class affects costing while initial
      condition only affects the probability of failure.

## Potential future improvements

- Name the six wall classes and attach a published fragility curve to each cell
  of the class, size and condition grid. The classes are still unnamed, which is
  the open decision in `../../status.md`.
- Use houses across gullies, which likely sit on thicker colluvium or fill with
  wetter soils, as a predictor. Not obviously usable, so it is not in phase 2.
- Exclude non-residential properties such as the zoo near Yabby Creek Road with a
  land-use layer rather than by hand, so they draw no lines.
