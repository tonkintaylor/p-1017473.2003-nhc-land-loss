# Welcome to NHC Land Loss

## How We Use Claude

Based on Maxim Millen's usage over the last 30 days (6 sessions, 5 with
descriptors):

Work Type Breakdown:
  Write Docs       ████░░░░░░░░░░░░░░░░  20%
  Build Feature    ████░░░░░░░░░░░░░░░░  20%
  Analyze Data     ████░░░░░░░░░░░░░░░░  20%
  Debug Fix        ████░░░░░░░░░░░░░░░░  20%
  Plan Design      ████░░░░░░░░░░░░░░░░  20%

An even spread — no single mode dominates. Sessions ranged from capturing the
project brief as context files, to wiring up the pre-commit hooks, to asking
whether data could be pulled out of the Natural Hazards Portal, to decoding a
git error.

Top Skills & Commands:
  /clear           ████░░░░░░░░░░░░░░░░  1x/month

Top MCP Servers:
  None recorded    ░░░░░░░░░░░░░░░░░░░░  0 calls

Light on slash commands and MCP so far — most of the work has been plain
conversation plus the repo's own skills.

## Your Setup Checklist

### Codebases
- [ ] p-1017473.2003-nhc-land-loss — git@github.com:maximmillen-tnt/p-1017473.2003-nhc-land-loss.git (this project)
- [ ] p-1017473-national-liquefaction-model — git@github.com:tonkintaylor/p-1017473-national-liquefaction-model.git (geology, liquefaction and slope inputs this project builds on)
- [ ] p-1017473-nlm-loss-modelling — git@github.com:tonkintaylor/p-1017473-nlm-loss-modelling.git (loss modelling approach)
- [ ] p-1017473.2002-nhc-risk-model-understanding — git@github.com:tonkintaylor/p-1017473.2002-nhc-risk-model-understanding.git (earlier NHC work)
- [ ] p-1099456-hurunui-high-level-geotech — git@bitbucket.org:tonkintaylor/p-1099456-hurunui-high-level-geotech.git (reference for the Koordinates readers pattern)

### Environment
- [ ] Run `./tasks/dev_sync.ps1` to set up the Python environment (uv, Python 3.13)
- [ ] Copy `.env.example` to `.env` and fill in the four Koordinates API keys. `.env` is gitignored; never commit it, and never paste a key into a chat or a ticket

  Each portal is a separate Koordinates account with its own key — a key from one
  will not work on another. Generate your own rather than sharing someone else's,
  by signing in and visiting that portal's API keys page:

  | Variable | Portal | Generate at |
  | --- | --- | --- |
  | `TNT_KOORDINATES_API_KEY` | T+T's own instance | https://ttgroup.koordinates.com/my/api/ |
  | `LINZ_API_KEY` | LINZ Data Service | https://data.linz.govt.nz/my/api/ |
  | `KOORDINATES_PUBLIC_API_KEY` | Public Koordinates catalogue | https://koordinates.com/my/api/ |
  | `LRIS_API_KEY` | Landcare Research LRIS portal | https://lris.scinfo.org.nz/my/api/ |

  Signing up is free on all but the T+T instance, where your T+T login already
  works. A reader fails with `Set <VARIABLE> in the .env file to read layers from
  <domain>` when the matching key is missing, which tells you which one to go get

  **Tick the export scopes when you create the key.** Koordinates keys are
  scoped, and the default scopes are not enough. Downloading a layer needs
  `exports:read` and `exports:write` as well as read access to the layer itself.
  Without them the key looks fine — it will read layer metadata quite happily —
  and then fails only at download time with a bare
  `401 Client Error: Unauthorized for url: .../exports/validate/`. If you see
  that, the key is valid but under-scoped: edit its scopes on the same API keys
  page rather than generating a new one. You can confirm what a key is missing
  with:

      curl -s -H "Authorization: key $KEY" https://<domain>/services/api/v1.x/exports/

  which names the missing scope outright. A scope set known to work end to end:

      catalog, documents:read, exports:read, exports:write, items:read,
      items:write, layers:read, query, sets:read, sources:read, tiles,
      wxs:esri, wxs:wfs
