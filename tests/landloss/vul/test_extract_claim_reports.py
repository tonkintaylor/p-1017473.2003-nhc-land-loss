"""Reading figures out of a T+T claim report.

The report here is invented, written in the layout of the recent T+T claim
report template -- header, property damage bullets, the construction issues
tick boxes and the Summary of Information table -- so no client report is
committed.
"""

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from scripts.landloss.vul.static_data_gen import extract_claim_reports as ecr
from scripts.landloss.vul.static_data_gen import fetch_claim_reports as fcr

NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


def cell(text: str, *, checkbox: bool = False) -> str:
    body = f"<w:tc><w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p></w:tc>"
    # Word wraps a check-box cell in a content control, which hides it from a
    # search of the row's direct children.
    return f"<w:sdt><w:sdtContent>{body}</w:sdtContent></w:sdt>" if checkbox else body


def table(rows: list[list[str]], *, checkboxes: bool = False) -> str:
    out = []
    for row in rows:
        cells = [cell(row[0])] + [cell(text, checkbox=checkboxes) for text in row[1:]]
        out.append("<w:tr>" + "".join(cells) + "</w:tr>")
    return "<w:tbl>" + "".join(out) + "</w:tbl>"


REPORT = [
    paragraph("Job No: 9999999.0001"),
    paragraph("1 March 2024"),
    paragraph("Example Insurance"),
    paragraph("Claim for Natural Disaster (Landslip) Damage"),
    paragraph("A Person, 1 Example Street, Suburb, Wellington"),
    paragraph("Insurer claim number: X123"),
    paragraph(
        "As requested, T+T inspected the subject property on 12 February 2024 "
        "to assess the claim."
    ),
    paragraph("This claim relates to a rain event that occurred in January 2024."),
    paragraph("Property damage"),
    paragraph("The damage consists of a 6.5 m wide landslip which has resulted in:"),
    paragraph("Collapse to 2 m length of RTW 1;"),
    paragraph("Damage to 1.5 m length of RTW 1; and"),
    paragraph("Damage to 3 m length of RTW 2."),
    paragraph("NHC considerations"),
    paragraph("Damage as defined by the Natural Hazards Insurance Act 2023."),
    paragraph("Conceptual remedial works"),
    paragraph("Remove debris working from the top down (est. 8 m3)"),
    paragraph("Repair/Replace RTW1 - Construct a timber pole retaining wall having:"),
    paragraph("6 m long wall"),
    paragraph("2.1m maximum retained height"),
    paragraph("Minimum pole embedment 2.8 m, 4.9 m total pole length"),
    paragraph("250 mm SED timber poles at 1.2 m centres"),
    paragraph("Additional information for cost estimation:"),
    table(
        [
            ["Construction Issues", "Easy", "Moderate", "Hard", "N/A"],
            ["Construction Access", "☐", "☒", "☐", ""],
            ["Earthworks required", "☒", "☐", "☐", ""],
            ["Constructability/Reinstatement", "☐", "☐", "☐", ""],
        ],
        checkboxes=True,
    ),
    table([["TOTAL (Excluding GST)", "$ 18,000"]]),
    paragraph("Summary of Information"),
    table(
        [
            ["Is this natural disaster damage?", "Yes (Landslip)"],
            ["Area of insured land damaged:", ""],
            ["Evacuated:", "12 m2"],
            ["Inundated:", "Nil"],
            ["Insured area of insured land at imminent risk", ""],
            ["Evacuation:", "4m2"],
            ["New inundation:", "3m2"],
            ["Re-inundation:", "Nil"],
            ["Main access way within 60 m of dwelling", "N/A"],
            ["Retaining Walls supporting or protecting insured land", ""],
            ["Retaining wall 1 – Timber pole retaining wall – 200 mm poles:", ""],
            ["Whole wall length:", "10m"],
            ["Retained height:", "1.8m"],
            ["Damaged: (insured face area):", "6.3m2"],
            ["Imminent damage: (insured face area):", "Nil"],
            ["Insured wall: (face area):", "18m2"],
            ["Total wall: (face area):", "18m²"],
            ["Retaining wall 2 – Crib retaining wall:", ""],
            ["Whole wall length:", "4m"],
            ["Retained height:", "1m"],
            ["Damaged: (insured face area):", "Nil"],
            ["Imminent damage: (insured face area):", "2m2"],
            ["Insured wall: (face area):", "4m2"],
            ["Total wall: (face area):", "4m²"],
            ["Dwelling and appurtenant structure(s)", "N/A"],
            ["Bridges or culverts situated on insured land", "N/A"],
            ["Conceptual remedial works:", ""],
            ["Construct new timber pole retaining wall", "$18,000 + construction"],
        ]
    ),
    paragraph("Applicability"),
]


