# Table: clipped walls and the slip's own new wall (check 6.3)

Run date 2026-10-14. World 0, earthquake 0 (w000-r000). Script:
`src/scripts/landloss/vul/landslide/rw/research/table_clipped_wall_double_count.py`.
Outputs: `temp/vul/research/clipped-wall-double-count/` (`summary.csv`, then
`pairs-`, `claims-` and `samples-<extent>.csv` per extent, and
`example-porirua-wall.csv`).

## Question

Check 6.3 of `.agents/plans/tweaks-to-property-damage.md`. A wall flagged
`is_evacuated` or `is_inundated` and not `is_damaged_by_shaking` is replaced
over its whole length. The slip that clipped it is usually a failure that came
with none of the claim's own walls, so loss s1 also gives it a new wall. Does
one claim pay twice for the same ground, and if so is it one structure or two?

## Method

1. **Settle in memory, no T:.** Each extent is read from `temp/vul`
   (`loss-input-rw`, `loss-input-land`, `wall-landslide-damage`) and
   `temp/hazard/landslide/landslide-realisation-w000-r000-<extent>`. The wall
   repair and the new walls are priced with loss s1's own functions:
   `landslide_failures`, `attach_failures_to_walls`, `replacement_wall_shape`
   (the clipped piece, as `wall_repair_by_claim` prices it) and the
   `land_repair_by_claim` steps kept per failure (`new_wall_costs` in the
   script). The QV land values are not needed: they touch only the land rate
   and the cap. For Upper Hutt and Porirua the wall repair and new wall cost per
   claim agree with the local `settlement-w000-r000-<extent>.parquet` to
   0.0000 NZD. Lower Hutt has no settlement file; the same code settles it, so
   its costs are on the same footing but are not cross-checked.
   Costs are the wall alone including GST and the site multiplier, before
   professional fees, on-costs (mob/demob, PM) and contingency, which loss adds
   on top (roughly 1.8 times for a claim whose only works are walls).