- [ ] Leave `KOOPCACHE_DIR` unset unless you want the download cache off the repo's disk — and if you do set it, use an absolute path. It defaults to `.koopcache` at the repo root, which is gitignored, and every reader that caches — Koordinates layers, clipped extents, DEM tiles, the LINZ elevation catalogue — resolves it through the one function, `landloss.io.koopcache_dir`, so they all share that root. If your `.env` carries `KOOPCACHE_DIR=.koopcache` from an older copy of `.env.example`, you can delete the line; a relative value is anchored to the repo root anyway now
- [ ] Check you can reach `T:\Auckland\Projects\1017473`. Everything that is not a Koordinates layer comes from there: this project's own derived data, the source material NHC supplied, and the National Liquefaction Model's release tree

  Every one of those reads is mirrored into a local cache and refreshed only when
  the copy on `T:` has changed, so the first read of a file is slow and the rest
  do not touch the network at all. The two caches are `.koopcache` and
  `.tdrivecache` at the repo root, both gitignored; set `KOOPCACHE_DIR` or
  `TTDRIVE_SYNC_CACHE_DIR` in `.env` only if you want them somewhere else
- [ ] Check `uv run --frozen pytest` and `uv run --frozen prek -a` both pass before you change anything

### MCP Servers to Activate
- [ ] None in use yet — no MCP calls recorded in the last 30 days. Several are configured in this workspace (Atlassian, Deltek VantagePoint, T+T Intranet, Koordinates, Microsoft 365) and authenticate on first use if you need them

### Skills to Know About
- [ ] `recording-project-context` — turns a meeting transcript, email or note into durable project context: tasks, limitations and improvements in the register workbook, refinements to the objectives and scope, and standalone notes on recurring topics. Use it whenever you hand Claude a transcript
- [ ] `seismic-landslide-hazard-wellington` — the method reference for earthquake-induced landslide work in the Wellington region: Newmark analysis, displacement methods by source mechanism, topographic amplification, and which GWRC datasets to pull rather than rebuild
- [ ] `writing-weekly-updates` — generates the weekly progress update to NHC from the `status.md` files into `release_updates/update_week_of_<monday>.typ`, which you then edit and finalise. Ask for "the weekly update" and it runs
- [ ] `maintaining-status-files` — the `status.md` each submodule of `exposure`, `hazard` and `vul` carries: the Approach / Where it is now / Next sections, keeping it current as the work moves, and how the weekly progress update to NHC is assembled from these files rather than written from scratch
- [ ] `adding-steps-scripts` — the convention every step script folder follows: its own numbered folder, an implementation plan in phases, and a method file describing what is actually implemented. Use it whenever you add or change a step under `steps/`
- [ ] `/clear` — start a fresh context when you switch tasks. The only built-in command showing up in the stats

## Team Tips

**Read the context files before you ask Claude for anything.** This is the most
important habit on this project. `.agents/context/` holds what the project is
for, what was agreed, and what we already know — and `AGENTS.md` points Claude at
them. Today that is:

- `project-objectives.md` and `project-scope.md` — the brief, the four phases,
  and what is explicitly out of scope. Both carry a **Refinements** section
  recording where later discussion clarified or narrowed the original scope
- `nhc-land-cover-and-settlement.md` — how NHC cover attaches to a property, the
  $25k retaining wall cap, insured land, sub-caps
- `land-damage-mechanisms.md` — how land damage actually happens in Wellington
- `data-sources.md` — which dataset comes from where, and what is not obtainable
- `code-structure.md` — the four modules (hazard, exposure, vul, loss), how
  `exposure`, `hazard` and `vul` are split into submodules, the library/scripts
  split, and the causes of financial land loss
- plus notes on the Natural Hazards Portal, event parameters and retaining wall
  fragility

