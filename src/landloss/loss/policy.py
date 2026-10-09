"""The policy settings the study puts under test, gathered into one object.

`loss` is the only module where policy wording enters the model, and comparing
one set of settings against another is the whole point of the study. Holding
them in a frozen dataclass rather than as bare module constants is what makes a
scenario a value instead of an edit: two scenarios can be built and run in the
same process without one leaking into the other, and a run records which
settings produced it.

The defaults are the Natural Hazards Insurance Act as it currently stands, taken
from ``.agents/context/nhi-act-land-cover-explainer.md``. The setting NHC is
considering introducing -- :attr:`PolicySettings.total_cap_nzd`, which has no
equivalent in the present Act -- sits alongside them, so switching it on is the
same kind of act as changing a sub-cap rather than a different kind of change.

**Dollar amounts in this module are exclusive of GST**, because that is how the
Act states the sub-caps. The settlement arithmetic in
:mod:`landloss.loss.settlement` works GST-inclusive, since that is the basis the
Act compares repair cost against undepreciated value on, so the sub-caps are
grossed up at the point of use by :meth:`PolicySettings.retaining_wall_limit_nzd`
and :meth:`PolicySettings.bridge_culvert_limit_nzd` rather than by the caller.
"""

from dataclasses import dataclass

import numpy as np

# The explainer's worked examples gross a one-dwelling retaining wall limit of
# $50,000 to $57,500, which is what fixes the rate at 15% rather than leaving it
# to be assumed.
GST_RATE = 0.15

# How much dearer a replacement wall is than the one it replaces, over and above
# the site multiplier. A failed wall is rebuilt to a more substantial current
# standard rather than like for like, and the square-metre rates carry no
# allowance for that -- so without this, repair cost and undepreciated value
# differ only by site difficulty, which was the misreading behind **L-34**.
# Agreed with Maxim Millen on 2026-09-24 as a flat 20%, pending anything better.
REPLACEMENT_SPEC_UPLIFT = 0.20

# Both sub-caps are per dwelling in the residential building -- not per wall, not
# per owner, and not per property. A site carrying two residential buildings has
# two caps, worked out separately.
RETAINING_WALL_SUB_CAP_NZD = 50_000.0
BRIDGE_CULVERT_SUB_CAP_NZD = 25_000.0

# The land excess is **$500 per dwelling, capped at $5,000**, so it stops
# growing at ten dwellings. That is the explainer's rule, and all three of its
# worked examples settle on it.
#
# Virginie Lacrosse described a different one on 2026-09-25: 10% of what would
# otherwise be paid, once per claim, floored at $500 and capped at $5,000. The
# module ran that from 2026-09-25 to 2026-09-30 and has gone back to the
# explainer's. The two disagree by $4,500 on the explainer's own first example
# and nobody has yet said which NHC applies, so the other is kept runnable:
# setting `excess_per_dwelling_nzd` to ``None`` charges the rate instead. See
# **Q-14**.
LAND_EXCESS_PER_DWELLING_NZD = 500.0
LAND_EXCESS_RATE = 0.10
LAND_EXCESS_MIN_NZD = 500.0
LAND_EXCESS_MAX_NZD = 5_000.0

# Damaged land is valued over the lesser of the district plan minimum area and
# 4,000 m2. No district plan minimum has been obtained for the four territorial
# authorities, so the Act's own fallback stands in for all of them and is the
# first number to replace when they arrive.
AREA_CAP_M2 = 4_000.0