@pytest.fixture(scope="module")
def extracted(tmp_path_factory) -> ecr.Extracted:
    path = tmp_path_factory.mktemp("report") / "report.docx"
    document = f"<w:document {NS}><w:body>{''.join(REPORT)}</w:body></w:document>"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
    return ecr.extract(ecr.read_blocks(Path(path)), subproject="9999999.0001")


def test_the_header_is_read(extracted):
    report = extracted.report
    assert report["job_number"] == "9999999.0001"
    assert report["report_date"] == "1 March 2024"
    assert report["addressee"] == "Example Insurance"
    assert report["claim_type"] == "Landslip"
    # The claimant's name is dropped; the site address is kept.
    assert report["address"] == "1 Example Street, Suburb, Wellington"
    assert report["claim_number"] == "X123"
    assert report["inspection_date"] == "12 February 2024"


def test_the_event_and_act_are_read(extracted):
    report = extracted.report
    assert report["event_month"] == "January"
    assert report["event_year"] == "2024"
    assert report["act"] == "NHI Act"


def test_land_damage_and_imminent_risk_come_off_the_summary(extracted):
    report = extracted.report
    assert report["evacuated_m2"] == pytest.approx(12.0)
    assert report["inundated_m2"] == 0.0  # Nil is zero, not blank
    assert report["imminent_evacuation_m2"] == pytest.approx(4.0)
    assert report["imminent_new_inundation_m2"] == pytest.approx(3.0)
    assert report["imminent_reinundation_m2"] == 0.0
    assert report["main_access_way"] == "N/A"
    assert report["missing"] == ""


def test_each_wall_in_the_summary_is_a_row(extracted):
    first, second = extracted.walls
    assert first["wall_number"] == 1
    assert first["construction"] == "Timber pole retaining wall"
    assert first["whole_length_m"] == pytest.approx(10.0)
    assert first["retained_height_m"] == pytest.approx(1.8)
    assert first["damaged_face_m2"] == pytest.approx(6.3)
    assert first["imminent_face_m2"] == 0.0
    assert first["total_face_m2"] == pytest.approx(18.0)
    assert second["construction"] == "Crib retaining wall"
    assert second["damaged_face_m2"] == 0.0
    assert second["imminent_face_m2"] == pytest.approx(2.0)


def test_damaged_lengths_come_off_the_damage_bullets(extracted):
    first, second = extracted.walls
    # Collapse and damage both count as damaged; only collapse as collapsed.
    assert first["damaged_length_m"] == pytest.approx(3.5)
    assert first["collapsed_length_m"] == pytest.approx(2.0)
    assert second["damaged_length_m"] == pytest.approx(3.0)
    assert extracted.report["wall_lengths_m"] == "10;4"


def test_damaged_face_areas_reach_the_report_row(extracted):
    report = extracted.report
    assert report["wall_damaged_faces_m2"] == "6.3;0"
    assert report["damaged_face_total_m2"] == pytest.approx(6.3)
    assert report["imminent_face_total_m2"] == pytest.approx(2.0)


def test_damaged_length_is_also_read_off_the_face_area(extracted):
    first, second = extracted.walls
    # 6.3 m2 over a 1.8 m retained height.
    assert first["damaged_length_from_face_m"] == pytest.approx(3.5)
    assert second["damaged_length_from_face_m"] == 0.0


def test_a_wall_with_only_imminent_damage_is_not_counted_damaged(extracted):
    assert extracted.report["n_walls"] == 2
    assert extracted.report["n_walls_damaged"] == 1


def test_the_tick_boxes_become_the_costing_tools_ratings(extracted):
    report = extracted.report
    assert report["construction_access"] == "M"
    assert report["earthworks_required"] == "E"
    # Nothing ticked is blank, never a guess.
    assert report["constructability_reinstatement"] == ""


def test_the_remedial_works_are_read(extracted):
    report = extracted.report
    assert report["landslip_width_m"] == pytest.approx(6.5)
    assert report["debris_volume_m3"] == pytest.approx(8.0)
    assert report["design_consent_cost_excl_gst_nzd"] == pytest.approx(18_000.0)
    (wall,) = extracted.remedial_walls
    assert wall["replaces"] == "RTW1"
    assert wall["construction"] == "timber pole"
    assert wall["length_m"] == pytest.approx(6.0)
    assert wall["max_retained_height_m"] == pytest.approx(2.1)
    assert wall["pole_sed_mm"] == pytest.approx(250.0)
    assert wall["embedment_m"] == pytest.approx(2.8)


def test_a_report_without_the_summary_says_so():
    result = ecr.extract([ecr.Block("Job No: 1.1"), ecr.Block("No table here")])
    assert result.report["missing"] == "summary table not found"
    assert result.walls == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [("10m2", 10.0), ("2.5 m²", 2.5), ("Nil", 0.0), ("N/A", None), ("", None)],
)
def test_areas(text, expected):
    assert ecr.area(text) == expected


