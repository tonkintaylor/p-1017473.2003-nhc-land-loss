import numpy as np
import pytest

from landloss.hazard.landslide.calibration import marc_2016 as m


def test_fault_length_spans_the_papers_range():
    # The paper: Leonard's scaling "holds for fault lengths of about 3.5 km to
    # 225 km for thrust earthquakes of Mw 5 to 8". Only the reading of eq. 7
    # with the 2/5 power on the whole ratio gives lengths of that order.
    short = m.fault_length_km(m.moment_from_mw(5.0), "R")
    long = m.fault_length_km(m.moment_from_mw(8.0), "R")
    assert 2.5 < short < 4.0
    assert 150 < long < 250


def test_strike_slip_length_joins_the_dip_slip_length_at_saturation():
    critical_m = (m.SEISMOGENIC_THICKNESS_M / m.C1_M) ** 1.5
    moment = m.SHEAR_MODULUS_PA * m.C1_M**1.5 * m.C2 * critical_m**2.5
    below = m.fault_length_km(moment * 0.999, "SS")
    above = m.fault_length_km(moment * 1.001, "SS")
    assert below == pytest.approx(above, rel=0.01)
    assert critical_m / 1000 == pytest.approx(33.0, abs=1.0)


def test_source_acceleration_saturates_at_the_hinge():
    assert m.source_acceleration_km(m.M_HINGE, "R") == pytest.approx(4.0)
    assert m.source_acceleration_km(m.M_HINGE, "N") == pytest.approx(2.8)
    # Above the hinge it grows only slowly (e7 = 0.054).
    assert m.source_acceleration_km(8.1, "R") == pytest.approx(
        4.0 * np.exp(0.054 * 1.35)
    )


def test_point_source_closed_form_matches_the_integral_of_eq_4():
    b_s, r0, a_c = 4.2, 6.0, 0.15
    rh_max = np.sqrt((b_s / a_c) ** 2 - r0**2)
    rh = np.linspace(0.0, rh_max, 200_001)
    density = b_s / np.sqrt(r0**2 + rh**2) - a_c
    numeric = 2 * np.pi * np.trapezoid(density * rh, rh)
    assert m.point_source_integral_km2(b_s, r0, a_c) == pytest.approx(numeric, rel=1e-4)


def test_no_landsliding_when_the_shaking_never_exceeds_the_threshold():
    # b S = 4 km at R0 = 30 km gives at most 0.13 g, below a_c = 0.15.
    assert m.point_source_integral_km2(4.0, 30.0, 0.15) == 0.0


def test_chi_chi_is_reproduced():
    # 1999 Chi-Chi from Table S1: Mw 7.58, R0 6 km, reverse, modal slope 31,
    # A_topo 0.9. Estimated volume 0.45 km3 and area 128 km2.
    source = [m.Source(mw=7.5847, r0_km=6.0, fault_type="R")]
    volume = m.total_landsliding(
        source, modal_slope_deg=31, a_topo=0.9, quantity="volume"
    )
    area = m.total_landsliding(source, modal_slope_deg=31, a_topo=0.9, quantity="area")
    assert volume == pytest.approx(0.43, rel=0.05)
    assert 64 < area < 256  # within a factor of 2 of 128 km2


def test_percentiles_bracket_the_central_prediction():
    source = [m.Source(mw=7.5847, r0_km=6.0, fault_type="R")]
    p25, p50, p75 = m.total_landsliding_percentiles(
        source,
        mw_sd=[0.1],
        r0_sd_km=[1.5],
        modal_slope_deg=31,
        a_topo=0.9,
        quantity="volume",
        samples=20_000,
    )
    central = m.total_landsliding(
        source, modal_slope_deg=31, a_topo=0.9, quantity="volume"
    )
    assert p25 < central < p75
    assert p25 < p50 < p75


def test_table_s1_has_forty_earthquakes():
    table = m.get_table_s1()
    assert table.groupby(["year", "name"]).ngroups == 40
    assert (table["country"] == "NZ").groupby(
        [table["year"], table["name"]]
    ).any().sum() == 9


def test_unknown_quantity_is_refused():
    with pytest.raises(ValueError, match="area"):
        m.total_landsliding([], modal_slope_deg=20, a_topo=1, quantity="number")


def test_only_onshore_asperities_count():
    onshore = [m.Source(mw=8.1, r0_km=20.0, fault_type="R")]
    half = [m.Source(mw=8.1, r0_km=20.0, fault_type="R", onshore_fraction=0.5)]
    assert m.seismic_term_km2(half) == pytest.approx(0.5 * m.seismic_term_km2(onshore))


def test_an_interface_deeper_than_b_s_over_a_c_triggers_nothing():
    # At Mw 8.1, b S = 4.3 km, so no landsliding once R0 exceeds 4.3 / 0.15.
    b_s = float(m.source_acceleration_km(8.1, "R"))
    deep = [m.Source(mw=8.1, r0_km=b_s / m.A_C + 0.1, fault_type="R")]
    assert m.seismic_term_km2(deep) == 0.0
