The vulnerability build now ends in the four tables the loss module reads. Vul
step 10 writes land, retaining wall, culvert and bridge tables for every
realisation to `temp/vul/loss-input-{land,rw,culverts,bridges}-rNNN.geoparquet`
(with a `-pilot` suffix for the pilot), each in EPSG:2193 and keyed on
`claim_id`, the LINZ property set in exposure step 5. The contract column names
live in one place, `landloss.domain.loss_contract`. Exposure now mints a stable
id for every asset (`land_id` in step 5, `rw_id` in step 6 and `crossing_id` in
step 7, which becomes `culvert_id` or `bridge_id` at step 10) and passes on only
insured structures: a retaining wall is kept if it touches its claim's insured
land buffered by 2 m, and a culvert or bridge only if it lies wholly inside it.
Two new landslide steps, step 11 under `vul/landslide/rw` and
`vul/landslide/culverts_bridges`, flag each wall and crossing as evacuated or
inundated. The landslide land step now measures the union of the evacuated and
inundated ground on each land polygon, so the landslide area is no longer a sum
that double counts overlap (**Q-06**). The land table also carries the dwelling
count (**Q-07**) and the culvert table an `is_evacuated` flag beyond the
contract (**Q-09**). Outputs written before this change lack the new ids and
are stale: rerun exposure step 5, then steps 6 and 7, the hazard steps, vul
steps 2, 3, both step 9s and both step 11s, and finally step 10.

The whole chain now runs from one script. `src/scripts/landloss/gen_all.py`
runs exposure, hazard and vul in order through `gen_exposure.py`,
`gen_hazard.py` and `gen_vul.py`, one per module, each taking the extent and
realisations from a `config.py` beside it and stopping at the first step that
fails. The land rate on the insured land is now written both excluding and
including GST, grossed up by `landloss.domain.gst.add_gst`, and only the
inclusive rate is handed to the loss module as the market value. Land off the
liquefaction grid is written as state 1, None, at no cost, rather than as a
missing state. A landslide realisation in which nothing fails now writes an
empty layer, so the vulnerability steps reading it report nothing damaged
instead of stopping on a missing file.