def test_a_length_is_not_read_off_an_area():
    assert ecr.length("24m2") is None
    assert ecr.length("19m") == pytest.approx(19.0)


# The 2016 EQC template: the same summary table in slightly different words,
# no construction issues tick boxes, and notes under the table.
REPORT_2016 = [
    paragraph("Job No: 8888888.0001"),
    paragraph("1 February 2017"),
    paragraph("Earthquake Commission"),
    paragraph("Claim for Natural Disaster (Landslip) Damage"),
    paragraph("B Person, 2 Example Road, Suburb, Wellington"),
    paragraph("EQC Ref: 2016/000001"),
    paragraph(
        "The landslip is believed to have occurred as a result of the "
        "14 November 2016 Kaikoura earthquake."
    ),
    paragraph("Property Damage"),
    paragraph("Collapse of 4 m length of RTW 2."),
    paragraph("EQC Considerations"),
    paragraph("Potential Remedial Works"),
    paragraph(
        "removing the damaged wall and constructing a timber pole retaining wall:"
    ),
    paragraph("4 m long wall;"),
    paragraph("1.2 m  maximum retained height;"),
    paragraph("Summary of Information"),
    table(
        [
            ["Is this Natural Disaster damage?", "Yes (Landslip)"],
            ["Area of Land damaged", ""],
            ["Evacuated:", "nil"],
            ["Inundated:", "3 m2"],
            ["Area of Land at imminent risk", ""],
            ["Evacuation:", "1 m2"],
            ["New Inundation:", "nil"],
            ["Re-inundation", "nil"],
            ["RTW 2 – Concrete block retaining wall:", ""],
            ["Whole wall length", "12 m"],
            ["Retained height", "0.5 m to 1.2 m"],
            ["Damaged: (face area);", "4 m2"],
            ["At imminent risk: (face area);", "1 m2"],
            ["Insured: (face area);", "10 m2"],
            ["Total Wall: (face area);", "10 m²"],
            ["Dwelling & Appurtenant Structures", "N/A"],
            ["Remedial Option:", ""],
            ["Rebuild RTW 2", "$9,000 + Items TBA*"],
        ]
    ),
    paragraph("Note: RTW 2 is shared with the neighbouring property."),
    paragraph("Applicability"),
]


@pytest.fixture(scope="module")
def extracted_2016(tmp_path_factory) -> ecr.Extracted:
    path = tmp_path_factory.mktemp("report_2016") / "report.docx"
    document = f"<w:document {NS}><w:body>{''.join(REPORT_2016)}</w:body></w:document>"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
    return ecr.extract(ecr.read_blocks(Path(path)), subproject="8888888.0001")


def test_the_2016_header_and_event_are_read(extracted_2016):
    report = extracted_2016.report
    assert report["claim_number"] == "2016/000001"
    assert report["event_cause"] == "earthquake"
    assert report["event_month"] == "November"
    assert report["event_year"] == "2016"


def test_the_2016_summary_table_is_read(extracted_2016):
    report = extracted_2016.report
    assert report["evacuated_m2"] == 0.0
    assert report["inundated_m2"] == pytest.approx(3.0)
    assert report["imminent_evacuation_m2"] == pytest.approx(1.0)
    assert report["dwelling"] == "N/A"
    assert report["missing"] == ""
    assert report["remedial_works"].endswith("$9,000 + Items TBA*")


def test_a_2016_wall_block_is_read(extracted_2016):
    (wall,) = extracted_2016.walls
    assert wall["wall_number"] == 2
    assert wall["construction"] == "Concrete block retaining wall"
    assert wall["whole_length_m"] == pytest.approx(12.0)
    # A height range is charged on its tallest section, with the range kept.
    assert wall["retained_height_m"] == pytest.approx(1.2)
    assert wall["retained_height_text"] == "0.5 m to 1.2 m"
    assert wall["imminent_face_m2"] == pytest.approx(1.0)
    assert wall["insured_face_m2"] == pytest.approx(10.0)
    assert wall["damaged_length_m"] == pytest.approx(4.0)


def test_notes_under_the_summary_are_kept(extracted_2016):
    assert "shared" in extracted_2016.report["notes"]


def test_the_2016_remedial_wall_is_read(extracted_2016):
    (wall,) = extracted_2016.remedial_walls
    assert wall["construction"] == "timber pole"
    assert wall["length_m"] == pytest.approx(4.0)
    assert wall["max_retained_height_m"] == pytest.approx(1.2)


def test_rain_is_told_from_an_earthquake(extracted):
    assert extracted.report["event_cause"] == "rain"


def blocks(*items: str | tuple[str, ...]) -> list[ecr.Block]:
    """Build blocks directly: a string is a paragraph, a tuple a table row."""
    return [
        ecr.Block(" | ".join(item), item)
        if isinstance(item, tuple)
        else ecr.Block(item)
        for item in items
    ]


