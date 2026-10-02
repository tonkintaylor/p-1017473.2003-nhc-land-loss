"""Run every loss step end to end, over the four tables vul hands across.

    uv run --frozen python src/scripts/landloss/loss/gen_loss.py

Reads what the vulnerability module wrote, so `gen_vul.py` runs first, and with
it the exposure and hazard modules it depends on. Two steps: step 0 builds the
land cover cap on each claim, and step 1 builds the repair cost and settles
against it, writing ``land-cover-cap-r<nnn>[-pilot].parquet`` and
``settlement-r<nnn>[-pilot].parquet`` under ``temp/loss``.

The extent and realisations come from ``config.py`` beside this; anything else a
step reads comes from that step's own ``config.py``.

**Every repair cost in step 1 rests on a stated assumption**, and the three site
ratings are proxied off exposure layers rather than measured. Step 1's docstring
lists each one. The module settles, but what it settles is a model whose
placeholders are named rather than hidden.
"""

from scripts.landloss.loss import config
from scripts.landloss.loss.steps.s0_land_cover_cap import s0_gen_land_cover_cap
from scripts.landloss.loss.steps.s1_settlement import s1_gen_settlement
from scripts.landloss.pipeline import run_steps


def main(*, pilot, realisation_ids):
    """Run the loss steps in order.

    Args:
        pilot: Whether to run over the small Wellington pilot box.
        realisation_ids: Which modelled earthquakes to run.
    """
    ids = {"pilot": pilot, "realisation_ids": realisation_ids}
    run_steps(
        "loss",
        [
            (
                "s0, the land cover cap per claim",
                lambda: s0_gen_land_cover_cap.main(**ids),
            ),
            (
                "s1, the settlement per claim",
                lambda: s1_gen_settlement.main(**ids),
            ),
        ],
    )


if __name__ == "__main__":
    main(pilot=config.PILOT, realisation_ids=config.REALISATION_IDS)
