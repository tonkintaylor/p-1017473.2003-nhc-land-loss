"""Goods and services tax, applied as a deliberate step rather than folded in.

The Act compares market value, undepreciated value and repair cost on a
GST-inclusive basis, while most of the rates the study builds on are stated
excluding it. A value is therefore grossed up in one named place, by
:func:`add_gst`, so every GST-inclusive figure can be traced back to the
exclusive one it came from.
"""

import numpy as np
import pandas as pd

# New Zealand GST, as a fraction. The loss module holds its own copy on its
# policy settings, since a policy scenario may vary it.
GST_RATE = 0.15


def add_gst[T: (float, np.ndarray, pd.Series)](
    amount_excl_gst: T, *, rate: float = GST_RATE
) -> T:
    """Return an amount stated excluding GST grossed up to include it.

    Args:
        amount_excl_gst: The amount, or amounts, excluding GST.
        rate: GST as a fraction.

    Returns:
        The amount including GST, in the same shape and type as given.

    Raises:
        ValueError: If the rate is negative.
    """
    if rate < 0:
        msg = f"the GST rate must not be negative, got {rate}"
        raise ValueError(msg)
    return amount_excl_gst * (1.0 + rate)
