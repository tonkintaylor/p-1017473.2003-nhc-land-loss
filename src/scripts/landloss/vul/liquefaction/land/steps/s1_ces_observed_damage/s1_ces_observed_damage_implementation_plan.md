# Step 1 — Canterbury observed land damage: implementation plan

**Status:** Phase 4 not started — neither script has been run against the real
data yet. The NLM release pin was consolidated onto `CORE_NLM_VERSION`, which
leaves one open check in phase 1.

## Why this step exists

The vulnerability module needs evidence for how much land damage costs at a
given level of liquefaction demand. The Canterbury earthquake sequence is the
only New Zealand dataset with both settled land claims and mapped land damage
observations, so it is what the Wellington land damage relationships are
calibrated against.

A version of this figure already exists in the National Liquefaction Model loss
repository (`p-1017473-nlm-loss-modelling`), as
`src/scripts/figs/fig_bdr_v_lsn.py`. The figure is worth having here; the way its
database is built is not. There the underlying `bdr_observed_damage_db.parquet`
is the tail of a four script chain that pulls in the NHC building portfolios
through pins, the per-event simulated loss parquets, a QPID-keyed merge with a
100 m spatial fallback, and a KNN imputation of missing building losses. None of
that is needed for a land damage figure, and the last step flattens its spatial
join to a Python dictionary, which silently keeps an arbitrary match where a
property falls inside more than one observation polygon. This step replaces the
chain with a single join from the loss points straight to the observations,
over properties masked to flat land.

## Phase 1 — Pin the National Liquefaction Model release

- [x] The release named once in `src/landloss/domain/constants.py` rather than
      spelled out in every path reaching into its tree. Now `CORE_NLM_VERSION`,
      the single pin the whole study reads the NLM at, chosen from the
      `NlmRelease` enum of the releases the code has been pointed at.
- [ ] Confirm the buffered observations exist under `CORE_NLM_VERSION`. They
      were previously read from an older release, on the grounds that survey data
      does not change when the model is re-run and so is not necessarily carried
      forward. If `fragility/event_obs_buffered_no_map` is absent there, point
      `OBS_DIR` at the `NlmRelease` member that has it.

## Phase 2 — Join the losses to the observations (complete)

- [x] Read the geocoded loss GeoPackage, clean the dollar columns and drop
      unusable QPIDs and geometry (`get_losses` in `gen_observed_damage_db.py`).
- [x] Aggregate to one row per property per event before joining, so a property
      with many claims is joined once.
- [x] Mask the properties to flat land (`mask_to_flat_land`, using
      `CHCH_FLAT_ONLY`), so the reach of the database is a named extent rather
      than the coverage of whatever layer the step joins to.
- [x] Resolve each event's observation vocabulary onto the six land damage
      states (`OBS_HAZ_MAP`, `DAMAGE_STATES`, `get_observed_damage`).
- [x] Join the observations with a worst-state-wins reduction where a property
      falls inside several polygons (`assign_observed_damage`).
- [x] Write `observed_damage_db.parquet`, keeping the geometry.

## Phase 3 — Draw the figure (complete)

The figure was first built as a six panel scatter of settled land damage against
the modelled LSN. The database no longer carries LSN, so it was replaced with a
spatial one: `fig_land_damage_maps.py`, three map panels across the Christchurch
extent showing where each event's damage fell.

- [x] Three map panels, one per event, over the `CHRISTCHURCH` extent
      (`fig_land_damage_maps.py`).
- [x] Properties coloured by land damage state 1 to 6, drawn least damaged first
      so the severe states are not buried (`STATE_COLOURS`, `split_by_state`).
- [x] Ungraded and unsurveyed properties drawn in grey rather than on the ramp,
      which also answers how complete the observation coverage is.
- [x] Shared basemap, north arrow and scale bar through
      `landloss.common.utils.plot.style_basemap_ax`, so the panels match the
      other report maps.
