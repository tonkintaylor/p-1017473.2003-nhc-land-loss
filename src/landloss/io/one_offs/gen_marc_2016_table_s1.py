"""Parse Marc et al. (2016) Table S1 into one numeric row per (sub)event.

Table S1 of the supporting information to Marc, Hovius, Meunier, Gorum & Uchida
(2016) lists the 40 earthquakes their total landslide area and volume
expression was tested on. It is packaged verbatim as

    src/landloss/io/assets/marc-2016-table-s1.csv

with the published text in each cell ("0.13 (0.115 – 0.145) (M)", "9.5 (4) /
10 (4) / 12 (4)", ...). This one-off turns that into numbers, writing

    src/landloss/io/assets/marc-2016-table-s1-subevents.csv

one row per earthquake, or per sub-event where the paper treated an
earthquake sequence as several sources (the events marked "*"). Event-level
quantities (landslide volume and area, modal slope, A_topo) repeat on each
sub-event's row; source quantities (moment, mean asperity depth, hypocentral
depth) are the sub-event's own. Nothing is corrected: a published range that
does not bracket its value is kept as published, and noted in the assets
README.

    uv run --frozen python src/landloss/io/one_offs/gen_marc_2016_table_s1.py
"""

import math
import re

import numpy as np
import pandas as pd

from landloss.io import ASSETS_DIR

VERBATIM_PATH = ASSETS_DIR / "marc-2016-table-s1.csv"
SUBEVENTS_PATH = ASSETS_DIR / "marc-2016-table-s1-subevents.csv"

_FAULT_TYPE = re.compile(r"[{(]\s*(SS-supershear|SS|R|N|S)\s*[})]\s*$")
# A dash between two numbers, but not the minus of an exponent ("2.2e-4").
_RANGE_DASH = re.compile(r"(?<=[0-9.])\s*[-–]\s*(?=[0-9])")


def _number(text: str) -> float:
    """Read a number as the table writes it, spaces and all ("6.3 e -3")."""
    cleaned = text.replace(" ", "").rstrip("*")
    return float(cleaned) if cleaned and cleaned not in {"x", "?"} else math.nan


def _range(text: str) -> tuple[float, float]:
    parts = _RANGE_DASH.split(text.strip(), maxsplit=1)
    if len(parts) != 2:
        return math.nan, math.nan
    return _number(parts[0]), _number(parts[1])


def parse_volume(cell: str) -> dict:
    """'0.13 (0.115 – 0.145) (M)' to value, range and estimation method."""
    m = re.match(r"^(.*?)\((.*?)\)\s*\((\w)\)\s*$", cell)
    value, low_high, method = m.groups()
    low, high = _range(low_high)
    return {
        "volume_km3": _number(value),
        "volume_min_km3": low,
        "volume_max_km3": high,
        "volume_method": method,
    }


def parse_slope(cell: str) -> dict:
    """'18 (14 – 19)' to the modal slope and its range, in degrees."""
    m = re.match(r"^(.*?)\((.*?)\)\s*$", cell)
    low, high = _range(m.group(2))
    return {
        "modal_slope_deg": _number(m.group(1)),
        "modal_slope_min_deg": low,
        "modal_slope_max_deg": high,
    }


def parse_r0(cell: str) -> list[dict]:
    """'9.5 (4) / 10 (4)', '3(1) !', '? (8-24)' to one dict per sub-event."""
    out = []
    for part in cell.split("/"):
        m = re.match(r"^\s*([?0-9.]+)\s*\(([^)]*)\)\s*(!?)\s*$", part)
        value, spread, inversion = m.groups()
        low, high = _range(spread)
        out.append(
            {
                "r0_km": _number(value),
                "r0_sd_km": _number(spread) if math.isnan(low) else math.nan,
                "r0_min_km": low,
                "r0_max_km": high,
                "r0_from_rupture_inversion": inversion == "!",
            }
        )
    return out


def parse_hypocentre(cell: str) -> list[float]:
    """'19 / 20 / 24' or '4 /' to one depth per sub-event, km."""
    return [_number(part) for part in cell.split("/")]


def parse_moment(cell: str) -> tuple[list[dict], str]:
    """'1.4 (0.15) + 0.72 (0.2) {R}' to one moment per sub-event, and the fault type."""
    fault = _FAULT_TYPE.search(cell)
    body = cell[: fault.start()] if fault else cell
    out = []
    for part in body.split("+"):
        m = re.match(r"^\s*(.*?)\s*\(([^)]*)\)\s*$", part)
        moment = _number(m.group(1)) * 1e19
        spread = _number(m.group(2)) * 1e19
        out.append(
            {
                "moment_nm": moment,
                "moment_2sd_nm": spread,
                "mw": (2.0 / 3.0) * (math.log10(moment) - 9.1),
            }
        )
    return out, fault.group(1) if fault else ""


def parse_earthquake(cell: str) -> dict:
    """'1993, Finisterre*, (PNG)' to year, name, country and the sequence flag."""
    m = re.match(r"^(\d{4}),\s*(.*?),?\s*\(([^)]*)\)\s*$", cell)
    year, name, country = m.groups()
    return {
        "year": int(year),
        "name": name.replace("*", "").strip(" ,"),
        "country": country,
        "sequence": "*" in name,
    }


def build(verbatim: pd.DataFrame) -> pd.DataFrame:
    """Parse every row of the verbatim table."""
    rows = []
    for _, row in verbatim.iterrows():
        event = {"earthquake": row["earthquake"], **parse_earthquake(row["earthquake"])}
        event["comprehensive_inventory"] = bool(row["comprehensive_inventory"])
        event.update(parse_volume(row["volume_km3"]))
        event["area_km2"] = _number(str(row["area_km2"]))
        event.update(parse_slope(row["modal_slope_deg"]))
        event["a_topo"] = float(row["a_topo"])
        sources = parse_r0(row["mean_asperity_depth_r0_km"])
        depths = parse_hypocentre(str(row["hypocentral_depth_km"]))
        moments, fault_type = parse_moment(row["moment_1e19_nm_and_fault_type"])
        event["fault_type"] = fault_type
        count = max(len(sources), len(moments))
        for i in range(count):
            rows.append(
                {
                    **event,
                    "subevent": i + 1,
                    "subevents": count,
                    **(sources[i] if i < len(sources) else {}),
                    "hypocentral_depth_km": depths[i] if i < len(depths) else np.nan,
                    **(moments[i] if i < len(moments) else {}),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    """Parse the verbatim table and write the sub-event table."""
    verbatim = pd.read_csv(VERBATIM_PATH, dtype=str)
    table = build(verbatim)
    table.to_csv(SUBEVENTS_PATH, index=False, encoding="utf-8")
    earthquakes = verbatim.shape[0]
    print(f"Wrote {len(table)} rows for {earthquakes} earthquakes to {SUBEVENTS_PATH}")


if __name__ == "__main__":
    main()