def test_the_2013_template_is_read_and_a_declined_claim_is_marked():
    result = ecr.extract(
        blocks(
            "T&T Ref : 7777777.0001",
            "18 September 2013",
            "Earthquake Commission",
            "Claim for Natural Disaster (Earthquake) Damage",
            "C Person, 3 Example Road, Suburb",
            "EQC Ref: 2013/000001",
            "Summary Information (all costs excl GST)",
            ("Is this Natural Disaster damage?", "No"),
            ("Area of Land damaged", ""),
            ("Evacuated:", "Nil"),
            ("Inundated:", "Nil"),
            ("Area of Land at imminent risk", ""),
            ("Evacuation:", "Nil"),
            ("Inundation:", "2 m2"),
            ("Retaining Walls within 8m of Dwelling or Appurtenant Structure", "N/A"),
            "Applicability",
        )
    )
    report = result.report
    assert report["job_number"] == "7777777.0001"
    assert report["report_date"] == "18 September 2013"
    # No event sentence, so the cause comes off the claim heading.
    assert report["event_cause"] == "earthquake"
    assert report["claim_accepted"] is False
    assert report["evacuated_m2"] == 0.0
    # 2013's single imminent "Inundation" row is new inundation.
    assert report["imminent_new_inundation_m2"] == pytest.approx(2.0)


def test_an_unnumbered_wall_and_a_replacement_in_another_material_are_read():
    result = ecr.extract(
        blocks(
            "Property Damage",
            "Rotation to a 4 m section of RTW1 within 8 m of the dwelling,",
            "EQC Considerations",
            "Potential Remedial Works",
            "would comprise replacing the damaged section of RTW1 as follows:",
            "4 m long Type II 190 mm block masonry wall",
            "1.4 m  maximum retained height",
            "Summary of Information",
            ("Is this Natural Disaster damage?", "Yes (Landslip)"),
            ("Retaining Walls supporting or protecting insured land", ""),
            ("Timber Pole retaining wall – 200 mm dia poles at 2m centres:", ""),
            ("Whole wall length", "6 m"),
            ("Retained height", "1.3 m"),
            ("Damaged: (face area);", "5 m2"),
            ("Dwelling & Appurtenant Structures", "n/a"),
            "Applicability",
        )
    )
    (wall,) = result.walls
    assert wall["wall_number"] == 1
    assert wall["construction"] == "Timber Pole retaining wall"
    assert wall["whole_length_m"] == pytest.approx(6.0)
    assert wall["damaged_face_m2"] == pytest.approx(5.0)
    # "section of RTW1" counts as a damaged length, matched to wall 1.
    assert wall["damaged_length_m"] == pytest.approx(4.0)
    (remedial,) = result.remedial_walls
    assert remedial["replaces"] == "RTW1"
    assert remedial["construction"] == "Type II 190 mm block masonry"
    assert remedial["length_m"] == pytest.approx(4.0)
    assert remedial["max_retained_height_m"] == pytest.approx(1.4)
    assert result.report["claim_accepted"] is True


def test_a_claims_list_is_extracted_across_projects_with_its_coordinates(
    tmp_path, monkeypatch
):
    assets = tmp_path / "assets"
    monkeypatch.setattr(fcr, "CLAIM_REPORTS_ASSETS_DIR", assets)
    document = f"<w:document {NS}><w:body>{''.join(REPORT)}</w:body></w:document>"
    for project, sub in (("85650", "0001"), ("86101", "0002")):
        report = tmp_path / f"{project}.docx"
        with zipfile.ZipFile(report, "w") as archive:
            archive.writestr("word/document.xml", document)
        fcr.write_index(
            fcr.index_path(project),
            {
                f"{project}.{sub}": fcr.IndexRow(
                    project_number=project,
                    subproject_number=sub,
                    subproject=f"{project}.{sub}",
                    status=fcr.FETCHED,
                    cached_path=str(report),
                )
            },
        )
    claims = tmp_path / "example-list.csv"
    claims.write_text(
        "subproject,programme,start_date,lon,lat,ta_name,in_study_area,"
        "name_event_hint\n"
        "85650.0001,0085650,2013-08-01,174.77,-41.29,Wellington City,True,2013\n"
        "86101.0002,0086101,2016-11-16,173.28,-41.27,,False,\n",
        encoding="utf-8",
    )
    results = ecr.run_list(claims, out_dir=tmp_path / "out")
    assert [r.report["subproject"] for r in results] == ["85650.0001", "86101.0002"]
    assert results[0].report["ta_name"] == "Wellington City"
    assert results[0].report["lat"] == "-41.29"
    assert results[0].report["list_start_date"] == "2013-08-01"
    assert (tmp_path / "out" / ecr.REPORTS_NAME).exists()
    only_study_area = ecr.run_list(
        claims, study_area_only=True, out_dir=tmp_path / "out2"
    )
    assert [r.report["subproject"] for r in only_study_area] == ["85650.0001"]


