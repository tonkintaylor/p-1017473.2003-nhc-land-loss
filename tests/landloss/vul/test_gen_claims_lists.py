"""Turning a Site Search export into a claims list."""

import json

import geopandas as gpd
import pytest
from shapely.geometry import box

from scripts.landloss.vul.static_data_gen import gen_claims_lists as gcl


@pytest.mark.parametrize(
    ("number", "folder"),
    [
        ("0085650.3847", "85650.3847"),
        ("1502000.0005", "1502000.0005"),
        ("1001154.0000R", "1001154.0000"),
    ],
)
def test_a_subproject_is_named_as_its_folder_is(number, folder):
    assert gcl.folder_name(number) == folder


@pytest.mark.parametrize(
    ("name", "hint"),
    [
        ("LOGIEST19-EQC13", "2013"),
        ("ANAKIWA124-EQC2013", "2013"),
        ("TAIMATE198-EQCJULY13", "2013"),
        ("HampdenSt-282-EQC2016", "2016"),
        ("OWHIROBAYPDE66-EQC", ""),
        ("EQC 2085 Kenepuru Rd", ""),
    ],
)
def test_an_event_hint_is_read_off_the_name(name, hint):
    assert gcl.name_hint(name) == hint


def test_claims_are_tagged_with_the_authority_they_fall_in(tmp_path):
    export = tmp_path / "export.json"
    export.write_text(
        json.dumps(
            {
                "status": "success",
                "data": [
                    {
                        "project_number_full": "0085650.0002",
                        "project_name": "INSIDE-EQC13",
                        "start_date": "2013-08-01T00:00:00",
                        "points": [[174.5, -41.5]],
                    },
                    {
                        "project_number_full": "0085650.0001",
                        "project_name": "OUTSIDE-EQC",
                        "start_date": "2013-07-23T00:00:00",
                        "points": [[176.0, -39.0]],
                    },
                    {
                        "project_number_full": "0085650.0003",
                        "project_name": "NOWHERE-EQC",
                        "start_date": "2013-09-01T00:00:00",
                        "points": None,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    study_areas = gpd.GeoDataFrame(
        {"name": ["Example City"]},
        geometry=[box(174.0, -42.0, 175.0, -41.0)],
        crs=gcl.WGS84,
    )
    claims = gcl.build(gcl.read_export(export), study_areas).set_index("subproject")
    assert claims.loc["85650.0002", "ta_name"] == "Example City"
    assert claims.loc["85650.0002", "in_study_area"]
    assert claims.loc["85650.0002", "name_event_hint"] == "2013"
    assert not claims.loc["85650.0001", "in_study_area"]
    # No coordinates is kept, and is outside rather than guessed in.
    assert not claims.loc["85650.0003", "in_study_area"]
    assert claims.loc["85650.0001", "start_date"] == "2013-07-23"
    assert claims.loc["85650.0002", "programme"] == "0085650"
