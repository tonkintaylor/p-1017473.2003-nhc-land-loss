"""Tests for the landloss versioned-data save/read helpers.

These monkeypatch tdrive_sync.local_save/local_read directly rather than
building a real tdrive_sync_config.py -- the only thing versioned_store adds
is prefixing sub_dirs with the module name, which tdrive_sync itself already
has thorough tests for.
"""

from typing import Any

import pytest

import tdrive_sync as ts
from landloss.io import versioned_store as vs


@pytest.fixture
def fake_local_save(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Record the call made to tdrive_sync.local_save."""
    calls: dict[str, Any] = {}

    def fake(obj: Any, **kwargs: Any) -> None:
        calls["obj"] = obj
        calls["kwargs"] = kwargs

    monkeypatch.setattr(ts, "local_save", fake)
    return calls


@pytest.fixture
def fake_local_read(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Record the call made to tdrive_sync.local_read, returning a sentinel."""
    calls: dict[str, Any] = {}
    sentinel = object()

    def fake(**kwargs: Any) -> object:
        calls["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(ts, "local_read", fake)
    calls["sentinel"] = sentinel
    return calls


@pytest.mark.parametrize(
    ("save_fn", "module"),
    [
        (vs.save_hazard, "hazard"),
        (vs.save_exposure, "exposure"),
        (vs.save_vul, "vul"),
        (vs.save_loss, "loss"),
    ],
)
def test_save_prefixes_sub_dirs_with_the_module_name(
    save_fn: Any, module: str, fake_local_save: dict[str, Any]
) -> None:
    """Each save_* helper saves under its own module subdirectory."""
    obj = {"a": 1}

    save_fn(obj, fname="data.json", sub_dirs=["extra"])

    assert fake_local_save["obj"] is obj
    assert fake_local_save["kwargs"]["fname"] == "data.json"
    assert fake_local_save["kwargs"]["sub_dirs"] == [module, "extra"]


@pytest.mark.parametrize(
    ("save_fn", "module"),
    [
        (vs.save_hazard, "hazard"),
        (vs.save_exposure, "exposure"),
        (vs.save_vul, "vul"),
        (vs.save_loss, "loss"),
    ],
)
def test_save_defaults_sub_dirs_to_just_the_module_name(
    save_fn: Any, module: str, fake_local_save: dict[str, Any]
) -> None:
    """Without sub_dirs, only the module name is used to prefix the path."""
    save_fn({"a": 1}, fname="data.json")

    assert fake_local_save["kwargs"]["sub_dirs"] == [module]


@pytest.mark.parametrize(
    ("save_fn"),
    [vs.save_hazard, vs.save_exposure, vs.save_vul, vs.save_loss],
)
def test_save_passes_extra_kwargs_through(
    save_fn: Any, fake_local_save: dict[str, Any]
) -> None:
    """Format-specific kwargs (e.g. index=False for csv) reach local_save."""
    save_fn({"a": 1}, fname="data.csv", index=False)

    assert fake_local_save["kwargs"]["index"] is False


@pytest.mark.parametrize(
    ("read_fn", "module"),
    [
        (vs.read_hazard, "hazard"),
        (vs.read_exposure, "exposure"),
        (vs.read_vul, "vul"),
        (vs.read_loss, "loss"),
    ],
)
def test_read_prefixes_sub_dirs_with_the_module_name(
    read_fn: Any, module: str, fake_local_read: dict[str, Any]
) -> None:
    """Each read_* helper reads from its own module subdirectory."""
    result = read_fn(fname="data.json", sub_dirs=["extra"])

    assert result is fake_local_read["sentinel"]
    assert fake_local_read["kwargs"]["fname"] == "data.json"
    assert fake_local_read["kwargs"]["sub_dirs"] == [module, "extra"]


@pytest.mark.parametrize(
    ("read_fn", "module"),
    [
        (vs.read_hazard, "hazard"),
        (vs.read_exposure, "exposure"),
        (vs.read_vul, "vul"),
        (vs.read_loss, "loss"),
    ],
)
def test_read_defaults_sub_dirs_to_just_the_module_name(
    read_fn: Any, module: str, fake_local_read: dict[str, Any]
) -> None:
    """Without sub_dirs, only the module name is used to prefix the path."""
    read_fn(fname="data.json")

    assert fake_local_read["kwargs"]["sub_dirs"] == [module]


@pytest.mark.parametrize(
    ("read_fn"),
    [vs.read_hazard, vs.read_exposure, vs.read_vul, vs.read_loss],
)
def test_read_passes_copy_to_local_and_return_path_through(
    read_fn: Any, fake_local_read: dict[str, Any]
) -> None:
    """The read-specific keyword arguments reach local_read unchanged."""
    read_fn(fname="data.json", copy_to_local=False, return_path=True)

    assert fake_local_read["kwargs"]["copy_to_local"] is False
    assert fake_local_read["kwargs"]["return_path"] is True
