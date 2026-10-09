# Step 1 — Canterbury observed land damage: method

- The step joins NHC's settled Canterbury earthquake sequence losses to the
  National Liquefaction Model's mapped land damage observations, producing one
  row per insured property per event. It is the only New Zealand dataset holding
  both, and it is the evidence the Wellington land damage relationships are
  calibrated against.
- The three events covered, the raw event string each carries in the NHC extract
  and the observation file that belongs to it are listed in `EVENTS` in
  `gen_observed_damage_db.py`. The observation filenames do not announce which
  event they hold — `CESSept` is Darfield, `CESFeb` is February 2011, `CHCH16` is
  February 2016 — so `EVENTS` is the record of that mapping.
- The National Liquefaction Model release the observations are read from is
  `CORE_NLM_VERSION` in `src/landloss/domain/constants.py`, the single pin every
  part of this study reads the NLM at. The releases themselves are listed in the
  `NlmRelease` enum beside it; if a release ever ships without the buffered
  observations — they are survey data that does not change when the model is
  re-run, so they are not necessarily carried forward — `OBS_DIR` in
  `gen_observed_damage_db.py` names the member that has them, rather than a
  second project-wide constant being reintroduced.
- The loss records are read from the GeoPackage written by
  `../../static_data_gen/gen_ces_loss_data.py`, not from NHC's source CSV, so
  that script runs first. The GeoPackage is fetched from T:'s SourceMaterial
  through `tdrive_sync.get_source_mat` (`LOSS_MAT_PATH` in
  `gen_observed_damage_db.py`), which caches it locally rather than reading
  T: on every run.
- Column names are stripped of the stray whitespace the source carries and
  renamed to snake_case through `COLUMN_MAPPINGS` in
  `gen_observed_damage_db.py`, which is taken from the National Liquefaction
  Model loss repository so the two studies name the same field the same way.
- The dollar columns arrive as text carrying a currency symbol, thousands
  separators and a bare `-` for nil. `to_money` converts them, treating a lone
  dash as nil and leaving a genuine negative — a credit — intact.
- Records outside the three modelled events, records with a null or non-positive
  QPID, and records with missing or empty geometry are dropped by `get_losses`,
  which prints the count dropped at each of those three steps. Empty geometry is
  tested at the shapely level rather than through `GeoSeries.notna`, which warns
  on exactly the case being looked for.
- Records are aggregated to one row per property and event by `get_losses`,
  summing the dollar columns and counting the claims into `n_claims`. Aggregating
  before the joins means a property with many claims is joined once.
- The properties are then masked to flat land by `mask_to_flat_land`, using
  `CHCH_FLAT_ONLY` from `src/landloss/exposure/land/landform.py`. That extent is
  the `CHRISTCHURCH` rectangle in `src/landloss/io/area_of_interest.py` cut down
  to the National Liquefaction Model flatland polygons; the run prints how many
  properties it drops and what share it keeps. Reading the flatland layer needs
  `TNT_KOORDINATES_API_KEY`.
- The mask is what decides the reach of the database, so the extent is named and
  written down rather than inherited from the coverage of whatever other layer
  the step happens to join to. It also states limitation L-09 in code: the
  Canterbury sequence is flat land liquefaction evidence, and the database now
  holds only flat land properties rather than asserting the point in prose.
  `CHCH_SLOPE_ONLY` is the complementary extent — the same rectangle minus the
  flatland polygons — and is what would be used to show how little of the
  sequence bears on the landslide relationships.
- Because the mask comes from the National Liquefaction Model flatland layer, it
  carries that layer's limitation L-16: it is a national-scale generalisation, so
  a property on a small terrace inside a flat suburb is kept or dropped on a
  boundary drawn coarsely.
- Damage is carried as one of the six land damage states, listed with their
  labels in `DAMAGE_STATES` in `gen_observed_damage_db.py`: 1 none observed,
  2 minor, 3 moderate, 4 major, 5 severe, 6 very severe. The state is what the
  observation layers code in `dissolve_col`, so it is kept rather than folded
  into coarser bands — a band can be recovered from a state, but not the reverse.