@dataclass(frozen=True)
class PolicySettings:
    """One scenario's policy settings.

    Attributes:
        gst_rate: GST as a fraction, used to gross the sub-caps up.
        retaining_wall_sub_cap_nzd: Retaining wall sub-cap per dwelling,
            excluding GST.
        bridge_culvert_sub_cap_nzd: Bridge and culvert sub-cap per dwelling,
            excluding GST.
        excess_per_dwelling_nzd: The land excess charged per dwelling, the
            explainer's rule. ``None`` charges :attr:`excess_rate` of what is
            payable instead, which is what Virginie Lacrosse described. The two
            contradict each other; see **Q-14**.
        excess_rate: The land excess as a fraction of what would otherwise
            be paid. Used only when :attr:`excess_per_dwelling_nzd` is
            ``None``.
        excess_min_nzd: The least the rate-based excess can be on a claim that
            is paid anything. Used only when :attr:`excess_per_dwelling_nzd` is
            ``None``.
        excess_max_nzd: The most the land excess can reach however many
            dwellings there are.
        area_cap_m2: The largest area of damaged land that is valued. Damage
            beyond it is valued as though it stopped here.
        replacement_spec_uplift: How much dearer the replacement wall is than
            the one it replaces, as a fraction, over and above the site
            multiplier. Zero prices a like-for-like rebuild.
        total_cap_nzd: A single cap over the whole land settlement. ``None`` is
            the present Act, which has no such cap; a figure is the setting
            under test.
        include_imminent_damage: Whether imminently damaged land and structures
            are settled. ``True`` is the present Act. Setting it ``False`` is
            how the study prices removing the provision.
    """

    gst_rate: float = GST_RATE
    retaining_wall_sub_cap_nzd: float = RETAINING_WALL_SUB_CAP_NZD
    bridge_culvert_sub_cap_nzd: float = BRIDGE_CULVERT_SUB_CAP_NZD
    excess_per_dwelling_nzd: float | None = LAND_EXCESS_PER_DWELLING_NZD
    excess_rate: float = LAND_EXCESS_RATE
    excess_min_nzd: float = LAND_EXCESS_MIN_NZD
    excess_max_nzd: float = LAND_EXCESS_MAX_NZD
    area_cap_m2: float = AREA_CAP_M2
    replacement_spec_uplift: float = REPLACEMENT_SPEC_UPLIFT
    total_cap_nzd: float | None = None
    include_imminent_damage: bool = True

    def __post_init__(self) -> None:
        """Refuse settings that cannot describe a real policy."""
        negatives = {
            "gst_rate": self.gst_rate,
            "retaining_wall_sub_cap_nzd": self.retaining_wall_sub_cap_nzd,
            "bridge_culvert_sub_cap_nzd": self.bridge_culvert_sub_cap_nzd,
            "excess_rate": self.excess_rate,
            "excess_min_nzd": self.excess_min_nzd,
            "excess_max_nzd": self.excess_max_nzd,
            "replacement_spec_uplift": self.replacement_spec_uplift,
        }
        for name, value in negatives.items():
            if not np.isfinite(value) or value < 0:
                msg = f"{name} must be finite and not negative"
                raise ValueError(msg)
        if not np.isfinite(self.area_cap_m2) or self.area_cap_m2 <= 0:
            msg = "area_cap_m2 must be finite and positive"
            raise ValueError(msg)
        if self.total_cap_nzd is not None and (
            not np.isfinite(self.total_cap_nzd) or self.total_cap_nzd < 0
        ):
            msg = "total_cap_nzd must be finite and not negative, or None"
            raise ValueError(msg)
        if self.excess_per_dwelling_nzd is not None and (
            not np.isfinite(self.excess_per_dwelling_nzd)
            or self.excess_per_dwelling_nzd < 0
        ):
            msg = "excess_per_dwelling_nzd must be finite and not negative, or None"
            raise ValueError(msg)

    def retaining_wall_limit_nzd(
        self, n_dwellings: np.ndarray | float
    ) -> np.ndarray | float:
        """Return the retaining wall sub-cap limit, grossed up for GST.

        Args:
            n_dwellings: Dwellings in the residential building.

        Returns:
            The applicable limit in GST-inclusive dollars.
        """
        gross = self.retaining_wall_sub_cap_nzd * (1.0 + self.gst_rate)
        return np.asarray(n_dwellings, dtype=float) * gross

    def bridge_culvert_limit_nzd(
        self, n_dwellings: np.ndarray | float
    ) -> np.ndarray | float:
        """Return the bridge and culvert sub-cap limit, grossed up for GST.

        Args:
            n_dwellings: Dwellings in the residential building.

        Returns:
            The applicable limit in GST-inclusive dollars.
        """
        gross = self.bridge_culvert_sub_cap_nzd * (1.0 + self.gst_rate)
        return np.asarray(n_dwellings, dtype=float) * gross

    def excess_nzd(
        self,
        payable_nzd: np.ndarray | float,
        n_dwellings: np.ndarray | float = 1.0,
    ) -> np.ndarray | float:
        """Return the land excess on a claim.

        :attr:`excess_per_dwelling_nzd` for every dwelling in the residential
        building, capped at :attr:`excess_max_nzd` -- so it scales with dwellings
        the way the sub-caps do, and stops growing at ten.

        A claim with nothing payable is charged nothing, so an undamaged claim
        does not acquire a $500 debt. The settlement is floored at zero either
        way; this keeps the excess reported against a claim to one that was
        actually taken.

        Setting :attr:`excess_per_dwelling_nzd` to ``None`` runs the rule
        Virginie Lacrosse described instead: :attr:`excess_rate` of what would
        otherwise be paid, once per claim, held between :attr:`excess_min_nzd`
        and :attr:`excess_max_nzd`. It is taken on the amount payable --
        ``min(repair cost, cap)`` -- rather than on the repair cost, so a claim
        is never charged an excess on cost NHC is not bearing. It is kept so the
        contradiction (**Q-14**) can be run both ways rather than argued about.

        Args:
            payable_nzd: What would be paid before the excess.
            n_dwellings: Dwellings in the residential building.

        Returns:
            The excess.
        """
        payable = np.asarray(payable_nzd, dtype=float)
        if self.excess_per_dwelling_nzd is not None:
            dwellings = np.asarray(n_dwellings, dtype=float)
            excess = np.minimum(
                dwellings * self.excess_per_dwelling_nzd, self.excess_max_nzd
            )
        else:
            excess = np.clip(
                payable * self.excess_rate, self.excess_min_nzd, self.excess_max_nzd
            )
        return np.where(payable > 0, excess, 0.0)
