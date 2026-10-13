"""Tests for running the modules' steps, from the start or part-way."""

from unittest.mock import Mock, call

import pytest

from scripts.landloss import gen_extents, pipeline


def modules(ran):
    """Run three small modules the way gen_all runs the real ones."""

    def step(name):
        return name, lambda: ran.append(name)

    pipeline.run_steps(
        "ground", [step("s3, instability zones"), step("s4, slope faces")]
    )
    pipeline.run_steps("exposure", [step("rw s6, wall probability")])
    pipeline.run_steps("vul", [step("s10, tables")])


def test_with_no_start_every_step_runs():
    ran = []
    with pipeline.starting_from(None):
        modules(ran)
    assert ran == [
        "s3, instability zones",
        "s4, slope faces",
        "rw s6, wall probability",
        "s10, tables",
    ]


def test_a_start_part_way_through_a_module_skips_what_comes_before_it():
    ran = []
    with pipeline.starting_from({"module": "ground", "step": "s4"}):
        modules(ran)
    assert ran == ["s4, slope faces", "rw s6, wall probability", "s10, tables"]


def test_a_start_in_a_later_module_skips_the_modules_before_it():
    ran = []
    with pipeline.starting_from({"module": "exposure", "step": "rw s6"}):
        modules(ran)
    assert ran == ["rw s6, wall probability", "s10, tables"]


def test_a_step_named_under_the_wrong_module_is_not_a_start():
    ran = []
    with (
        pytest.raises(ValueError, match="No step matches START_FROM"),
        pipeline.starting_from({"module": "vul", "step": "s4, slope faces"}),
    ):
        modules(ran)
    assert ran == []


def test_an_unmatched_start_lists_every_step():
    with (
        pytest.raises(ValueError, match="ground: s4, slope faces") as raised,
        pipeline.starting_from({"module": "ground", "step": "s99"}),
    ):
        modules([])
    assert "exposure: rw s6, wall probability" in str(raised.value)


def test_a_start_must_name_a_module_and_a_step():
    with (
        pytest.raises(ValueError, match="must name a module and a step"),
        pipeline.starting_from({"step": "s4, slope faces"}),
    ):
        pass


def test_the_start_does_not_outlive_its_run():
    with pipeline.starting_from({"module": "vul", "step": "s10"}):
        modules([])
    ran = []
    modules(ran)
    assert len(ran) == 4


@pytest.mark.parametrize(
    "start_from_by_extent",
    [{}, {"wellington-city": {"module": "ground", "step": "s2, ground map"}}],
)
def test_extent_batch_runs_model_then_loss_in_configured_order(
    monkeypatch, start_from_by_extent
):
    extents = ["wellington-city", "upper-hutt", "porirua"]
    runner = Mock()
    monkeypatch.setattr(gen_extents.gen_all, "main", runner.model)
    monkeypatch.setattr(gen_extents.gen_loss, "main", runner.loss)

    gen_extents.main(
        extents=extents,
        world_ids=[0, 1],
        realisation_ids=[2],
        start_from_by_extent=start_from_by_extent,
    )

    expected = []
    for extent in extents:
        ids = {"extent": extent, "world_ids": [0, 1], "realisation_ids": [2]}
        expected.extend(
            [
                call.model(**ids, start_from=start_from_by_extent.get(extent)),
                call.loss(**ids),
            ]
        )
    assert runner.mock_calls == expected


def test_extent_batch_validates_all_names_before_running(monkeypatch):
    model = Mock()
    monkeypatch.setattr(gen_extents.gen_all, "main", model)

    with pytest.raises(KeyError, match="not a known extent"):
        gen_extents.main(
            extents=["wellington-city", "unknown"],
            world_ids=[0],
            realisation_ids=[0],
            start_from_by_extent={},
        )
    model.assert_not_called()


def test_extent_batch_rejects_restart_for_an_extent_outside_the_batch(monkeypatch):
    model = Mock()
    monkeypatch.setattr(gen_extents.gen_all, "main", model)

    with pytest.raises(ValueError, match="Restart extents are not in EXTENTS"):
        gen_extents.main(
            extents=["wellington-city"],
            world_ids=[0],
            realisation_ids=[0],
            start_from_by_extent={"lower-hutt": {"module": "ground", "step": "s2"}},
        )
    model.assert_not_called()


@pytest.mark.parametrize("failed_stage", ["model", "loss"])
def test_extent_batch_stops_at_the_first_failure(monkeypatch, failed_stage):
    runner = Mock()
    getattr(runner, failed_stage).side_effect = RuntimeError("stage failed")
    monkeypatch.setattr(gen_extents.gen_all, "main", runner.model)
    monkeypatch.setattr(gen_extents.gen_loss, "main", runner.loss)

    with pytest.raises(RuntimeError, match="stage failed"):
        gen_extents.main(
            extents=["wellington-city"],
            world_ids=[0],
            realisation_ids=[0],
            start_from_by_extent={},
        )
    assert runner.model.call_count == 1
    assert runner.loss.call_count == (0 if failed_stage == "model" else 1)
