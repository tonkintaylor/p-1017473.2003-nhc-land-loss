# The NHC Natural Hazards Portal is not a data source for this project

Investigated 17 September 2026, after the question was raised of whether settled
claim data could be pulled from the public portal at
<https://www.naturalhazardsportal.govt.nz/map/> for the study area.

The conclusion is that it could be, technically, but it must not be. The portal's
terms of use prohibit automated extraction, and the data it exposes is materially
weaker than what NHC can supply directly through the channel this project already
has open. Both halves of that conclusion are recorded below so the question does
not have to be re-investigated, and so nobody rebuilds the extractor on the
assumption that it was simply never tried.

## Why not

The [terms and conditions](https://www.naturalhazardsportal.govt.nz/about/terms-and-conditions/)
grant only a limited licence to use the portal for "searching the Portal and
obtaining information about natural hazards ... and residential properties in New
Zealand". Against that purpose, the terms state that you must not:

> use any robot, spider, screen scraper, data aggregation tool or any other or use
> any process or processes that send automated queries to data mine, scrape, crawl,
> email harvest, aggregate, copy or extract any processes, information, content,
> data or information from the Portal

and separately must not "modify, alter, adapt or incorporate any portion of the
Portal or the Portal Data into any other materials, products, services or
databases, other than for the Purpose". Bulk extraction into this project's model
is squarely what those two clauses describe, on a commercial engagement.
`robots.txt` is permissive and disallows only `/admin` and `/dev`, but it does not
override the terms.

There is no open data release of the claims to fall back on. The portal is the
only public surface for them.

## The route that is already open

NHC is the client on this project, and claims data is already being requested from
them directly — task T-17 in the register covers land damage claim costs for
Wellington, with Bridget Attwood as the routing contact and Andrew Kang identified
as the claims data contact. That request is the correct and sufficient path.

It is also the better one. The portal carries no cost information whatsoever, only
a binary flag for whether a claim involved land damage. Cost is the thing this
project actually needs.

## What the portal holds, for shaping the request to NHC

Worth knowing when writing the data request, because it shows what the claims
systems can express and what the public view deliberately withholds. Each claim
point carries exactly four attributes:

| Field | Values |
| --- | --- |
| `LossCause` | `Earthquake`, `Landslip`, `Storm/Flood`, `Tsunami`, `Volcanic Eruption`, `Hydrothermal Activity` |
| `LossDate` | Date of damage, as epoch seconds |
| `BuildingClaim` | 0 or 1 |
| `LandClaim` | 0 or 1 |

The two hazards relevant here are `Earthquake` and `Landslip`, and `LandClaim = 1`
isolates land damage, so the portal's own filtering vocabulary maps cleanly onto
the study. Asking NHC for those fields *plus claim cost and a property identifier*
turns a general request into a specific schema they can extract against.

Coverage and its caveats, from the portal's
[data sources page](https://www.naturalhazardsportal.govt.nz/about/data-sources/)
and terms, all of which apply equally to any extract NHC provides from the same
systems:

- Settled and closed claims only, from 1 January 1997, where EQC or NHC accepted
  liability for at least part of the claim. Declined, open and invalid claims are
  absent, as is everything before 1997.
- Storm and flood appear for land damage only, because NHC cover for those events
  does not extend to dwellings.
- Claims made to private insurers before 30 June 2021 are out of scope of
  EQCover/NHCover and so are absent.
- Known address-matching artefacts: subdivided land has prior land claims assigned
  to all new parcels, body corporate claims are linked to every dwelling in the
  complex, and rezoned or demolished-and-rebuilt properties can carry stale claims.
- Data is refreshed monthly.

The absence of a claim does not mean a property was undamaged — it may have been
uninsured, unclaimed, repaired privately, or damaged before 1997.

## Technical findings

Recorded only so that the investigation is not repeated. This is not an
instruction to use any of it.

The map is a MapLibre application backed by an ArcGIS vector tile service at
`https://tiles.arcgis.com/tiles/t6F7yyJcP4ZPzHIM/arcgis/rest/services/Claims/VectorTileServer/`,
authenticated with a short-lived token issued by the portal's own
`/api/arcgis-token` endpoint and bound to a portal `Referer`. The service is
`TilesOnly`, so there is no `FeatureServer` query API and no spatial or attribute
filtering server side; the portal's own hazard and date filters are applied in the
browser. Zoom 15 is the service's maximum level of detail and is complete — a
parent tile and its four children were checked to contain the same 1481 points.
