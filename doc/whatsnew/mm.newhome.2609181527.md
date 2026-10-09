`exposure`, `hazard` and `vul` are now each split into submodules, in both
`src/landloss/` and `src/scripts/landloss/`: `exposure` by insured asset type
(`land`, `rw`, `culverts`), `hazard` by hazard (`liquefaction`, `landslide`,
`shaking`), and `vul` by hazard and then asset type (`vul/liquefaction/land`).
`loss` stays flat. Only the submodules with something in them exist —
`exposure/land`, `hazard/liquefaction`, `hazard/landslide` and
`vul/liquefaction/land`.

Library modules moved accordingly: `landloss.exposure.land_value` and
`landloss.exposure.landform` are now under `landloss.exposure.land`, and
`landloss.hazard.waterways` under `landloss.hazard.liquefaction`.
`landloss.exposure.addresses` and `landloss.hazard.cross_sections` stay where
they are, because more than one submodule reads each of them.

`steps/`, `validations/`, `report/` and `research/` are now submodules of
whichever level the work belongs to rather than of the module, so
`s2_land_value` is under `exposure/land/steps/` while the shared address spine
stays at `exposure/steps/`. Report output directories mirror the module path of
the script that writes them, which renames `report/hazard/liq/` to
`report/hazard/liquefaction/` and moves the land value figures to
`report/exposure/land/land-value/`.

`src/scripts/landloss/paths.py` now exposes `REPO_ROOT`, `REPORT_DIR`,
`RESEARCH_DIR` and `TEMP_DIR`, and `landloss.io` exposes `ASSETS_DIR`. Scripts
and library modules import these instead of counting
`Path(__file__).resolve().parents[N]` for themselves, which no longer works when
a module sits at a depth that can change.
