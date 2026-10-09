# What drives land damage in the study area

Engineering context from the kick-off meeting on 16 September 2026, drawing on
John Leeves, Maxim Millen and Nick Peters' input relayed through the meeting. It
records the team's working picture of how land damage will actually occur in
Wellington, which is what the decision tree and the spatial model have to
represent.

## Modified slopes are where the losses are

The slopes most exposed are the modified ones. Two patterns dominate:

- Ground cut into the slope behind a house, often without a retaining wall, which
  leaves an oversteep natural slope.
- Fill placed in front of a dwelling, typically behind a retaining wall.

The expectation is that the majority of losses sit on these modified slopes rather
than on natural terrain. This is why a cut-and-fill dataset is valuable: Wellington
City Council is understood to hold a cut-and-fill model, and a tool built for
Auckland Council already identifies cut-fill slopes from property file data.

## Local failures versus global failures

Most earthquake-induced landslides are expected to be confined to a single
property, by analogy with the rainfall-induced landslips the team routinely sees.
Each is typically associated with a failed retaining wall, an oversteep cut, or a
fill embankment failing.

Multi-property failures concentrate in the **gullies**, where historic landslides
have left colluvium and more recent deposition, and where higher water tables
allow more global landslide types to develop. These are the failures capable of
writing a property off entirely.

One caveat on the rainfall analogy: earthquake shaking is expected to be more
damaging to steep faces than rainfall is, because of how the demand pulls material
away from the slope. This was raised as a reasonable expectation rather than an
established result.

## Retaining wall condition

Many walls in the study area are old and already deteriorating; several would not
take much to fail. As set out in `nhc-land-cover-and-settlement.md`, condition
affects the likelihood of failure but not the settlement, since the NHC Act pays
replacement value up to the cap regardless of state.

There is no dataset of privately owned retaining walls. The candidate routes, in
descending order of confidence, are an SME estimate of prevalence by suburb from
Nick Peters, LIDAR point cloud analysis for vertical surfaces, aerial imagery
interpretation by a trained optical model, and council property files. The LIDAR
route is limited by vegetation: it will find some walls, but the fraction it
misses is unknown, so the count cannot be scaled up reliably.

## Landslide extent

The open modelling question is whether to estimate the spatial extent of each
landslide, or to classify each property as fully, partially or not affected.
Estimating extent handles landslides running across several properties and was the
preferred direction, but GNS's model of landslide extent — which distinguishes
smaller and larger failures on the same slope — is complicated to implement. The
classification approach reaches a working answer faster, which matters given the
build-first-then-refine method.

## Sources of a landslide estimate

T+T will produce its own estimate of slope failures. GNS holds a model in PRUE
which one NHC reviewer distrusted and another was willing to use; the agreed
position is to request it and use it as a cross-comparison rather than as an
input. Greater Wellington Regional Council also holds two landslide susceptibility
layers.
