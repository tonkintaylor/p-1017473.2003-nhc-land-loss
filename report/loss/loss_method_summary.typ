// How the loss module settles a claim — method summary for a non-technical
// reader. Every assumption is numbered so a meeting can refer to one by number
// and the decision can be recorded against it.
//
//     typst compile report/loss/loss_method_summary.typ

#set page(paper: "a4", margin: (x: 1.6cm, y: 1.3cm), numbering: "1 / 1")
#set text(font: "Arial", size: 9.5pt)
#set par(leading: 0.55em, justify: true)
#show heading.where(level: 1): set text(size: 15pt)
#show heading.where(level: 2): set text(size: 11pt)
#show heading.where(level: 2): set block(above: 1.1em, below: 0.45em)
#show heading.where(level: 3): set text(size: 9.5pt)
#show heading.where(level: 3): set block(above: 0.8em, below: 0.3em)

#let a(n) = box(
  fill: rgb("#e8eef3"), inset: (x: 3.5pt, y: 1pt), outset: (y: 1.5pt),
  radius: 2pt, text(size: 8pt, weight: "bold", fill: rgb("#2c5470"))[A#n],
)
#let q(body) = block(
  fill: rgb("#fdf6e3"), stroke: (left: 2pt + rgb("#c9a227")),
  inset: (x: 8pt, y: 5pt), width: 100%, radius: 1pt, text(size: 9pt)[#body],
)

= Land loss: how a claim is settled

#text(size: 10pt, fill: luma(40%))[
  NHC land loss study · method summary · #datetime.today().display("[day] [month repr:long] [year]")
]

This note sets out how the study works out what NHC would pay on a damaged-land
claim, and — more importantly — *what it assumes where the evidence runs out*.
INTRO
Figures quoted are from the Wellington pilot, 4,388 properties, one modelled
earthquake.

#a[1] *Nothing here is an observed claim.* The earthquake, the landslides, the
liquefaction and the retaining walls themselves are all modelled. No property in
the pilot has been inspected, and the retaining wall population in particular is
generated rather than surveyed — the study knows how many walls a street is
likely to have, not which houses have one.

== What the Act pays

The Act does not let a claimant choose between the value of damaged land and
the cost of repairing it. It builds a *land cover cap* out of the value, then
pays the lesser of that cap and the repair cost, less an excess:

#align(center, block(inset: (y: 4pt))[
  #text(size: 10pt)[
    cap = market value of the damaged land + retaining wall value + crossing value \
    *settlement = min(repair cost, cap) − excess*
  ]
])

Each structure counts at the *lesser* of its undepreciated value and a
per-dwelling sub-cap — \$50,000 for retaining walls, \$25,000 for bridges and
culverts, both plus GST. The land is valued over the lesser of the damaged area
and 4,000 m#super[2]. Every figure in this note includes GST, which
is the basis the Act compares on.

#a[2] *A dwelling is counted as a postal address.* The sub-caps multiply by
the number of dwellings, and the count comes from address points. That works
for a block of flats, undercounts a minor dwelling never separately addressed,
and overcounts a building with a shop in it.

== Where the numbers come from

=== The damaged land

Damage arrives from two mechanisms that are measured quite differently.
*Landslide* damage arrives as an area of ground lost. *Liquefaction* damage
arrives only as a severity state — None through Very Severe — with no area
attached at all.

#a[3] A damaging liquefaction state is read as damaging the property's *whole
insured area*. Insured land is 93.5% of the property at the median, so this
values a whole section. It is the single largest reason the cap rarely binds,
and it is an assumption rather than a finding.

#a[4] Where both mechanisms hit one property, the damaged area is the *larger*
of the two rather than their sum, so ground damaged twice is valued once.

The land is valued at a market rate per square metre modelled in the exposure
work from published QV average residential land values.

=== Retaining walls

#a[5] Nothing in the data says what a wall is made of. 30% are priced as
reinforced concrete and the rest take one of four timber pole rates, spread
evenly. Which wall gets which is fixed by its identity, so it is the same in
every run. The costing tool's 29 rates span a factor of 21, so this is the
largest single assumption in any wall cost.

#a[6] A wall's height comes from its size class — 0.75 m, 1.75 m or 2.75 m —
rather than from the wall itself.

#a[7] A damaged wall is *replaced, not repaired*. Partial repair is about 1% of
real cases and is not modelled.

#a[8] The replacement is assumed to be a better wall than the one that failed,
at *20%* above the original specification. Walls are generally rebuilt to
current standards rather than like for like.

=== How hard the site is to work on