@pytest.mark.parametrize(
    ("sentence", "construction", "length", "height"),
    [
        (
            "Construct a 16m long anchored sprayed concrete retaining wall.",
            "anchored sprayed concrete",
            16.0,
            None,
        ),
        (
            (
                "Construct an anchored 3.0 m long, 2.5 m high sprayed concrete "
                "retaining wall."
            ),
            "anchored sprayed concrete",
            3.0,
            2.5,
        ),
        ("Construct a 3 m long gravity retaining wall.", "gravity", 3.0, None),
        (
            "Construct a cantilevered timber pole retaining wall as follows:",
            "cantilevered timber pole",
            None,
            None,
        ),
    ],
)
def test_dimensions_written_into_the_construct_phrase_are_lifted_out(
    sentence, construction, length, height
):
    (wall,) = ecr.read_remedial_walls([sentence])
    assert wall.construction == construction
    assert wall.length_m == length
    assert wall.max_retained_height_m == height


@pytest.fixture(scope="module")
def several_landslips() -> ecr.Extracted:
    """A 2013 report covering three landslips, one column each in the summary."""
    return ecr.extract(
        blocks(
            "Property Damage",
            "Landslip 1:",
            "A 2.0 m wide landslip, 5.0 m north of the dwelling; and",
            "Rotation of a 2.0 m wide section of Retaining wall 1.",
            "Landslip 2:",
            "A 2.7 m wide landslip, 4.6 m north-east of the dwelling; and",
            "Collapse of a 2.7 m wide section of Retaining wall 1.",
            "Landslip 3:",
            "A 2.0 m wide landslip, adjacent to the dwelling; and",
            "Failure of a 2.0 m wide section of Retaining wall 2.",
            "EQC Considerations",
            "Potential Remedial Works",
            "would comprise constructing three cantilevered timber pole retaining "
            "walls as follows:",
            "Landslip 1 / Retaining wall A:",
            "2.0 m long wall",
            "1.0 m  maximum retained height",
            "200 mm diameter SED timber poles (H5) in 400 mm diameter holes",
            "Landslip 3 / Retaining wall C:",
            "2.0 m long wall",
            "800 mm  maximum retained height",
            ("TOTAL (Excluding GST)", "$5,500"),
            ("Construct wall", "$3,000"),
            ("TOTAL (Excluding GST)", "$5,500"),
            "Summary Information (all costs excl GST)",
            ("Is this Natural Disaster damage?", "Yes"),
            ("Area of Land damaged", "", "", ""),
            ("Evacuated:", "1 m2", "2 m2", "1 m2"),
            ("Inundated:", "3 m2", "Nil", "2 m2"),
            ("Area of Land at imminent risk", "", "", ""),
            ("Evacuation:", "1 m2", "1 m2", "1 m2"),
            ("Re-inundation:", "1 m2", "Nil", "1 m2"),
            ("New inundation", "Nil", "1 m2", "Nil"),
            ("Retaining Walls within 8 m of Dwelling or Appurtenant Structure", ""),
            (
                (
                    "Retaining wall 1 – 160 mm dia SED timber poles at 2 m centres; "
                    "up to 800 mm retained height:"
                ),
                "",
            ),
            ("Damaged: (face area - m2);", "2 m2", "2 m2", "Nil"),
            ("At imminent risk: (face area - m2);", "Included above", "Nil", "Nil"),
            (
                (
                    "Retaining wall 2 – 160 mm dia SED timber poles at 2.2 m centres; "
                    "up to 850 mm retained height:"
                ),
                "",
            ),
            ("Damaged: (face area - m2);", "Nil", "Nil", "2 m2"),
            ("Total Cost", "$16,500"),
            "Applicability",
        )
    )


def test_areas_in_one_column_per_landslip_are_summed(several_landslips):
    report = several_landslips.report
    assert report["evacuated_m2"] == pytest.approx(4.0)
    assert report["inundated_m2"] == pytest.approx(5.0)
    assert report["imminent_evacuation_m2"] == pytest.approx(3.0)
    assert report["imminent_reinundation_m2"] == pytest.approx(2.0)
    assert report["imminent_new_inundation_m2"] == pytest.approx(1.0)
    assert report["missing"] == ""


def test_every_landslip_is_counted(several_landslips):
    report = several_landslips.report
    assert report["n_landslips"] == 3
    assert report["landslip_widths_m"] == "2;2.7;2"
    assert report["landslip_width_m"] == pytest.approx(2.7)


def test_a_2013_wall_takes_its_height_from_the_heading(several_landslips):
    first, second = several_landslips.walls
    assert first["retained_height_m"] == pytest.approx(0.8)
    assert second["retained_height_m"] == pytest.approx(0.85)
    # No length row in a 2013 wall block, so none is invented.
    assert first["whole_length_m"] is None
    # Damaged face summed across the landslips' columns.
    assert first["damaged_face_m2"] == pytest.approx(4.0)
    assert second["damaged_face_m2"] == pytest.approx(2.0)
    # "wide section of Retaining wall 1", twice, and "Failure of" wall 2.
    assert first["damaged_length_m"] == pytest.approx(4.7)
    assert first["collapsed_length_m"] == pytest.approx(2.7)
    assert second["damaged_length_m"] == pytest.approx(2.0)