- [x] Diagnostics printed before plotting, so a bad join is caught before a
      figure is believed.

## Phase 4 — First run against the real data

- [ ] Run both scripts and check the counts against what the National
      Liquefaction Model repository asserts about the same source: 327,247 loss
      records, 1,970 with a null QPID, 16,230 with a QPID at or below zero.
- [ ] Confirm the observation match rate is plausible. A near-zero rate means a
      CRS or column name assumption is wrong rather than that the data is sparse.
- [ ] Confirm the flat land mask keeps roughly the share of properties expected.
      The Canterbury claims are overwhelmingly on the plains, so a mask that
      drops most of them means the extent or the flatland read is wrong rather
      than that the claims are on hills.
- [x] Confirm the output location. The database now writes through
      `landloss.io.versioned_store.save_vul` (`OUT_SUB_DIRS`/`OUT_NAME` in
      `gen_observed_damage_db.py`), so it follows the project's versioned data
      store layout rather than a guessed `T:` path.
- [ ] Check the maps against what is known about the sequence: February 2011
      damage concentrated in the eastern suburbs along the Avon, Darfield
      reaching further west, February 2016 much the smaller footprint. A panel
      that does not show that is a join or a CRS problem, not a finding.
- [ ] Check the share of properties landing on states 4 to 6. The split between
      them rests on the `Lateral Spreading` reading of state 5, so if that class
      dominates the top of the scale the reading is doing more work than the
      graded observations are.

## Potential future improvements

- Relate the settled dollars to the state. The maps show where the damage fell
  and the database carries what each property was paid, but nothing yet plots one
  against the other. A distribution of `land_assessment` per damage state is the
  figure that turns this database into a damage relationship, and it is the
  natural successor to the LSN scatter this step used to draw.
- Normalise the damage. Land damage is carried in dollars. A damage ratio against
  the property's land value is the more transferable quantity and what the
  Wellington model ultimately needs, but the NHC extract carries no land value;
  it would have to come from the rating values being sought from the councils,
  joined on QPID.
- Compare assessment against payment. `land_assessment` is what was assessed and
  `land_paid` what was settled, and the two differ where the cap bites. Both are
  carried in the database and neither is yet plotted; comparing them would show
  how much of the Canterbury land loss the cap absorbed, which bears directly on
  the policy settings this study tests.
- Show the sequence as one map rather than three. The three panels are read
  against each other by eye, which makes "damaged twice" hard to see. A single
  panel coloured by the worst state a property reached across the sequence, or by
  how many events damaged it, would answer that directly.
- Build the sloping land counterpart. The database is now masked to
  `CHCH_FLAT_ONLY`, which states limitation L-09 rather than asserting it, but
  the sloping land properties are dropped rather than counted.
  `CHCH_SLOPE_ONLY` exists for exactly this; running the same joins over it
  would show how few sloping land observations the sequence holds, which is the
  evidence behind the limitation rather than a restatement of it.
- Settle the `Minor` mapping with the National Liquefaction Model team. This step
  deliberately departs from their category map, which sends a raw `Minor` to
  their `None Observed` band while sending the numeric code `2` to `Minor`. That
  looks like a defect rather than a judgement, but it has not been confirmed with
  whoever wrote it, and until it is the two studies' figures differ for a reason
  that is in neither method.
- Confirm the mechanism classes with the mapping teams. `Lateral Spreading` is
  read as state 5 and `Liquefaction`/`Liquefaction Ejecta` as state 3, because
  those classes name what was seen rather than how bad it was. Both are
  defensible readings rather than recorded gradings, and between them they may
  carry a large share of the observations, so they are worth putting to whoever
  mapped them.
- Move the figure script into this folder. It sits in
  `src/scripts/landloss/vul/liquefaction/land/report/` because that is where the
  project lead asked for it, which predates the step folder convention in the
  `adding-steps-scripts` skill; the skill would put it here beside the step it
  belongs to.
