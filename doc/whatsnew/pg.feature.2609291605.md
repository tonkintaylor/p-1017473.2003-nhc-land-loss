**One wall stands on a property, so a claim is now charged for one wall.**
Where a retaining wall is already there, `vul`'s damage flags decide whether it
needs replacing; where it does, that replacement is the whole of the wall cost
and holds the landslide ground as well. Where the property has no wall, or has
one `vul` finds undamaged, a wall is invented for the ground instead. The two
never both appear.

This replaces the earlier rule, which let a wall repair reinstate one metre of
land for every metre of its length and charged separately for the rest. That
allowance was arbitrary, and it was not monotonic — a longer damaged wall left
less land to pay for, so a claim could be better off for having been damaged
more.

Across the pilot the invented walls fall from \$1,248,769 to \$1,114,733, the
total repair cost by the same \$134,036, and the settlement from \$13.13 m to
\$13.03 m. Only **three claims** move, all of them properties where a wall was
replaced *and* a second one priced beside it. The largest had a 208.8 m² slip
and was paying \$28,326 to replace its wall and \$69,709 to build another; it
now settles at \$76,688 rather than \$156,854.

The **"a new wall is never smaller than the existing wall"** rule goes with it,
along with `at_least_the_existing_wall` and its tests. It is unreachable now
rather than abandoned: a wall is only invented where there is none to be no
smaller than, and where there is one, replacing it cannot produce something
smaller than itself. Keeping it did active harm under the two-wall reading —
on a 1.4 m² slip beside an 18.7 m wall it forced the invented wall out to the
full 18.7 m, for \$34,596.

Six tests now pin the rule down, in the first test module to reach into
`src/scripts`. Nothing covered the rule it replaces, which is why removing that
one broke no test.

**The Repair cost tab is rebuilt around the asset rather than the line item.**
Four blocks, each asking the same four questions about one thing: what is it,
what is it worth, what would repairing it cost, and what does it contribute.
Block A is landslide land, B the retaining wall, C liquefaction, and D turns
the three into one settlement. "RTW" throughout, a subtotal per block, and
`MIN(repair, cap)` taken once at claim level over all of them.

Block B leads with **what damaged the wall**, which is the column that was
missing. 530 of the pilot's 532 damaged walls are damaged by **shaking alone**,
with no landslide near them, so a claim with no damaged ground being charged
for a wall is the ordinary case and not an error — but nothing on the tab said
so. It now reads `shaking`, `evacuated`, `inundated`, `wall present, undamaged`
or `no wall on the property`.

**Every dollar is GST-exclusive** until block D adds it once, and the
settlement is given both ways. Two figures are deliberately not divided: the
land values, because a market value is not a GST-bearing price and dividing one
would invent a figure nobody quoted; and the crossing sub-cap, which is a limit
rather than a priced repair. That leaves `MIN(repair, cap)` compared on the
GST-inclusive basis, as the module does it — whether that is the intended
reading is still open.

Three columns are on the tab and **empty on purpose**, each headed with the
reason so nobody has to scroll to find it. Imminent damage is not modelled yet.
The liquefaction inundated and evacuated extents do not exist at all: `vul`
sends liquefaction as a damage state with no footprint, and lateral spreading
is being modelled as a magnification of the probability of states 4 to 6 near
waterways, which moves a property's state rather than drawing an area.

The tab reaches the settlement by a different route from the module — building
the repair up from four blocks rather than reading it whole — so it checks
itself. `check_repair_against_the_model` settles all twenty claims in Python
and compares the cap, the excess and the settlement against what the module
produced; it agrees to \$0.00, as does the Calculation tab's older check.
`repair_columns` additionally refuses to build a tab where two columns share a
heading, after "Total damaged land (m2)" appeared in both block A and block C
and misled the first person to read it.
