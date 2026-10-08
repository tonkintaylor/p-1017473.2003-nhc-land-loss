"""Run a module's steps in order, stopping at the first that fails.

Each module's ``gen_<module>.py`` hands :func:`run_steps` its steps as named
calls, already bound to their settings, so the order the pipeline runs in is
written down once per module rather than remembered.

A run can start part-way, after a failure or to rerun only what follows a
change: :func:`starting_from` names a module and a step, and every module and
step before it is skipped (``gen_all.py`` takes it from ``config.START_FROM``).
"""

import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

RULE = "=" * 78

# One step: the name it is reported under, and the call that runs it. A step
# that returns a truthy status has failed, which is how the older steps report a
# missing input rather than raising.
Step = tuple[str, Callable[[], int | None]]

# The step a run starts at, as (module, start of the step's name), while it has
# not been reached; None once it has, or when the run starts at the beginning.
_start: tuple[str, str] | None = None
# The steps passed on the way to the start, as "module: step", to name the valid
# starts if it is never reached.
_passed: list[str] = []


@contextmanager
def starting_from(start: dict[str, str] | None) -> Iterator[None]:
    """Skip every module and step before ``start`` in the runs inside this block.

    Args:
        start: ``{"module": ..., "step": ...}``: the module as its runner
            names it (``hazard``, ``exposure``, ``hazard urban``, ``vul``) and
            the start of the step's name as the run prints it, for example
            ``{"module": "hazard", "step": "landslide s13"}``. None runs
            everything.

    Raises:
        ValueError: If ``start`` is not a module and a step, or if the block
            ends without reaching it; the message lists every step passed.
    """
    global _start  # noqa: PLW0603 -- the run's one start, read by run_steps
    if start is not None and set(start) != {"module", "step"}:
        msg = f"START_FROM must name a module and a step, not {start!r}"
        raise ValueError(msg)
    _start = None if start is None else (start["module"], start["step"])
    _passed.clear()
    try:
        yield
        if _start is not None:
            names = "\n  ".join(_passed)
            msg = f"No step matches START_FROM {start!r}. The steps are:\n  {names}"
            raise ValueError(msg)
    finally:
        _start = None


def _from_start(module: str, steps: Sequence[Step]) -> Sequence[Step]:
    """The steps of a module still to run, given where the run starts."""
    global _start  # noqa: PLW0603 -- cleared once the start is reached
    if _start is None:
        return steps
    start_module, start_step = _start
    names = [name for name, _ in steps]
    first = next(
        (
            i
            for i, name in enumerate(names)
            if module == start_module and name.startswith(start_step)
        ),
        None,
    )
    _passed.extend(f"{module}: {name}" for name in names)
    if first is None:
        print(f"\n{RULE}\n{module}: skipped, the run starts later\n{RULE}")
        return []
    _start = None
    if first:
        print(f"\n{RULE}\n{module}: starting at {names[first]}; skipped:")
        for name in names[:first]:
            print(f"  {name}")
    return steps[first:]


def run_steps(module: str, steps: Sequence[Step]) -> None:
    """Run each step in turn, reporting what ran and how long it took.

    Steps before the run's start (:func:`starting_from`) are skipped.

    Args:
        module: The module the steps belong to, for the report.
        steps: The steps, in the order they have to run.

    Raises:
        RuntimeError: If a step returns a failing status. The steps after it
            are not run, because each one reads what the one before it wrote.
    """
    total = len(steps)
    steps = _from_start(module, steps)
    if not steps:
        return
    started = time.perf_counter()
    for number, (name, run) in enumerate(steps, start=total - len(steps) + 1):
        print(f"\n{RULE}\n{module} {number}/{total}: {name}\n{RULE}", flush=True)
        step_started = time.perf_counter()
        status = run()
        if status:
            msg = f"{module} stopped at {name}, which returned status {status}"
            raise RuntimeError(msg)
        print(f"\n{name} finished in {time.perf_counter() - step_started:,.0f} s")
    print(
        f"\n{RULE}\n{module}: {len(steps)} of {total} steps finished in "
        f"{time.perf_counter() - started:,.0f} s\n{RULE}"
    )
