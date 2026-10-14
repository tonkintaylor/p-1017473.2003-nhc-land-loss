# Shaking vulnerability, culverts and bridges: status

**Status:** A damage state is drawn on every structure, but the pilot holds
none, so nothing has run against real rows.

**Updated:** 2026-10-14

## Approach

- A **probability of full replacement** with a damage state drawn against it,
  as for a retaining wall -- but set by the property's liquefaction land damage
  state rather than the ground motion (T-36), because a buried crossing is
  broken by the ground moving around it, not by the shaking.
- Carry **two damage states only, no damage and replace**. A failed crossing is
  rebuilt rather than patched.
- Keep the **kind of structure** on every row. Culverts and bridges share the
  $25,000 sub-cap but are not priced the same, so the loss module needs to tell
  them apart even while the fragility does not.
- Emit **states, not costs**. A written-off crossing is priced from its
  undepreciated value in the loss module.

## Loss contract

What this module owes the culvert and bridge tables `loss` reads, as set in
`.agents/plans/asset-pricing-approach.md` section 1.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Carry `culvert_id` and `bridge_id` through from the exposure module.
  Carried as `crossing_id` and split into the two by `asset` at vul step 10.
- [x] Write culverts and bridges as two tables, at vul step 10.
- [x] Supply `is_damaged` for culverts and `is_damaged_by_shaking` for bridges,
  from `damage_state`: replaced for liquefaction, drawn on the property's land
  damage state (T-36, 2026-10-13). The bridge column keeps its name, liquefaction
  being the shaking's effect on the ground.
- [x] Carry coordinates, as each structure's geometry in EPSG 2193.
- [x] Supply `is_inundated` for both and `is_evacuated` for bridges, from
  `vul/landslide/culverts_bridges` step 11.
- Whether culverts deliberately carry no `is_evacuated` is **Q-09**. Until it
  is settled, culverts also carry `is_evacuated` as an extra column.

## Where it is now

- `steps/s9_structure_damage_state/` reads the crossing population and the
  realisation's PGA field, draws a state per structure and writes it with the
  `crossing_id`, `claim_id`, structure kind, geometry and PGA sampled at the
  structure's representative point.
- The chance of replacement is the one for the property's liquefaction land
  damage state (T-36), 0 to 40%, culverts and bridges alike; nought off the
  liquefaction grid. It replaced the flat 70% on 2026-10-13.
- **The Wellington pilot produces no rows.** The crossing population follows
  named watercourses, and the nearest is some kilometres from the pilot box. The
  step reports that in words rather than as an empty table, but it means the
  code has not been exercised against real structures.

## Next

1. Run over the full study area, where the named watercourse layers do produce
   crossings.
2. Widen the population beyond named watercourses — most private crossings are
   over unnamed drains and gullies.
3. A span per crossing, which the loss module's $15,000 a metre would use in
   place of its 5 m default.
4. A HAZUS PGA fragility for bridges (**T-164**), on the `pga_g` step 9
   already samples, so a bridge can fail from shaking and not only from its
   land damage state -- including on hill land, where it now has a nought
   chance.

## Validation

- The realised share written off against the fragility it was drawn from.
- The split between culverts and bridges against the 80/20 assumption the
  exposure module draws them at.

## Open decisions

- **How the sub-caps interact** when a property carries both a damaged wall and
  a damaged crossing. Recorded as an open question for NHC.
- **Whether the Canterbury land damage rates already include culvert and bridge
  damage** (**T-27**), which would double count them on flat land.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
