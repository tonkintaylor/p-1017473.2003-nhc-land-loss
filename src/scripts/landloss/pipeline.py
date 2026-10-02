"""Run a module's steps in order, stopping at the first that fails.

Each module's ``gen_<module>.py`` hands :func:`run_steps` its steps as named
calls, already bound to their settings, so the order the pipeline runs in is
written down once per module rather than remembered.
"""

import time
from collections.abc import Callable, Sequence

RULE = "=" * 78

# One step: the name it is reported under, and the call that runs it. A step
# that returns a truthy status has failed, which is how the older steps report a
# missing input rather than raising.
Step = tuple[str, Callable[[], int | None]]


def run_steps(module: str, steps: Sequence[Step]) -> None:
    """Run each step in turn, reporting what ran and how long it took.

    Args:
        module: The module the steps belong to, for the report.
        steps: The steps, in the order they have to run.

    Raises:
        RuntimeError: If a step returns a failing status. The steps after it
            are not run, because each one reads what the one before it wrote.
    """
    started = time.perf_counter()
    for number, (name, run) in enumerate(steps, start=1):
        print(f"\n{RULE}\n{module} {number}/{len(steps)}: {name}\n{RULE}", flush=True)
        step_started = time.perf_counter()
        status = run()
        if status:
            msg = f"{module} stopped at {name}, which returned status {status}"
            raise RuntimeError(msg)
        print(f"\n{name} finished in {time.perf_counter() - step_started:,.0f} s")
    print(
        f"\n{RULE}\n{module}: all {len(steps)} steps finished in "
        f"{time.perf_counter() - started:,.0f} s\n{RULE}"
    )
