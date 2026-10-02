The contract between `vul` and `loss` is recorded as `vul` actually sets it, in
`.agents/plans/asset-pricing-approach.md` section 1, replacing the earlier
sketch of one land frame keyed on `address_id` with a row per cause.

`vul` hands over **four tables** — land, retaining walls, culverts and bridges —
each carrying `claim_id` and coordinates. Land is one row per non-overlapping
insured polygon with a `$/m2` market value and the damaged areas named by
mechanism; structures arrive as a damage flag per cause rather than a single
state.

Three things change for `loss`:

- **`claim_id` arrives from upstream.** It is not minted at this boundary, which
  is what **L-11** assumed, so what `loss` owes is the roll-up onto a key it is
  given. `beta-build.md` and the module status are corrected to match.
- **The area cap becomes reachable.** Land carries its area and its rate
  separately, so the lesser of the damaged area and the cap can be valued. A
  pre-multiplied market value, which is what `settle` takes today, discards the
  area the cap needs.
- **A damaged structure is still one replacement.** Walls and bridges each carry
  three flags; since damage is none-or-replace, any flag being true means one
  replacement rather than one per flag.

`loss` can now price a wall straight from what the contract sends.
`landloss.loss.pricing.beta_wall_face_area_m2` turns `rw_size` and `rw_length`
into a wall face, the rate being charged per square metre of it, using a set
height per size class: **0.75 m, 1.75 m and 2.75 m**. Each is the middle of what
its class can contain, the population drawing heights over 0.4 to 3.0 m, and
each classifies back to its own size class — which is what ruled out 1 m for
small, the band being *below* 1 m. A size class therefore carries no variation
of its own, so the spread in wall cost comes from length and the site ratings
alone; adding it back is **I-14** (**Q-08** closed).

Three gaps in the contract are logged rather than assumed away: whether the
landslide area column is already the union of the evacuated and inundated
footprints (**Q-06**), where the dwelling count comes from, both sub-caps and the
excess needing one (**Q-07**), and why culverts and bridges carry different
damage flags (**Q-09**). Bridges do carry a `bridge_id`, confirmed after the
contract was first written, so every table identifies its own asset.