def test_several_remedial_walls_from_one_sentence(several_landslips):
    first, second = several_landslips.remedial_walls
    assert first["label"] == "A"
    assert first["construction"] == "cantilevered timber pole"
    assert first["length_m"] == pytest.approx(2.0)
    assert first["max_retained_height_m"] == pytest.approx(1.0)
    assert first["pole_sed_mm"] == pytest.approx(200.0)
    assert second["label"] == "C"
    assert second["max_retained_height_m"] == pytest.approx(0.8)


def test_per_wall_estimates_are_summed_and_flagged_as_including_construction(
    several_landslips, extracted
):
    report = several_landslips.report
    # The two per-wall totals, not the summary "Total Cost" as well.
    assert report["design_consent_cost_excl_gst_nzd"] == pytest.approx(11_000.0)
    assert report["estimate_includes_construction"] is True
    # The 2021 template prices design and consent only.
    assert extracted.report["estimate_includes_construction"] is False


def test_an_inspection_fee_is_not_construction():
    result = ecr.extract(
        blocks(
            ("Construction observations and Producer Statements", "$3,000"),
            ("Construct Retaining Wall", "TBA*"),
            ("TOTAL (Excluding GST)", "$10,000 + Items TBA*"),
        )
    )
    assert result.report["estimate_includes_construction"] is False
    assert result.report["design_consent_cost_excl_gst_nzd"] == pytest.approx(10_000.0)


def test_a_declined_claim_is_not_reported_as_missing_fields():
    result = ecr.extract(
        blocks(
            "Summary of Information",
            ("Is this Natural Disaster damage?", "No*"),
            ("Area of Land damaged", ""),
            ("Evacuated:", "N/A"),
            "Applicability",
        )
    )
    assert result.report["claim_accepted"] is False
    assert result.report["missing"] == ""


def test_a_heading_without_brackets_and_a_bare_claim_number_are_read():
    header = ecr.read_header(
        blocks(
            "Job No: 1501000.9999",
            "15 October 2021",
            "Example Insurance",
            "Claim for Natural Disaster Landslip Damage",
            "A Person, 1 Example Street, Wellington",
            "P034000000",
        )
    )
    assert header["claim_type"] == "Landslip"
    assert header["address"] == "1 Example Street, Wellington"
    assert header["claim_number"] == "P034000000"


def test_na_in_an_area_row_is_none_of_that_land():
    result = ecr.extract(
        blocks(
            "Summary of Information",
            ("Is this natural disaster damage?", "Yes (Landslip)"),
            ("Area of insured land damaged:", ""),
            ("Evacuated:", "1.5 m2"),
            ("Inundated:", "6.5 m2"),
            ("Area of insured land at imminent risk", ""),
            ("Evacuation:", "1 m2"),
            ("New inundation:", "N/A"),
            ("Re-inundation:", "2 m2"),
            "Applicability",
        )
    )
    assert result.report["imminent_new_inundation_m2"] == 0.0
    assert result.report["missing"] == ""


def test_the_access_way_block_does_not_overwrite_the_claims_own_areas():
    result = ecr.extract(
        blocks(
            "Summary of Information",
            ("Is this natural disaster damage?", "Yes (Landslip)"),
            ("Area of insured land damaged:", ""),
            ("Evacuated:", "4.0 m2"),
            ("Inundated:", "4.0 m2"),
            ("Area of insured land at imminent risk", ""),
            ("Evacuation:", "3.0 m2"),
            ("New inundation:", "1.0 m2"),
            ("Re-inundation:", "4.0 m2"),
            ("Main access way within 60 m of dwelling", ""),
            ("Area of insured land damaged on or supporting main access way:", ""),
            ("Evacuated:", "Nil"),
            ("Inundated:", "Nil"),
            (
                (
                    "Area of insured land at imminent risk on or supporting main "
                    "access way:"
                ),
                "",
            ),
            ("Evacuation:", "Included in areas above"),
            ("New Inundation:", "Nil"),
            ("Re-inundation:", "Nil"),
            "Applicability",
        )
    )
    report = result.report
    assert report["evacuated_m2"] == pytest.approx(4.0)
    assert report["imminent_evacuation_m2"] == pytest.approx(3.0)
    assert report["imminent_reinundation_m2"] == pytest.approx(4.0)
    assert report["access_evacuated_m2"] == 0.0
    assert report["access_imminent_evacuation_m2"] is None
    assert report["missing"] == ""