- Each event's observation layer uses its own vocabulary — numeric severity codes
  for one, damage descriptions for another, liquefaction presence for the third.
  `OBS_HAZ_MAP` in `gen_observed_damage_db.py` resolves all of them onto the six
  states, and `get_observed_damage` prints by name any class the map does not
  cover and leaves those polygons out.
- Two entries in `OBS_HAZ_MAP` are judgements rather than translations, because
  the class names a mechanism rather than a grade. `Lateral Spreading` is read as
  state 5, above a graded `Major` because it is the damage that wrote Canterbury
  properties off, but below an explicit `Very Severe`. `Liquefaction` and
  `Liquefaction Ejecta` are read as state 3.
- The February 2016 layer also carries classes describing something other than
  land damage. Only the liquefaction presence classes in `CHCH16_LIQ_CLASSES` are
  kept, matching the National Liquefaction Model's treatment.
- Properties are joined to the observation polygons by `assign_observed_damage`
  with an intersects spatial join. Where a property falls inside more than one
  polygon the worst state wins, which on a numeric scale is simply the highest.
  `UNKNOWN_RANK` sorts below every state, so an ungraded polygon never displaces
  a graded one. The National Liquefaction Model's build instead flattens the same
  join to a dictionary, which keeps an arbitrary match.
- `OBS_HAZ_MAP` departs from the National Liquefaction Model's map in one place:
  a raw `Minor` is state 2 here, where theirs sends it to its `None Observed`
  band while sending the numeric code `2` to `Minor`. Figures from the two
  studies therefore differ.
- Three outcomes are kept apart, because they say different things. A property
  with a state of 1 to 6 was surveyed and graded. One covered only by ungraded
  polygons has a null `observed_land_damage_state` and an
  `observed_land_damage_category` of `Unknown` — surveyed, could not be graded.
  One no polygon covered is null in both — never surveyed.
- No modelled LSN is attached. The database carries what was settled and what was
  observed on the ground, and nothing from a hazard model, so the extent it
  covers is the mask above rather than the reach of an LSN grid.
- The database is written as `observed_damage_db.parquet` under the vul module's
  `ces_observed_damage` area of the project's versioned data store, through
  `landloss.io.versioned_store.save_vul` (see `OUT_NAME`/`OUT_SUB_DIRS` in
  `gen_observed_damage_db.py`). It is derived and large, so it is regenerated
  rather than committed, and it respects `DATA_VERSION` and local-only working
  mode rather than a fixed `T:` path. `fig_land_damage_maps.py` reads it back
  the same way, through `versioned_store.read_vul`. Its columns are listed in
  `OUTPUT_COLUMNS`, and the geometry is kept so the database can be joined to
  further layers and mapped.
- The observed land damage is mapped by `fig_land_damage_maps.py` in
  `src/scripts/landloss/vul/liquefaction/land/report/`, as three map panels
  across the `CHRISTCHURCH` extent — one per event — with every property drawn at
  its own location and coloured by its land damage state. The figure is written
  to `report/vul/liquefaction/land/fig/`.
- The ramp the panels are coloured with is `STATE_COLOURS` in that script. States
  1, 3, 4 and 6 keep the National Liquefaction Model's colours so a panel reads
  against one from that study; 2 and 5 fill the ramp in between. Ungraded and
  unsurveyed properties are grey rather than any colour on the ramp, so the map
  never implies a severity for either.
- The panels are drawn least damaged first, so the severe states end up on top
  rather than buried under the undamaged majority (`split_by_state`). Map
  furniture — basemap, north arrow, scale bar — comes from
  `landloss.common.utils.plot.style_basemap_ax`, so these panels match the other
  report maps. The basemap is fetched over the network on each run.
- Because the database is masked to flat land, the hills in the panels are empty
  because no property in them is carried, not because none was damaged.
- The Canterbury sequence is dominated by flat land liquefaction damage, so this
  evidence constrains the liquefaction land damage relationship and not the
  landslide relationships. That is limitation L-09 in the project register, and
  the flat land mask is how the database now reflects it.

Potential future improvements: see `s1_ces_observed_damage_implementation_plan.md`.
