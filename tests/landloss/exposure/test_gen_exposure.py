"""Tests for the exposure runner, ``gen_exposure.py``.

The runner hands each step's ``main`` its keywords inside a lambda, so a step
whose signature gains a keyword the runner does not pass fails only when the
runner reaches it. These tests stand every step's ``main`` in with a recorder
that binds the runner's keywords to the real signature, so the runner is
exercised without reading or writing anything.
"""

import inspect
from types import ModuleType

import pytest

from scripts.landloss.exposure import gen_exposure


def _step_modules() -> dict[str, ModuleType]:
    """Return every module the runner imports that carries a ``main``."""
    return {
        name: value
        for name, value in vars(gen_exposure).items()
        if isinstance(value, ModuleType) and callable(getattr(value, "main", None))
    }


@pytest.fixture
def called(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace each step's ``main`` with a recorder that checks its keywords.

    Returns:
        The step module names, in the order the runner called them.
    """
    order: list[str] = []
    for name, module in _step_modules().items():
        signature = inspect.signature(module.main)

        def record(
            *args: object,
            _name: str = name,
            _signature: inspect.Signature = signature,
            **kwargs: object,
        ) -> None:
            _signature.bind(*args, **kwargs)
            order.append(_name)

        monkeypatch.setattr(module, "main", record)
    return order


def test_every_step_binds_to_its_main(called: list[str]) -> None:
    """Every lambda's keywords bind to its step's ``main`` signature."""
    gen_exposure.main(extent="wlg-pilot", realisation_ids=[0], world_ids=[0])

    assert sorted(called) == sorted(_step_modules())


def test_accessibility_runs_between_terrain_and_land_value(
    called: list[str],
) -> None:
    """The land value reads the terrain and accessibility files written first."""
    gen_exposure.main(extent="wlg-pilot", realisation_ids=[0], world_ids=[0])

    terrain = called.index("s1_build_terrain_attributes")
    accessibility = called.index("s2_build_accessibility")
    land_value = called.index("s4_estimate_land_value")
    assert terrain < accessibility < land_value


def test_wall_steps_run_in_contract_order(called: list[str]) -> None:
    """The wall lines, probability and population run after the insured land."""
    gen_exposure.main(extent="wlg-pilot", realisation_ids=[0], world_ids=[0])

    positions = [
        called.index(name)
        for name in (
            "gen_insured_land",
            "gen_wall_lines",
            "gen_wall_probability",
            "gen_wall_population",
        )
    ]
    assert positions == sorted(positions)