2. **Clipped piece** = a `rw` row with `is_evacuated` or `is_inundated` and no
   `is_damaged_by_shaking`. The stretch inside a slip is the wall line inside
   that slip's evacuated plus inundated ground, by the test of
   `landloss.vul.landslide.flags` (more than 1 cm inside the ground shrunk by
   1 cm; the wall's own polygon never counts).
3. **A pair** is a clipped piece and a new wall (a failure held by no damaged
   wall) on the same claim. A pair is linked when the new wall's slip is one of
   the slips whose ground clips the piece. An unlinked pair is "different
   structures (slip does not touch the wall)" by definition.
4. **Where the new wall stands.** Loss gives a slip's new wall only a length
   (`landslide_wall_length_m`: width plus 2 m a side, at least 5 m) and no
   geometry. The slip's own ground (evacuated and inundated unioned) stands in
   for it. Verdict, for a linked pair:
   - **same structure** if at least **50 %** of the clipped stretch lies within
     **2 m** (`LANDSLIDE_WALL_MARGIN_M`, the margin loss puts on a slip wall) of
     the slip ground's boundary: the stretch lies along the edge the new wall
     would hold;
   - otherwise **different structures (slip clips the wall, not along its
     edge)**: the wall runs through the ground rather than along its edge.

   Also written, not used for the verdict: the share within 1 m and 5 m, the
   maximum and mean distance to the edge, the angle between stretch and edge
   (stretches of 2 m or more), and a new wall of its real length laid along the
   boundary at the point nearest the stretch (minimum and maximum distance,
   share within 2 m).
5. **Apart vs merged cost** (`merged_wall_costs`): for same-structure pairs, the
   cost with the two kept apart (section 6.1's stretch, damaged length plus 2 m
   a side, at least 5 m, plus the slip's own new wall) against one wall that
   holds both, sized as `replacement_wall_shape` sizes a wall against its slip
   (longer of the two lengths, taller of the two heights, at the clipped wall's
   own type rate).

## Result (world 0, earthquake 0)

Claims carrying **both** a clipped wall piece and a new wall. Money is for those
claims (all their clipped pieces and all their new walls), wall only, incl GST.

| | Lower Hutt | Upper Hutt | Porirua |
|---|---|---|---|
| claims with a clipped piece | 791 | 340 | 530 |
| claims with a new wall | 6,653 | 2,955 | 4,808 |
| **claims with both** | **636** | **274** | **410** |
| pairs (piece x new wall) | 1,202 | 574 | 752 |
| pairs where the slip clips the piece | 416 | 181 | 280 |
| claims with a clipping slip | 392 | 161 | 251 |
| clipped wall cost | $16.51M | $7.11M | $10.14M |
| new wall cost | $40.45M | $17.08M | $21.15M |
| total | $56.97M | $24.19M | $31.29M |
| clipped pieces: length / wall line inside a slip's ground | 8,402 m / 2,858 m | 3,639 m / 1,037 m | 5,264 m / 1,582 m |
| new walls' length | 15,562 m | 6,691 m | 8,826 m |
| claims **same structure** | 337 | 148 | 231 |
| claims different (slip clips, not along edge) | 55 | 13 | 20 |
| claims different (slip does not touch) | 244 | 113 | 159 |

A claim takes its best verdict across its pairs. Lengths are the piece lengths
(`rw_length`); inside lengths are measured on the wall line (see the split
caveat).

The money at risk of double charging is the new wall of each same-structure
slip, beside the clipped piece it duplicates:

| | Lower Hutt | Upper Hutt | Porirua |
|---|---|---|---|
| same-structure pairs | 348 | 163 | 252 |
| of which on split walls | 145 | 65 | 107 |
| their new walls (once per claim and slip) | $14.25M | $6.57M | $8.98M |
| the clipped pieces they sit on (once per piece) | $8.53M | $3.88M | $6.01M |

Costing the same-structure pairs three ways (pieces with a single
same-structure slip only: 334, 151 and 234 of them; wall only, incl GST):

| | Lower Hutt | Upper Hutt | Porirua |
|---|---|---|---|
| today: whole piece plus the slip's new wall | $22.20M | $10.46M | $14.50M |
| section 6.1 stretch plus the slip's new wall, kept apart | $18.04M | $8.66M | $11.52M |
| section 6.1 stretch enlarged to hold the slip, one wall | $15.14M | $7.44M | $9.55M |

Sensitivity of the claim count to the 2 m tolerance (50 % share): same-structure
claims at 1 m are 263 / 114 / 178 and at 5 m are 388 / 159 / 250 (Lower Hutt /
Upper Hutt / Porirua), against 337 / 148 / 231 at 2 m.

## Porirua example (wall `4eef7bbf-bfe3-40c4-91eb-a29515837562-RW01`, SP0003334)

**The current local Porirua outputs do not hold it.** Neither the wall nor
SP0003334 is in `temp/vul/loss-input-rw-w000-r000-porirua`,
`temp/exposure/wall-population-w000-porirua` or the current realisation: the
world has been redrawn since 2026-10-11. The 2026-10-11 run is saved at
`temp/versions/porirua/v3-20261011/`, so the example is read from that (type and
height from its wall population; site ratings from the current exposure, which
shares the claim). The layers beside `wall_neighbour_slide.qgs` show the same
geometry.

That run's land table predates T-124 and lists no separate failures, so loss
then held the claim's pooled ground on the wall itself and charged **no new
wall**. The table is what the current loss s1 would charge for the same ground:
SP0003334 as one failure held by no damaged wall.

| | |
|---|---|
| wall | reinforced concrete pre-1992, 1.712 m high, medium, 46.08 m, one piece |
| wall's own polygon | SP0003419, standing |
| stretch inside SP0003334 | 3.94 m (the plan says about 3.96) |
| clipped wall, replaced whole, as it was | $85,124 wall only; $155,062 with fees, on-costs and contingency |
| SP0003334 on the claim | 47.56 m2 (21.90 m2 inundated, 3.02 m mean depth) |
| its new wall | large, 2.75 m high, 13.75 m long, $43,775 wall only |
| both, with loadings | $234,802 |
| stretch to SP0003334's edge | at most 0.50 m, mean 0.28 m; angle 6 degrees |
| stretch within 2 m of the edge | 100 % |
| a 13.75 m new wall laid on the edge | 0.01 to 0.50 m from the stretch, 100 % overlap |
| verdict | **same structure** |

The $225k of 2026-10-11 is not reproduced. Pricing the wall as the old pooled
rule did (the slip held by the wall, which then rebuilds at 2.75 m rather than
1.712 m) gives $146,670 wall only and $267,175 loaded, so the old figure was an
enlarged replacement with loadings, and prices and fee rules have moved since.
Either way the clipped stretch is 3.94 m of 46 m, it lies along the slip's
edge, and the slip would also get its own 13.75 m wall.

## Samples

Five same-structure pairs and two of each different verdict per extent, drawn
with seed 1 (`samples-<extent>.csv`). "wall line m" is the whole wall's line,
"piece m" the length on this claim and "inside m" the wall line inside this
slip's ground. Costs are wall only, incl GST.

#### lower-hutt

| claim | wall piece | split | piece m | wall line m | inside m | clipped wall $ | slip | new wall m | new wall $ | on edge | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 69902634 | 3fc5d8e0...-RW01-P2 | yes | 6.5 | 28.3 | 0.7 | 9,989 | SP0006819 | 15.2 | 50,653 | 100% | same |
| 8d7aee71 | 8d7aee71...-RW01-P1 | yes | 18.8 | 22.6 | 3.3 | 32,267 | SP0049836 | 10.2 | 19,246 | 100% | same |
| 365cd0da | 4c7241bb...-RW01-P2 | yes | 1.1 | 5.0 | 4.0 | 2,296 | SP0073269 | 23.2 | 77,379 | 100% | same |
| 4c7241bb | 4c7241bb...-RW01-P1 | yes | 3.9 | 5.0 | 4.0 | 8,524 | SP0073269 | 14.3 | 28,222 | 100% | same |
| 5cae156d | 5cae156d...-RW01 | no | 9.0 | 9.0 | 5.1 | 12,932 | SP0072844 | 12.3 | 23,177 | 100% | same |
| e4706245 | e4706245...-RW01-P1 | yes | 24.3 | 37.4 | 18.4 | 51,965 | SP0027951 | 9.3 | 21,009 | 49% | different (clips, not along edge) |
| 529b699c | 824fec17...-RW01-P3 | yes | 3.7 | 14.4 | 14.4 | 6,508 | SP0013212 | 24.6 | 89,541 | 36% | different (clips, not along edge) |
| fa052cfe | fa052cfe...-RW01 | no | 8.3 | 8.3 |  | 24,853 | SP0047764 | 7.3 | 5,132 |  | different (slip does not touch) |
| 76c771fc | 2910936f...-RW02-P2 | yes | 1.1 | 30.9 |  | 1,726 | SP0050648 | 15.4 | 27,754 |  | different (slip does not touch) |

#### upper-hutt

| claim | wall piece | split | piece m | wall line m | inside m | clipped wall $ | slip | new wall m | new wall $ | on edge | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4d665123 | 4d665123...-RW01 | no | 16.6 | 16.6 | 0.8 | 32,231 | SP0024425 | 14.0 | 50,945 | 100% | same |
| fa3eeb53 | 5101f81d...-RW01-P2 | yes | 3.8 | 25.8 | 1.2 | 8,268 | SP0010167 | 6.8 | 5,457 | 100% | same |
| dcb6825c | 9447c4de...-RW01-P2 | yes | 19.1 | 19.1 | 16.3 | 38,152 | SP0042751 | 42.1 | 153,073 | 64% | same |
| 80dcb5aa | 80dcb5aa...-RW01 | no | 9.6 | 9.6 | 9.6 | 15,435 | SP0065344 | 9.5 | 19,551 | 60% | same |
| fdf524c2 | fdf524c2...-RW01 | no | 2.9 | 2.9 | 0.7 | 3,408 | SP0048407 | 6.0 | 4,358 | 100% | same |
| 54a0ae3c | 54a0ae3c...-RW01 | no | 5.7 | 5.7 | 5.7 | 7,035 | SP0015833 | 13.2 | 23,735 | 42% | different (clips, not along edge) |
| 1a1b7c1b | 1a1b7c1b...-RW01 | no | 4.9 | 4.9 | 4.9 | 7,875 | SP0031566 | 13.8 | 25,976 | 0% | different (clips, not along edge) |
| 325afe8d | 325afe8d...-RW02 | no | 14.5 | 14.5 |  | 27,243 | SP0046756 | 7.3 | 5,623 |  | different (slip does not touch) |
| 6b789e66 | 6b789e66...-RW02 | no | 10.0 | 10.0 |  | 19,660 | SP0015094 | 10.8 | 21,269 |  | different (slip does not touch) |

#### porirua

| claim | wall piece | split | piece m | wall line m | inside m | clipped wall $ | slip | new wall m | new wall $ | on edge | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 40a29c1c | 40a29c1c...-RW01-P1 | yes | 20.8 | 31.4 | 0.5 | 43,723 | SP0026065 | 17.1 | 62,358 | 100% | same |
| 976c4707 | ff5dccff...-RW01-P2 | yes | 2.6 | 7.2 | 1.9 | 3,632 | SP0049589 | 22.4 | 78,015 | 100% | same |
| e13f347a | e13f347a...-RW01 | no | 6.7 | 6.7 | 1.0 | 8,546 | SP0016915 | 13.1 | 23,489 | 100% | same |
| 9f9ed2be | 9f9ed2be...-RW02 | no | 24.1 | 24.1 | 15.0 | 39,549 | SP0051907 | 15.0 | 32,439 | 100% | same |
| 58882d92 | 58882d92...-RW02 | no | 15.9 | 15.9 | 2.9 | 32,991 | SP0029106 | 14.2 | 28,066 | 100% | same |
| 8a5b0634 | e099fb18...-RW01-P2 | yes | 10.5 | 33.0 | 24.9 | 27,980 | SP0025233 | 21.1 | 70,508 | 33% | different (clips, not along edge) |
| aac66466 | aac66466...-RW01-P1 | yes | 20.9 | 35.2 | 5.5 | 39,556 | SP0018137 | 33.1 | 120,244 | 43% | different (clips, not along edge) |
| 5e1ef342 | 5e1ef342...-RW03 | no | 6.5 | 6.5 |  | 10,534 | SP0038932 | 5.0 | 4,161 |  | different (slip does not touch) |
| 9f9ed2be | 9f9ed2be...-RW02 | no | 24.1 | 24.1 |  | 39,549 | SP0051881 | 20.9 | 76,172 |  | different (slip does not touch) |

## Findings

1. **About 1,320 claims carry both** across the three extents (636, 274, 410),
   holding $112M of wall cost between them ($57.0M, $24.2M, $31.3M), of which
   $33.8M is clipped-wall replacement and $78.7M is new walls. Most claims with
   a new wall are not in this group (new walls are on 6,653, 2,955 and 4,808
   claims).
2. **Only 804 of the 1,320 are one slip and one wall.** A slip that
   clips the wall is on 392, 161 and 251 claims (804). The rest (516) pair a
   clipped piece with a new wall for some other slip that does not touch it, a
   legitimate second structure, and stay as they are.
3. **Of the 804 claims with a clipping slip, 716 (337, 148, 231) are the same
   structure by the edge test** and 88 (55, 13, 20) are different: the wall runs
   across the slip's ground (angles near 90 degrees, only a third to a half of
   the stretch near the edge). The same-structure share is stable to the
   tolerance (at 5 m, 797 of the 804).
4. **The same-structure pairs are what the plan fears.** The slip's new wall is
   $14.2M, $6.6M and $9.0M, beside clipped pieces of $8.5M, $3.9M and $6.0M. The
   new wall is usually the larger of the two in the samples: a 5 to 30 m wall
   for the slip against a clipped wall of usually 1 to 5 m inside the ground.
5. **The stretches are mostly short.** The median stretch inside a clipping slip
   is 3.7, 2.9 and 2.8 m, against whole-wall pieces of about 11 m. A short
   stretch of wall across a slip's corner is within 2 m of the slip's edge
   almost by construction, so the edge test is generous for stretches under
   about 4 m. Of the 126, 59 and 75 same-structure pairs with a stretch over
   4 m, the verdict is less clear-cut. The angle column helps: among clipping
   pairs with a measurable angle (stretch of 2 m or more) 108 of 266, 52 of 112
   and 56 of 166 are more than 45 degrees to the edge.
6. **Most clipped pieces are `absorbed` walls.** Of the clipped pieces 423 of
   828 (Lower Hutt), 182 of 359 and 297 of 559 are `absorbed` by a larger urban
   failure, and a few `superseded`; the rest are `standing` walls caught by a
   neighbour's ground. The absorbing failure is another polygon, so for these the
   slip that "clips" the wall and the slip that took the wall can be the same
   one, and the "clipped stretch" is then only part of what is gone.

## Implications for section 6's s1 pricing

1. **Where a clipping slip is a failure with no wall of the claim's own, the
   current s1 charges the whole clipped piece and a new wall for the slip.** For
   the 716 same-structure claims that is a double charge of the ground the
   stretch stands on. It is not a double charge for the 516 claims whose new
   wall is for a different slip, or the 88 where the wall runs across the
   ground.
2. **Yes: where the stretch lies along the slip's edge, the clipped stretch
   should hold the slip.** Size the stretch as `replacement_wall_shape` sizes a
   wall against its slip (the larger of the stretch and the slip's length,
   height and size class) and charge no separate new wall for that slip. On the
   single-slip same-structure pieces (wall only) today's $22.2M, $10.5M and
   $14.5M fall to $18.0M, $8.7M and $11.5M with section 6.1 alone (damaged
   stretch plus the slip's own wall, kept apart), and to $15.1M, $7.4M and
   $9.5M merged: a further $2.9M, $1.2M and $2.0M that section 6.1 leaves in as
   the same structure charged twice, $7.1M, $3.0M and $4.9M in all.
3. **Mechanism.** In s1 `attach_failures_to_walls` holds a slip by the claim's
   damaged wall whose parent is the failure's `landslide_rw_id`. The same-
   structure case needs the slip also held by the clipped wall. That needs vul
   to say which slips clip which wall (the `landslide_id`s of the slips
   behind each wall's `damaged_line`, which section 6 has vul rw s11 measure) and carry
   them into `rw`, so s1 can hold the slip by the clipped piece and size it in
   `replacement_wall_shape` with its slip. It needs no geometry in loss.
4. **The different-structure cases stay as they are** (both charged), subject to
   the test being right. The edge test needs a polygon edge, which loss does not
   have; the rule has to be made in vul, where the slip's ground and the wall's
   line are both to hand.
5. Bring the counts and the threshold to the lead before s1 is built: the 2 m
   and 50 % are a judgement, and the verdict for short stretches is generous.

## Caveats

1. **Split walls.** Pieces of a wall split across properties each carry the
   whole wall's line as geometry and their own share as `rw_length`
   (3,213 of 8,482 Lower Hutt pieces are split). The stretch is measured on the
   whole line, so on a split wall it may fall on another claim's piece. Pairs on
   split pieces: 145 of the 348 same-structure pairs in Lower Hutt, 65 of 163 and
   107 of 252. Section 1's insured stretches would settle which claim holds the
   stretch. Without them the same-structure count for split walls is an upper
   bound. Counting only unsplit pieces, same-structure claims fall to 200, 92 and
   134.
2. **No geometry for the new wall.** The slip's ground stands in for where its
   wall would stand. A real wall might stand at the headscarp, the toe or the
   boundary of the insured land, and loss's length (width plus margin) is
   computed from area on the claim only.
3. **Thresholds are judgement** (2 m, 50 %, the 1 m and 5 m sensitivity); the
   sensitivity is a spread of about 15 % either way of the 2 m count.
4. **The stretch is measured on the line's inside length, not the cost.** Merged
   costs size the stretch by section 6.1's rule on the whole-wall inside length
   (so for split walls too long) and take the clipped wall's type and height;
   the merged wall takes the larger height as `replacement_wall_shape` does.
   A piece with two same-structure slips is counted once per pair in the
   per-pair CSVs, and the summary costing is restricted to single-slip pieces.
5. **Costs are the wall alone**, before fees (at least $5,100 a claim), mob/demob
   (at least $5,000) and contingency; merging two walls on a claim into one
   also saves some of these, because fees and mob/demob have floors, so the
   saving is larger than the wall-only figures.
6. **Current outputs, not 2026-10-11.** The wall of the Porirua example is in the
   saved run only, whose land table predates the failure lists, and its
   costs use today's pricing, not the run's. Lower Hutt costs are not checked
   against a settlement file.
7. **Other mechanisms of a damaged wall** (shaking, `failed_with_polygon`) are not
   in this table by design: they are replaced whole and the slip they came
   with is held by them.
