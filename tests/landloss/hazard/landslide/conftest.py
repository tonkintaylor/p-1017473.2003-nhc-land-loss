"""Fixtures shared by the landslide tests."""

import pytest

from landloss.hazard.landslide import slope_elements
from landloss.hazard.landslide.wall_lines import WallLineSettings

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


@pytest.fixture
def settings() -> WallLineSettings:
    """The settings of ground step 3's config, written out for the test."""
    return WallLineSettings(
        outline_step_m=0.5,
        normal_half_window_m=1.5,
        fall_radius_m=3.0,
        normal_angles_deg=(45.0, 60.0, 75.0, 90.0),
        min_run_m=4.0,
        join_gaps_m=(6.0, 3.0, 1.5, 9.0, 12.0),
        max_length_m=49.0,
        fit_step_m=1.0,
        max_bends=3,
        min_segment_m=3.0,
        max_bend_deg=100.0,
        max_total_turn_deg=185.0,
        bend_penalty_m2=2.5,
        bend_length_scale_m=25.0,
        fit_loss_scale_m=0.5,
        refine_reach_m=1.5,
        refine_max_nfev=20,
        hook_m=4.0,
        hook_sharp_m=5.0,
        hook_sharp_deg=60.0,
        beyond_m=0.75,
        beyond_ok=0.1,
        rms_ok_m=1.0,
        rms_weight=0.25,
        chord_ok_m=1.5,
        chord_weight=0.15,
        bend_score=0.03,
        jog_m=8.0,
        jog_score=0.15,
        cone_half_angle_deg=45.0,
        cone_reach_m=200.0,
        cone_arc_n=9,
        leftover_join_m=2.1,
        min_no_wall_pips=5,
        enclosed_share=0.5,
        edge_buffer_m=0.5,
        wall_join_m=1.5,
        stay_m=3.0,
    )
