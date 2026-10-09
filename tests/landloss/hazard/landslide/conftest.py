"""Fixtures shared by the landslide tests."""

import pytest

from landloss.hazard.landslide import slope_elements

# The eight-band table the free-face and bank pipeline was built and tested on
# (before landslide-slope-thresholds.csv became the two siz bands): soil 35
# throughout; weak rock 45 to 10 m then 34; stronger rock 53 to 6 m, 45 to 10 m
# then 34. Heights are those of the plan, phase 1.
LEGACY_HEIGHT_BANDS_M = (0.5, 1.0, 1.5, 2.5, 3.5, 6.0, 10.0, 16.0)
LEGACY_STEP_ANGLE_DEG = {
    "soil_like": (35.0,) * 8,
    "weak_rock": (45.0,) * 6 + (34.0,) * 2,
    "stronger_rock": (53.0,) * 5 + (45.0, 34.0, 34.0),
}


@pytest.fixture
def legacy_step_table(monkeypatch):
    """Run the old free-face and bank pipeline on the table it was tested with."""
    monkeypatch.setattr(slope_elements, "HEIGHT_BANDS_M", LEGACY_HEIGHT_BANDS_M)
    monkeypatch.setattr(slope_elements, "N_HEIGHT_BANDS", len(LEGACY_HEIGHT_BANDS_M))
    monkeypatch.setattr(slope_elements, "STEP_ANGLE_DEG", LEGACY_STEP_ANGLE_DEG)