def test_rows_a_storm_flood_table_does_not_carry_are_absent_not_missing():
    result = ecr.extract(
        blocks(
            "Summary of Information",
            ("Is this natural disaster damage?", "Yes (Storm/Flood)"),
            ("Area of insured land damaged:", ""),
            ("Inundated:", "86.5 m2"),
            ("Area of insured land at imminent risk", ""),
            ("Re-inundation: due to imminent risk of collapsed RTW1", "2.0 m2"),
            "Applicability",
        )
    )
    report = result.report
    assert report["inundated_m2"] == pytest.approx(86.5)
    assert report["imminent_reinundation_m2"] == pytest.approx(2.0)
    assert report["missing"] == ""
    assert report["absent_rows"] == (
        "evacuated_m2;imminent_evacuation_m2;imminent_new_inundation_m2"
    )


def test_one_column_per_inspection_is_counted(several_landslips):
    result = ecr.extract(
        blocks(
            "Summary of Information",
            ("Is this natural disaster damage?", "Yes", "Yes", "Yes"),
            ("Area of insured land damaged:", "", "", ""),
            ("Evacuated:", "76 m2 *", "20 m2 (15 m2 is new damage)", "12 m2"),
            "Applicability",
        )
    )
    assert result.report["summary_columns"] == 3
    assert several_landslips.report["summary_columns"] == 3


def test_the_cached_text_reads_the_same_as_the_whole_report(tmp_path):
    document = f"<w:document {NS}><w:body>{''.join(REPORT)}</w:body></w:document>"
    whole = tmp_path / "Report.docx"
    with zipfile.ZipFile(whole, "w") as archive:
        archive.writestr("word/document.xml", document)
    text = tmp_path / "Report.docx.document.xml"
    text.write_text(document, encoding="utf-8")
    assert ecr.read_blocks(text) == ecr.read_blocks(whole)


def test_totals_add_the_access_way_to_the_land_by_the_dwelling():
    result = ecr.extract(
        blocks(
            "Summary of Information",
            ("Is this natural disaster damage?", "Yes (Landslip)"),
            ("Area of insured land damaged:", ""),
            ("Evacuated:", "0.5 m2"),
            ("Inundated:", "0.5 m2"),
            ("Main access way within 60 m of dwelling", ""),
            (
                (
                    "Insured area of insured land damaged on or supporting main "
                    "access way:"
                ),
                "",
            ),
            ("Inundated:", "8.0 m2"),
            "Applicability",
        )
    )
    report = result.report
    assert report["inundated_m2"] == pytest.approx(0.5)
    assert report["access_inundated_m2"] == pytest.approx(8.0)
    assert report["total_inundated_m2"] == pytest.approx(8.5)
    assert report["total_evacuated_m2"] == pytest.approx(0.5)


def test_damage_only_on_the_access_way_still_totals():
    result = ecr.extract(
        blocks(
            "Summary of Information",
            ("Is this natural disaster damage?", "Yes (Landslip)"),
            ("Land within 8 m of dwelling or appurtenant structures", "N/A"),
            ("Main access way within 60 m of dwelling", "Yes"),
            ("Area of insured land damaged on or supporting main access way:", ""),
            ("Evacuated:", "1 m2"),
            "Applicability",
        )
    )
    report = result.report
    assert report["evacuated_m2"] is None
    assert report["total_evacuated_m2"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("line", "address"),
    [
        ("A Person, 44 Example Road, Suburb", "44 Example Road, Suburb"),
        (
            "A Person and B Person, 26 Example Street, Wellington",
            "26 Example Street, Wellington",
        ),
        ("Dr A Person, 122 Example Road, Suburb", "122 Example Road, Suburb"),
        ("A Person, Lot 2 DP 12345, Example Road", "Lot 2 DP 12345, Example Road"),
        ("A Person, Example Road, Suburb", "Example Road, Suburb"),
        ("35A Example Drive, Tawa", "35A Example Drive, Tawa"),
        ("An Example Family 128 Trust, 84 Example Road", "84 Example Road"),
        ("Example Trust No.2, 37 Example Street, Suburb", "37 Example Street, Suburb"),
        ("A Person 1 Example Street, #3, Suburb", "1 Example Street, #3, Suburb"),
        ("Body Corporate 12345, 5 & 5A Example Terrace", "5 & 5A Example Terrace"),
        ("Unit 8, 30 Example Street, Suburb", "Unit 8, 30 Example Street, Suburb"),
        ("FLAT 1 9A Example Street, Suburb", "FLAT 1 9A Example Street, Suburb"),
    ],
)
def test_the_claimants_name_is_taken_off_the_address(line, address):
    assert ecr.site_address(line) == address


