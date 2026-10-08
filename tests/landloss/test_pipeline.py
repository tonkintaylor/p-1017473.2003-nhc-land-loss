"""Tests for running the modules' steps, from the start or part-way."""

import pytest

from scripts.landloss import pipeline


def modules(ran):
    """Run three small modules the way gen_all runs the real ones."""

    def step(name):
        return name, lambda: ran.append(name)

    pipeline.run_steps("hazard", [step("landslide s3"), step("landslide s13")])
    pipeline.run_steps("exposure", [step("rw s6, wall probability")])
    pipeline.run_steps("vul", [step("s10, tables")])


def test_with_no_start_every_step_runs():
    ran = []
    with pipeline.starting_from(None):
        modules(ran)
    assert ran == [
        "landslide s3",
        "landslide s13",
        "rw s6, wall probability",
        "s10, tables",
    ]


def test_a_start_part_way_through_a_module_skips_what_comes_before_it():
    ran = []
    with pipeline.starting_from({"module": "hazard", "step": "landslide s13"}):
        modules(ran)
    assert ran == ["landslide s13", "rw s6, wall probability", "s10, tables"]


def test_a_start_in_a_later_module_skips_the_modules_before_it():
    ran = []
    with pipeline.starting_from({"module": "exposure", "step": "rw s6"}):
        modules(ran)
    assert ran == ["rw s6, wall probability", "s10, tables"]


def test_a_step_named_under_the_wrong_module_is_not_a_start():
    ran = []
    with (
        pytest.raises(ValueError, match="No step matches START_FROM"),
        pipeline.starting_from({"module": "vul", "step": "landslide s13"}),
    ):
        modules(ran)
    assert ran == []


def test_an_unmatched_start_lists_every_step():
    with (
        pytest.raises(ValueError, match="hazard: landslide s13") as raised,
        pipeline.starting_from({"module": "hazard", "step": "landslide s99"}),
    ):
        modules([])
    assert "exposure: rw s6, wall probability" in str(raised.value)


def test_a_start_must_name_a_module_and_a_step():
    with (
        pytest.raises(ValueError, match="must name a module and a step"),
        pipeline.starting_from({"step": "landslide s13"}),
    ):
        pass


def test_the_start_does_not_outlive_its_run():
    with pipeline.starting_from({"module": "vul", "step": "s10"}):
        modules([])
    ran = []
    modules(ran)
    assert len(ran) == 4
