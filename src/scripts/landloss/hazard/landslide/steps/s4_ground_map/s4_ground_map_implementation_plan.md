# Step 4 — Ground map: implementation plan

**Status:** Phase 1 complete. The step ran over `SMALL_WLG_PILOT` on
2026-10-02 as part of the whole chain and wrote 19,275 pieces. Two findings
from that run are open: the map stops short of the extent the other steps use,
which left 9,144 urban candidates without a material (fixed by phase 0 of
`.agents/plans/building-face-based-urban-slope-polygons.md`), and SLIDE's mixed
fill classes make 71% of the pilot fill (below). Reviewed against the GNS
literature review on 2026-10-02: three changes are proposed in phase 2 (the
mixed fills, the fill strength, the Wellington Fault sheared zone), all
accepted by the lead on 2026-10-02 and to be built before the faces layer,
because the faces' step test and the wall chain's rock-cut factor read this
map. The two fill changes are built in code (2026-10-02) and wait on a pilot
rerun; the fault zone is not built.

## Background

The urban slope failure and retaining wall models need one non-probabilistic
statement of what the ground is made of, whether it has been cut or filled,
whether it has failed before, how wet it is and how strong it is, read by the
slope candidates (step 6), the wall lines (exposure rw step 6), the slope units
(step 5) and the strength-based models. Section 9 of
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md` sets
the sources and their precedence; sections 3.2, 7.3 and 9 of
`.agents/plans/urban-slope-build-contract.md` fix the columns, the vocabulary
and the function signatures this step is built against.

## Phase 1 — The reconciled map (complete)

- [x] The vocabulary, the source mappings and the precedence in
      `landloss.hazard.landslide.ground_map`: every mapper lists its source's
      classes and raises on a new one; the three genesis tuples partition the
      fifteen genesis types.
- [x] `build_ground_map()`: the union overlay of every source's boundaries
      and the flatland into one planar partition, attributed by
      representative-point lookup in precedence order, with the defaults
      written where no source reaches and water pieces dropped.
- [x] `strength_from_material()` reading `wellington-greywacke-strength.csv`
      through `ASSETS_DIR`, with the pick rule (all three values present,
      `check` false first, published first, file order) and the six picks on
      the committed CSV asserted in the tests.
- [x] `gen_ground_map.py`: reads the seven polygon sources, polygonises the
      NLM groundwater depth over the flat land and the thresholded 30 m
      residual, builds the map, takes the fill thickness as the mean positive
      100 m residual per fill piece, mints `ground_id` by location and writes
      `ground-map[-pilot].geoparquet`.
- [x] `fig_ground_map.py`: material and modification panels.
- [x] Tests on synthetic overlapping sources carrying every vocabulary value,
      the precedence order, the defaults, the water rule, the strength picks
      and the step chain end to end through `main()` on synthetic inputs in a
      temporary directory.

## Phase 2 — The pilot and the full extent

- [x] Run `gen_ground_map.py` over the pilot. Made on 2026-10-02 in the
      whole-chain run: 19,275 pieces.
- [ ] Review the area shares the run prints, the strength row chosen per
      grade, and the two panels of `fig_ground_map.py`.
- [ ] Build the map over the same snapped extent as step 3 and the urban
      candidates, so every candidate has a material (faces plan, phase 0, and
      `.agents/plans/running-per-territorial-authority.md`, phase 0).
- [ ] SLIDE's mixed fill classes, 65% of the SLIDE area over the pilot, are
      mapped to `fill_uncontrolled`. **New mapping (literature review,
      accepted by the lead 2026-10-02), to build before the faces**: the natural material as the
      material, and fill as the modification, so the two are read separately.
      **Built in code on 2026-10-02** (`SLIDE_MATERIALS`, `SLIDE_FILL_TYPES`,
      `modification_from_slide()`, `slide_modification_sources()`, with
      tests); to tick once the pilot is rerun and its fill share recorded in
      the method file.

      | SLIDE `Type` | Material | Modification |
      | --- | --- | --- |
      | Fill | `fill_uncontrolled` (as now) | fill |
      | Mixed fill/rock | `rock` | fill |
      | Mixed fill/colluvium | `colluvium` | fill |
      | Mixed fill/colluvium/rock | `colluvium` | fill |
      | Mixed fill/talus | `colluvium` | fill |
      | Old alluvium (mixed fill) | `alluvium` | fill |

      Why: the class is a map unit, not a statement that the whole polygon is
      fill [townsend_2020], and gully fills in greater Wellington are mostly
      too small to map at all [begg_2000] (`qmap10-2000-F08`). The ground
      that fails under a Wellington fill is the contact with what lies
      beneath, the buried colluvium in particular, which is weaker than the
      fill above it [brown_larkin_2005; lyndsell_2019; monteith_2020]
      (`sr2019-040-F04`, `sr2019-051-F15`), so the colluvium takes precedence
      over rock where the class names both. Today's mapping makes 71% of the
      pilot fill, which puts Kingsbury's geology factor at its top over most
      hillsides and leaves almost no rock for the wall chain's rock-cut factor
      to act on (exposure rw step 6), against the advice that steep greywacke
      often stands unsupported [nzgs_2025_torlesse] (`nzgs2025-u7c2-F25`).
      To build it, the SLIDE materials layer becomes a modification source
      too, below the SLIDE genesis and the WCC areas in precedence, and the
      fill thickness from the 100 m residual applies to every piece whose
      modification is fill, as it does now.
- [ ] **The fill strength pick** (accepted, 2026-10-02). What the strength is
      for: `c_kpa`, `phi_deg` and `unit_weight_kn_m3` are written onto every
      piece but read by nothing today. The faces' step test does not read
      them (it uses fixed angles); the faces plan's phase 3 wedge,
      `H x tan(45 - phi'/2)`, will, as would a strength-based large model
      after Godt et al. [godt_2008]. Every fill material reads S48, φ′ 45.7° and
      c′ 0 from one Orchy Crescent sample's first shear stage. The fills in
      those tests densified and strengthened over successive stages and show
      no clear peak, so the values are maxima over a limited displacement, and
      the report does not say which stage stands for the field
      [lyndsell_2019] (`sr2019-040-F07`). Proposed: S52, the set GNS supplied
      for Wellington greywacke-derived fill in the Priscilla and Orchy
      analyses, 22 kN/m³, c′ 2 kPa, φ′ 42° [monteith_2020] (`sr2019-051-F14`),
      with Brown and Larkin's best estimate for a compacted Wellington fill,
      φ′ 32° and c′ 5 kPa [brown_larkin_2005] (`brown2005-F11`), as the low
      case. The pick rule takes file order among equal rows, so the change is
      either a `check` true on S48 or an explicit pick per grade; the picks
      asserted in `test_ground_map.py` change with it. **Built in code on
      2026-10-02** as an explicit pick, `STRENGTH_GRADE_PICKS = {"FILL":
      "S52"}`, because a `check` true on S48 would hand the pick to S49, the
      next unflagged complete row, not S52; to tick with the pilot rerun.
      Colluvium reads S08
      (Careys Gully, φ′ 30°, c′ 2 kPa); the colluvium under the Orchy fill,
      S53, φ′ 23.7° and c′ 18.3 kPa, is the competing value where colluvium
      sits under fill, and is marked `check` true today.
- [ ] **The sheared zone of the Wellington Fault.** Grant-Taylor puts
      intensely sheared greywacke, with planes of weakness at many angles, in
      a zone about half a mile (0.8 km) wide westward from the Wellington
      Fault [grant_taylor_1964] (`granttaylor1964-F16`), and investigations
      near the Wellington, Ohariu, Moonshine and Pukerua Bay faults commonly
      meet crushed, sheared, weak mudstone and siltstone [nzgs_2025_torlesse]
      (`nzgs2025-u7c2-F08`). Proposed: rock within 0.8 km west of the mapped
      Wellington Fault trace becomes `rock_crushed`, and a narrower band, its
      width judgement, along the other three. Needs the active fault traces as
      a source; the 1:50,000 geology may already carry them.
- [ ] The full extent. The fill thickness burns every fill piece onto the 1 m
      residual grid at once, which the 59 by 54 km study area cannot carry in
      memory; tile the residual read by step 3's output tiles, or by a
      regular grid of the map's pieces, before a full run.
- [ ] Decide the material for the NLM classes that occur nationally but not in
      the Wellington extents (`Melange`, `Estuarine`, `Alluvial fan and
      plains`, `Glacial till`, the beach and marine terrace classes): the
      mapper raises on them today, which is right while none reaches the
      study area.

## Phase 3 — Sources not yet read

- [ ] QMAP [begg_2000] outside the 1:50,000 geology, for the parts of Upper
      Hutt and Porirua the urban map does not reach; no reader exists, so the
      material there is `unknown` today.
- [ ] Weathering grade from New Zealand Geotechnical Database boreholes
      interpolated into a depth-to-grade surface, which would let `rock`
      become `rock_uw_mw` or `rock_hw_cw`, and the depth-to-rock observations
      already compiled in `wellington-greywacke-depth-to-rock.csv`. The faces'
      step test reads NZGS Figure 35 by weathering grade (faces plan,
      phase 1), so this decides the angle each rock face is tested at. Until
      it is built, a landform proxy has published support: cuts on flattened
      hilltops and the peneplain expose highly or completely weathered weak
      greywacke, while sharp ridgelines, valleys and coastal platforms expose
      slightly weathered strong rock, and gully slopes weather shallower than
      ridge tops [nzgs_2025_torlesse] (`nzgs2025-u7c2-F01`); weathering
      reaches 50 m under the K-surface at Quartz Hill [begg_2000]
      (`qmap10-2000-F18`). Step 3's topographic position and slope could
      carry that rule; no thresholds are published for it.
- [ ] Whether a fill is engineered, from its age. NZ earthfill standards did
      not exist until the mid-1970s [monteith_2020] (`sr2019-051-F06`),
      suburb-scale earthworks followed the machinery of the 1950s
      [lyndsell_2019] (`sr2019-040-F28`), and non-engineered fills and pre-1960
      cuts are a sign of future failure [nzgs_2025_recognition]
      (`nzgs2025-u2-F09`). Fills certified under NZS 4431:1989 likely had no
      earthquake analysis either [brown_larkin_2005] (`brown2005-F35`), so a
      later date makes a fill engineered, not seismically designed. Read from
      exposure rw step 8's age bin once it is on the claim properties.
- [ ] The harbour reclamation extent, so `reclamation` is reached; no source
      names it today.
- [ ] The GNS fill and colluvium strengths (`sr2019-040-F01` to `F05`,
      `sr2019-051-F14`, `F15`) as a competing pick for the `FILL` and `COL`
      grades: proposed in phase 2 above. These are first-batch findings with
      no independent check; read each value off its table before adopting it.
      The colluvium envelope EN1418a is φ′ 27.9° and c′ 28.3 kPa; the report's
      Table A4.6 swaps the two (`sr2019-040-F35`).

## Potential future improvements

- Carry the mapper's confidence per polygon rather than per source; the
  split of the SLIDE materials into three sources by confidence does this for
  the one layer that records a confidence, and a second such layer would need
  the same treatment.
- Fill thickness from boreholes or from the archived WCC earthworks plans
  where they give a depth, instead of the 100 m residual, which reads a
  natural spur as fill where no mapping says otherwise.
- A representative-point lookup attributes a sliver by one point; an area
  weighted rule would be more robust where a source boundary is drawn a few
  metres off another's.
