import numpy as np
import pandas as pd
import pytest

from landloss.domain.gst import GST_RATE, add_gst


def test_gst_is_fifteen_percent():
    assert pytest.approx(0.15) == GST_RATE


def test_a_scalar_is_grossed_up():
    assert add_gst(100.0) == pytest.approx(115.0)


def test_an_array_keeps_its_shape():
    out = add_gst(np.array([0.0, 200.0, np.nan]))
    assert out[:2].tolist() == pytest.approx([0.0, 230.0])
    assert np.isnan(out[2])


def test_a_series_keeps_its_index():
    rates = pd.Series([500.0, 700.0], index=["a", "b"])
    out = add_gst(rates)
    assert out.index.tolist() == ["a", "b"]
    assert out.tolist() == pytest.approx([575.0, 805.0])


def test_a_different_rate_can_be_passed():
    assert add_gst(100.0, rate=0.0) == pytest.approx(100.0)


def test_a_negative_rate_is_refused():
    with pytest.raises(ValueError, match="must not be negative"):
        add_gst(100.0, rate=-0.1)