Claude will not infer this from the code. A question asked without it gets an
answer that ignores decisions the team has already made.

**Every step folder carries its own plan and method.** A step under any
`steps/` folder in `src/scripts/landloss/` lives in its own numbered folder
with an implementation plan written in phases and a method file describing the
methodology *as currently implemented*, each bullet pointing at the script,
function or figure where the detail actually lives. Changing a step's scripts
without updating its method file is the one thing the convention exists to
prevent — the report gets assembled from those method files later. The
`adding-steps-scripts` skill has the templates.

**Everything new goes back into context.** If a meeting, email or call produces
something durable, use the `recording-project-context` skill so it lands in
`.agents/context/` rather than staying in a transcript. Add new files to the list
in `AGENTS.md` or nobody — including Claude — will read them.

**The register is append-only.** Tasks, limitations and improvements live in
`.agents/context/register.json` and render to a workbook in the OneDrive project
folder. Add entries; never renumber or rewrite existing ones, because other
documents cite the IDs. The workbook owns the Status column, so anything you tick
off in Excel survives the next append.

**Read `T:` through `tdrive_sync`, never with a bare path.** Opening a `T:` path
directly works right up until you are on a train, and it hits the network on
every run. Each helper mirrors the file into the local cache and refreshes it
only when `T:` has a newer one; which helper you want depends on whose data it
is:

- `ts.local_read` / `ts.get_path` — data this project derives and writes itself,
  under the `BASE_DIR`/`DATA_VERSION` in `tdrive_sync_config.py`
- `ts.get_source_mat` — data someone else supplied to us, under
  `SOURCE_MATERIAL_DIR`. `landloss.io.source_material` wraps it for rasters
- `ts.get_cached` — any other absolute `T:` path, for a tree that has no reason
  to go through `tdrive_sync_config.py` at all. Read-only, no save side, no
  local-only working mode. This is the newest of the three

**The National Liquefaction Model releases are cached the same way now.** The NLM
publishes to its own tree at
`T:\Auckland\Projects\1017473\WorkingMaterial\new_versioned_releases`, one level
above this project's folder because every subproject under 1017473 shares it.
`landloss.io.nlm` reads it through `ts.get_cached`, so ask it for the grid —
`get_nlm_scenario_raster`, or `nlm_release_path` if you want the file rather than
the data — instead of opening a path under `new_versioned_releases` yourself.

**There is one NLM release pin, and it is an enum.** `CORE_NLM_VERSION` in
`landloss.domain.constants` is the release this whole study reads the NLM at —
the scenario grids, the mapped land damage observations, everything. Bump it and
the study follows; there is deliberately no second pin per sub-tree, because two
of them drift and you end up reading one release's hazard against another's
observations without noticing.

The releases themselves are the `NlmRelease` enum next to it. Pick a member
rather than typing a folder name: they are punctuated inconsistently
(`v2025p0_rc4` has an underscore, `v2026p0rc4` does not), and a mistyped release
is a `FileNotFoundError` three directories deep. If a reader genuinely has to
stay on an older release — a file the NLM did not carry forward — name the enum
member at the point of use, where it is visible, rather than adding a constant.

**Never hardcode your username in a path.** The project outputs live in a shared
OneDrive folder, so write `$env:USERPROFILE` (or `Path.home()` in Python). A path
with one person's username in it is wrong for everyone else.

**Plans go in `.agents/plans/`** so the reasoning behind an approach is reviewable
alongside the code.

## Get Started

No starter ticket — pick up whatever is current.

1. Read `AGENTS.md`, then `project-objectives.md` and `project-scope.md` in
   `.agents/context/`. Twenty minutes, and it will save you a lot more
2. Run the example to check your keys and see how data loading works:
   `uv run --frozen python src/scripts/landloss/example_download_linz_data.py`
3. Open the register workbook to see what is open and who owns it
4. Ask Maxim what is live right now — this project moves faster than the docs

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->