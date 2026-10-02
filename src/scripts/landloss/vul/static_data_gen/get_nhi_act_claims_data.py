"""Convert the NHC land claims workbooks to CSV.

Run:

    uv run --frozen python src/scripts/landloss/vul/static_data_gen/get_nhi_act_claims_data.py

Reads the two workbooks NHC supplied under SourceMaterial on T: and writes them
as CSV to the paths in ``scripts.landloss.paths``, so the rest of the scripts
can read them without needing a T: drive mapping.
"""

from pathlib import Path

import pandas as pd

from scripts.landloss import paths

SOURCE_DIR = Path(
    r"T:\Auckland\Projects\1017473\1017473.2003\SourceMaterial"
    r"\NHI_Act_Land claims cohort modelling"
)
COHORT_XLSX = SOURCE_DIR / "NHI_Act_Land claims cohort modelling.xlsx"
SETTLED_XLSX = SOURCE_DIR / "NHI_Act_Settled_Land_Claims - 20260916.xlsx"


def main() -> int:
    paths.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    pd.read_excel(COHORT_XLSX).to_csv(paths.NHI_ACT_LAND_CLAIMS_COHORT_CSV, index=False)
    pd.read_excel(SETTLED_XLSX).to_csv(
        paths.NHI_ACT_SETTLED_LAND_CLAIMS_CSV, index=False
    )
    print(f"Wrote {paths.NHI_ACT_LAND_CLAIMS_COHORT_CSV}")
    print(f"Wrote {paths.NHI_ACT_SETTLED_LAND_CLAIMS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
