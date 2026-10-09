A settled claim now says whether each sub-cap bound.
`landloss.loss.settlement.Settlement` carries
`retaining_wall_sub_cap_bound` and `bridge_culvert_sub_cap_bound`, from the new
`structure_sub_cap_bound`, so "how often does the $50,000 sub-cap actually
bite?" is a column rather than something a caller reconstructs. That share is
one of the module's stated validation checks, and it could not be answered from
what `settle` returned before: the contribution is `min(udv, limit)`, so a wall
the sub-cap clipped and a wall worth exactly the limit are the same number, and
telling them apart meant comparing floats for equality.

Binding is strict, matching `capped`: a structure worth exactly the limit had
nothing taken off it and does not count as bound, and an undamaged structure,
whose undepreciated value is zero, never binds.

`Settlement.capped` now says in its docstring how to read it on a claim with no
damaged land. There the cap reduces to the structures' contribution, which is
below the repair cost by construction — undepreciated value excludes the
enabling works, compliance items and site difficulty the repair cost carries —
so `capped` is true of every such claim and distinguishes none of them. What
moves the settlement is the undepreciated value itself, passing through pound
for pound until the sub-cap clips it.
