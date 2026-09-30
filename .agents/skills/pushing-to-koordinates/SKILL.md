---
name: pushing-to-koordinates
description: >-
  Publish a layer from this study to the T+T Koordinates site, in the National
  Liquefaction Model groups, creating it the first time and adding a new version on
  every later run, with the house colours applied as a server-side style. Use when the
  user wants to save, push, publish, upload or share a layer 'to the NLM' or 'to
  Koordinates', wants stable model inputs or outputs put somewhere other than source
  material, or asks how to create a Koordinates layer from the API. Not for quick looks
  at unstable output — that is the making-kml-files or making-qgis-projects skill.
compatibility:
  platform: universal
metadata:
  author: mmillen
  version: "1.0"
---

# Pushing layers to Koordinates (NLM groups)

A push is the opposite of the other two viewing skills: it **writes to a shared service**
other people read from. So it is a dry run unless told otherwise, it refuses groups outside
the NLM ones, and it never retries the call that creates a layer.

## 1. Is this layer worth pushing?

Push **stable** layers: inputs the study relies on, boundaries, and final model outputs. Do
not push a per-realisation working output that changes every run — each run adds a version
on the server, and other people may come to depend on what they see. For a quick look, use
`making-kml-files` or `making-qgis-projects`.

Anything derived from LINZ data is CC BY 4.0 and must credit LINZ. Put the credit in the
layer's `attribution` and it is added to the Koordinates description.

## 2. Where it goes

| Group | ID | Use |
|---|---|---|
| National Liquefaction Model Dev | `5452` | The default, and the only one tested. |
| National Liquefaction Model | `5380` | Production. Needs `"confirm_production": true` on the layer. |

The project's own group, **NHC WTGN Land Damage Model (`8867`)**, is deliberately *not*
allowed yet: on 2026-09-30 and 2026-10-01 an upload to it returned **403 "You don't have
permission to edit this user or group"** with two different API keys, while the same
upload to 5452 worked. The user is a plain `user` member of both groups, so the difference
is on the group's side (a publisher or admin role, or an upload setting), not the key. When
that is fixed, add `8867` to `NLM_GROUPS` in the script — and ask the user first, since it
is outside "the NLM".

Never paste an API key into a file or a command that is saved. The key is read by
`landloss.io.readers.resolve_api_key`, from `TNT_KOORDINATES_API_KEY` in `.env`. That one
function is the only place the lookup is done.

## 3. The spec

The layer is named exactly as in `making-qgis-projects` (`store` + `fname`, or `path`) and
styled with the same keys, so the same spec can feed all three skills. Additions:

- `key` — a short stable slug, the registry's name for the layer. Never reuse one.
- `title` — what Koordinates shows. Needed, and unique within the group.
- `group` — `5452` unless stated. `description`, `tags`, `attribution`, `style_name`.
- `apply` (top level) — `true` to push. Without it nothing is written.

Styling: `field` with `categories` (a named set from `colors.py` or an explicit map),
`field` with `cmap` and `bins` (graduated, quantile by default), or a single `color`.
`outline`, `width` and `"fill": false` work as in the KML skill. See
`references/example-spec.json`.

## 4. Run it

1. Write the spec to the scratchpad. **Dry run first**:

   ```bash
   uv run --frozen python .agents/skills/pushing-to-koordinates/scripts/push_to_koordinates.py spec.json
   ```

   It prints, per layer, whether it would create or update, the group, the feature count,
   the CRS and the style.

2. Show the user the plan and get a clear yes for *this* push: the layer, the group, and
   that it will be visible to that group's members.
3. Set `"apply": true` and run again.

The script, for a layer with no registry entry: checks the group for a layer with the same
title (and stops if there is one the registry does not know), converts the local copy to
GeoPackage, uploads it as a source, creates the layer, waits for the import, publishes,
**records the layer ID in `registry.json` straight away**, then publishes the style and sets
it as the default.

With a registry entry it adds a new version to that layer instead (section 6).

`registry.json` is committed. It is updated one key at a time and never rewritten from
scratch, so earlier entries survive.

## 5. Check it, then say what you did

Compare the layer with the source: the feature count, the CRS and the field names all come
back from `GET /layers/{id}/`, and the extent should sit over the study area. Say plainly
what was checked. Do not claim the style looks right without looking at it — the style is
only confirmed to be generated (`ACTIVE`), not viewed.

## 6. Known limits

1. **Update is untested from here.** The create path was run end to end against group 5452
   on 2026-09-30 (upload, create, import, publish, style, delete). The update path is
   ported from the NLM repo's `update_layer_datasource` and has not been run from this one.
   Test it on a throwaway layer before using it on one that matters.
2. **A styled layer has two or more versions**, because setting the default style needs a
   new draft. Every update adds more.
3. **Import is slow**: about 70 seconds for 761 lines. Large layers take longer; the wait
   stops at 30 minutes.
4. **Rasters are not supported.** This handles vectors only.
5. **Graduated styles** cut the classes from the data when pushed, so they freeze at those
   breaks until the next push.

## 7. Deleting

`DELETE /layers/{id}/` removes a layer (204) and `DELETE /sources/{id}/` the source it came
from. The script has no delete; do it deliberately, only for a layer this session created
or the user names, and remove its registry entry. A deleted layer returns 410.

## 8. API facts learned the hard way

1. The source upload needs `title` as well as `name`, or it returns 400.
2. `POST /layers/` returns a `Location` header for the **layer**, not the draft; get the
   draft from `GET /layers/{id}/versions/`.
3. Creating starts the import on its own; there is no need to call `/import/`.
4. Do not retry `POST /layers/`. The NLM `KoordinatesConnection` does, and a timeout can
   then create two layers. This skill uses its own session for that reason.
5. A key can be scoped. `/users/me/` returns 401 "requires users:me:read" on the current
   keys, which does not stop layer work.