@pytest.fixture(scope="module")
def nhi_act() -> ecr.Extracted:
    """A report on the NHI Act template, with its unfilled example wall block."""
    return ecr.extract(
        blocks(
            "Job No: 1501000.9999",
            "25 November 2025",
            "C/- Example Project Services Limited",
            "By Email",
            "Claim for Natural Hazard (Landslide) Damage",
            "A Person and B Person, 330 Example Esplanade, Suburb, Wellington, 6023",
            "Claim Number P000000000 L",
            "This claim relates to a landslide that occurred in June 2025 following "
            "a period of heavy rainfall.",
            "The damage to the insured property consists of an 8 m wide landslide.",
            "Assessed under the Natural Hazards Insurance Act 2023.",
            "Summary of damage information",
            ("Is this natural hazard damage?", "Yes (Landslide)"),
            ("Land within 8 m of dwelling or appurtenant structures", "Yes"),
            ("Area of insured land damaged:", ""),
            ("Evacuated:", "Nil"),
            ("Inundated on land:", "130 m2 / 210 m3"),
            ("Area of insured land subject to imminent damage:", ""),
            ("Evacuation:", "Nil"),
            ("New inundation:", "12 m2 / 6 m3"),
            ("Re-inundation on land:", "130 m2 / 40 m3"),
            ("Main access way within 60 m of dwelling", "NA"),
            (
                (
                    "Retaining walls supporting or protecting insured buildings and/or "
                    "land located within 60 m of dwelling (or an appurtenant structure)"
                ),
                "NA**",
            ),
            ("Timber pole retaining wall – 200 mm diameter poles at 2 m centres:", ""),
            ("Whole wall length:", "m"),
            ("Retained height:", "m to m"),
            ("Damaged: (insured face area):", "m2"),
            ("Dwelling and appurtenant structure(s)", ""),
            "Applicability",
        )
    )


def test_the_nhi_act_template_is_read(nhi_act):
    report = nhi_act.report
    assert report["claim_type"] == "Landslide"
    assert report["report_kind"] == "land"
    assert report["claim_accepted"] is True
    assert report["evacuated_m2"] == 0.0
    assert report["inundated_m2"] == pytest.approx(130.0)
    assert report["inundated_volume_m3"] == pytest.approx(210.0)
    assert report["imminent_new_inundation_m2"] == pytest.approx(12.0)
    assert report["imminent_reinundation_m2"] == pytest.approx(130.0)
    assert report["missing"] == ""


def test_an_unfilled_template_wall_block_is_not_a_wall(nhi_act):
    assert nhi_act.walls == []
    assert nhi_act.report["n_walls"] == 0


def test_a_structural_report_is_labelled_as_one():
    header = ecr.read_header(
        blocks(
            "Job No: 1502000.9999",
            "Claim for Natural Hazard (Landslide) Structural Assessment",
            "A Person, 18 Example Grove, Suburb, Lower Hutt",
        )
    )
    assert header["claim_type"] == "Landslide"
    assert header["report_kind"] == "structural"
    assert header["address"] == "18 Example Grove, Suburb, Lower Hutt"


def test_walls_in_a_table_after_the_summary_are_read():
    result = ecr.extract(
        blocks(
            "Property Damage",
            "Damage to a 4.5 m length of RTW1.",
            "Damage to a 4.4 m length of RTW2.",
            "NHCover considerations",
            "Summary of damage information",
            ("Is this natural hazard damage?", "Yes (Landslide)"),
            ("Area of insured land damaged:", "", "", ""),
            ("Evacuated:", "13 m2", "", ""),
            ("Refer to retaining wall summary information below", "NA", "Yes", "NA"),
            "*To be assessed by the cost estimator",
            ("Dwelling", "Shared Land", "Flat 1 & 2", "Flat 3"),
            (
                "Retaining walls supporting or protecting insured land",
                "NA",
                "Yes",
                "NA",
            ),
            ("Retaining Wall 1 (RTW1) – Cement mortar boulder wall", "", "", ""),
            ("Whole wall length:", "", "8.2 m", ""),
            ("Retained height:", "", "0.8 m", ""),
            ("Damaged: (insured face area):", "", "3.6 m2", ""),
            ("Imminent damage: (insured face area):", "", "Nil", ""),
            ("Retaining Wall 2 – Metal pole timber lagged wall", "", "", ""),
            ("Whole wall length:", "", "4.4 m", ""),
            ("Damaged: (insured face area):", "", "4 m2", ""),
            ("Construction access", "☐", "☒", "☐"),
            ("TOTAL (Excluding GST)", "$ Nil *"),
        )
    )
    first, second = result.walls
    assert first["wall_number"] == 1
    assert first["construction"] == "Cement mortar boulder wall"
    assert first["whole_length_m"] == pytest.approx(8.2)
    assert first["retained_height_m"] == pytest.approx(0.8)
    assert first["damaged_face_m2"] == pytest.approx(3.6)
    assert first["damaged_length_m"] == pytest.approx(4.5)
    assert second["construction"] == "Metal pole timber lagged wall"
    assert second["damaged_length_m"] == pytest.approx(4.4)
    assert result.report["n_walls"] == 2