Three ratings — construction access, earthworks, and constructability — mark a
wall's cost up by 0%, 5% or 10% each, to a ceiling of 30%. In a real claim a
geotechnical engineer supplies all three from a site visit. The study has no
site visits.

#a[9] *Construction access* is proxied by the length of the driveway from the
house to the road: the longer the run, the harder it is to get plant in.

#a[10] *Constructability* is proxied by the slope of the ground at the property.

#a[11] *Earthworks* comes from the volume of material a landslide deposited.

#a[12] A property with no driveway routed and no slope recorded rates *easy* on
both proxies, which flatters it.

What bounds the risk here: all three together can move a wall's cost by 30% at
most, against the factor of 21 that the construction type spans. Getting these
roughly right matters far less than getting the rate right.

=== Repairing damaged land

#a[13] *One wall stands on a property, so a claim is charged for one wall.*
Where a retaining wall is already there it is assumed damaged and is replaced,
and that replacement holds the ground as well. Where there is none, one is
invented. The two are never both charged — doing so priced the same structure
twice, once at \$74,302 against a slip of 1.4 square metres.

#a[14] Where the property had no wall, landslide ground is held by *building a
retaining wall that was never there*. Its size comes from the area lost and the
depth of the deposit; its length from the width of the failure, plus a margin,
never under 5 m. It is a cost and never an asset: a wall that did not exist has
no value to add to the cap.

#a[15] Material deposited on a property is cleared at \$150 per cubic metre,
which is the costing tool's own rate.

#a[16] Liquefaction land damage carries its own cost, taken from what NHC
actually settled in Canterbury: \$200 to \$4,000 per property by severity.

#a[17] Bridges and culverts are not priced. A damaged one is assumed to exceed
its sub-cap and is settled at that limit.

=== Professional fees

#a[18] Consent, design, engineering, health and safety, project management and
survey come to \$5,100 per claim, from the costing tool's own fee table. They
are charged once on any claim involving a wall, and they scale with site
difficulty — a hard site costs more to design and consent as well as to build.
Mileage is excluded. Fees never form part of an asset's value, only the cost of
putting it right.

=== The excess

#a[19] The excess is *10% of what would otherwise be paid, once per claim*,
with a \$500 floor and a \$5,000 ceiling. It is taken on the amount payable
rather than on the repair cost, so a claim is never charged an excess against
cost NHC is not bearing.

#q[
  *Open question.* NHC's own explainer states a flat "\$500 per dwelling, capped
  at \$5,000" and works all three of its examples that way, which disagrees with
  the above by \$4,500 on its own first example. Both rules can be run; the
  study currently uses the 10% rule. *This needs settling before any figure is
  issued.*
]

== What the study cannot yet see

#a[20] The Canterbury costs are in *2010/2011 dollars and have not been
escalated*. They are compared against land values and wall rates in today's
money, which understates the repair side of every liquefaction claim. NHC's
actuarial team has been asked to advise the factor; a 2–4× increase is expected.

#a[21] Those same Canterbury rates *exclude the increased-vulnerability
payments* (ILV and IFV) that made up the expensive end of the Canterbury
settlements, and they are documented as applying to *flat land only*. Much of
Wellington is hill.

#a[22] A single cost is used per severity state — the median. The underlying
data is skewed with a long tail, so the median cost is not the median
settlement. Running the low and high cases would give a range rather than a
single figure.

#a[23] The Canterbury rates may already include some retaining wall damage. If
so, a property carrying both liquefaction and a damaged wall is charged for the
wall twice. 107 pilot properties carry both.

== What the pilot shows

On 4,388 properties and one modelled earthquake, \$13.1 m is paid across 2,283
claims. Two findings matter more than the total.

*The cap almost never binds.* Repair costs are around 0.2% of the cap at the
median. The Act's cap exists to limit the largest claims, but the mechanism
that produces most claims here — minor liquefaction — is cheap to repair while
its cap is the value of a whole section. Every assumption at #a[20] through
#a[23] pushes repair costs up, and the cap will begin to bind as they are
resolved.

*Liquefaction and retaining wall claims are two different populations.* Of
claims paid, 72% are liquefaction only and account for 12% of the money. Almost
every claim settling above \$5,000 involves a wall.

#v(0.4em)
#block(fill: luma(96%), inset: 8pt, width: 100%, radius: 2pt)[
  *How to read a figure from this study.* Every number is conditional on the
  assumptions above, and several of them — #a[3], #a[5], #a[19] and #a[20] in
  particular — would move the totals materially. The study is at the point where
  the machinery is complete and the inputs are still being confirmed.
]
