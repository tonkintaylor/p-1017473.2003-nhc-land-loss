# Step 1 — Free faces: method

- The step builds the layer the lateral spreading zones are buffered from: the
  free faces a spreading block moves towards. It is run by
  `gen_liq_free_faces.py`; the filters are in
  `landloss.hazard.liquefaction.waterways` (`get_free_faces`,
  `assemble_free_faces`).
- **It rebuilds the National Liquefaction Model's own layer**, from
  `lats.gen.waterways.get_major_waterways` on the NLM repository's
  `lateral-spread` branch, with the same sources and the same filters. Decided
  2026-09-25 (register task T-46): every published river layer has oddities, and
  matching the NLM means the two studies buffer the same ground.
- The sources, all LINZ, all read for the run's bounding box:
  - the river name lines (layer 103632), kept where the name contains "river"
    or the `river_section_id` is in `EXTRA_RIVER_SECTION_IDS`. That list is the
    NLM's four features around Bottle Lake in Christchurch, which add nothing
    here, plus this study's Wellington additions (T-48);
  - the topo50 river (50328), lake (50293), swamp (50359) and lagoon (50292)
    polygons, kept where at least `MIN_FREE_FACE_AREA_M2`, 5 ha. The NLM chose
    5 ha by ablation over none, 0.5, 1 and 5 ha, as the threshold giving the
    cleanest distance to damage signal in Christchurch;
  - the topo50 coastline (50258), kept whole.
- Water bodies stay polygons rather than outlines, so a buffer drawn from one
  starts at the water's edge and covers the water itself.
- Every feature carries `wtype` (river, coast, lake, swamp, lagoon — the NLM's
  values), `source` (name line, polygon, coastline) and `name` where its layer
  has one, which is what T-48's review reads.
- The area filter runs on what the bounding box read left, so a lake cut by the
  edge of the box is measured by its part inside. The NLM filters after its clip
  the same way.
- What a run covers is set by `EXTENT` in `config.py`: one of the study's
  extents (`"wlg-pilot"`, `"full"` for the four territorial authorities, clipped
  to their own boundary, and so on), or `"lower-hutt"`, the lower Hutt pilot box,
  for checking. Each writes its own file, named with `extent_suffix` --
  `temp/hazard/liquefaction/free-faces{-pilot,,-lower-hutt}.gpkg` -- and step 2
  reads the one for its own `EXTENT`.
- Every extent is read 200 m wider than itself (`FAR_FIELD_M`), so a free face
  just outside it still puts the ground inside it in the near or middle zone.

## Where it departs from the NLM's layer

- **The Waiwhetū Stream is added by ID** (`WELLINGTON_EXTRA_RIVER_SECTION_IDS`,
  river sections 6818507 and 7212609, 7.5 km). It is named a stream, so the
  NLM's rule leaves it out, but it crosses the liquefiable lower Hutt Valley
  floor to the harbour at Seaview. Included provisionally on 2026-10-02, after
  a QGIS review of the lower Hutt layer, pending Maxim Millen's view (Q-19).

## Checked by eye, lower Hutt, 2026-10-02

- The Hutt River polygon follows the channel reasonably.
- The coastline follows the beach, lying on the sand a little nearer the shore
  than the water, close to where the sand gives way to grass. At Seaview it runs
  out into the water along the edge of the Hutt River polygon at the mouth,
  where it is not a free face; the two buffers overlap there, so it adds no
  ground the river's buffer does not already hold.

## Known departures from the real free faces

- The rule is the NLM's, not a geotechnical judgement: a channel named a
  stream is not a free face here however deep its banks, and a lined drain named
  a river is one however shallow.
- The coast is a free face along its full length, including rock and seawall
  coast that cannot spread. The liquefaction probabilities underneath should
  keep that from mattering, because the buffer modifies a probability and on rock
  that probability is near zero; T-47 is where to check it.
