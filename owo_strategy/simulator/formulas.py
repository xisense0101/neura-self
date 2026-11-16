"""
Basement Pet Stat, Resistance, and EHP Formulas.

Based on OwO battle mechanics documented at https://owo.bwep.net/pets
and https://owo.bwep.net/battleSystem/math.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, NamedTuple


class EffectiveResistance(NamedTuple):
    """Effective resistance representation returning rounded integer percent and float ratio."""
    percent: int
    ratio: float

    @property
    def float_value(self) -> float:
        return self.ratio

    def __float__(self) -> float:
        return self.ratio

    def __int__(self) -> int:
        return self.percent


class EHPResult(NamedTuple):
    """Effective Hit Points for physical and magical damage."""
    physical: float
    magical: float

    def __getitem__(self, item: Any) -> float:
        if item in ("physical", "ehp_physical"):
            return self.physical
        if item in ("magical", "ehp_magical"):
            return self.magical
        return tuple.__getitem__(self, item)


@dataclass
class PetStats:
    """Pet stats container supporting attribute access and mapping-like subscripting."""
    hp: int
    wp: int
    str: int
    mag: int
    ipr: int
    imr: int
    level: int = 1
    pr_percent: int = 0
    pr_ratio: float = 0.0
    mr_percent: int = 0
    mr_ratio: float = 0.0
    ehp_physical: float = 0.0
    ehp_magical: float = 0.0

    def __post_init__(self) -> None:
        pr_eff = calculate_effective_resistance(self.ipr)
        mr_eff = calculate_effective_resistance(self.imr)
        self.pr_percent = pr_eff.percent
        self.pr_ratio = pr_eff.ratio
        self.mr_percent = mr_eff.percent
        self.mr_ratio = mr_eff.ratio

        ehp = calculate_ehp(self.hp, self.pr_ratio, self.mr_ratio)
        self.ehp_physical = ehp.physical
        self.ehp_magical = ehp.magical

    def __getitem__(self, key: str) -> Any:
        normalized = key.lower().replace("_", "")
        key_map = {
            "hp": self.hp,
            "wp": self.wp,
            "str": self.str,
            "mag": self.mag,
            "ipr": self.ipr,
            "imr": self.imr,
            "pr": self.pr_ratio,
            "mr": self.mr_ratio,
            "prpercent": self.pr_percent,
            "mrpercent": self.mr_percent,
            "prratio": self.pr_ratio,
            "mrratio": self.mr_ratio,
            "ehpphysical": self.ehp_physical,
            "ehpmagical": self.ehp_magical,
            "level": self.level,
        }
        if normalized in key_map:
            return key_map[normalized]
        raise KeyError(key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hp": self.hp,
            "wp": self.wp,
            "str": self.str,
            "mag": self.mag,
            "ipr": self.ipr,
            "imr": self.imr,
            "level": self.level,
            "pr_percent": self.pr_percent,
            "pr_ratio": self.pr_ratio,
            "mr_percent": self.mr_percent,
            "mr_ratio": self.mr_ratio,
            "ehp_physical": self.ehp_physical,
            "ehp_magical": self.ehp_magical,
        }


def _extract_dex_value(dex_stats: Mapping[str, Any] | Any, *keys: str) -> int:
    """Helper to extract stat value from dict or object across various key namings."""
    for key in keys:
        if isinstance(dex_stats, Mapping):
            for k, v in dex_stats.items():
                if k.lower() == key.lower():
                    return int(v)
        elif hasattr(dex_stats, key):
            val = getattr(dex_stats, key)
            if val is not None:
                return int(val)
        elif hasattr(dex_stats, key.lower()):
            val = getattr(dex_stats, key.lower())
            if val is not None:
                return int(val)
    return 0


def calculate_pet_stats(
    level: int,
    dex_stats: Mapping[str, Any] | Any,
    weapon_stat_boosts: Mapping[str, Any] | None = None,
) -> PetStats:
    """
    Calculate exact pet stats based on Basement formulas:
        HP  = 500 + 2 * level * HP_dex
        WP  = 500 + 2 * level * WP_dex
        STR = 100 + 1 * level * STR_dex
        MAG = 100 + 1 * level * MAG_dex
        iPR = 25  + 2 * level * PR_dex
        iMR = 25  + 2 * level * MR_dex

    Optionally incorporates weapon stat boosts (e.g. STR/MAG/HP/WP/iPR/iMR passives).
    """
    hp_dex = _extract_dex_value(dex_stats, "hp", "hp_dex", "hpDex")
    wp_dex = _extract_dex_value(dex_stats, "wp", "wp_dex", "wpDex")
    str_dex = _extract_dex_value(dex_stats, "str", "str_dex", "strDex")
    mag_dex = _extract_dex_value(dex_stats, "mag", "mag_dex", "magDex")
    pr_dex = _extract_dex_value(dex_stats, "pr", "ipr", "pr_dex", "prDex")
    mr_dex = _extract_dex_value(dex_stats, "mr", "imr", "mr_dex", "mrDex")

    hp = 500 + 2 * level * hp_dex
    wp = 500 + 2 * level * wp_dex
    str_ = 100 + 1 * level * str_dex
    mag = 100 + 1 * level * mag_dex
    ipr = 25 + 2 * level * pr_dex
    imr = 25 + 2 * level * mr_dex

    if weapon_stat_boosts:
        hp += _extract_dex_value(weapon_stat_boosts, "hp", "hp_boost")
        wp += _extract_dex_value(weapon_stat_boosts, "wp", "wp_boost")
        str_ += _extract_dex_value(weapon_stat_boosts, "str", "str_boost")
        mag += _extract_dex_value(weapon_stat_boosts, "mag", "mag_boost")
        ipr += _extract_dex_value(weapon_stat_boosts, "ipr", "pr", "ipr_boost", "pr_boost")
        imr += _extract_dex_value(weapon_stat_boosts, "imr", "mr", "imr_boost", "mr_boost")

    return PetStats(
        hp=hp,
        wp=wp,
        str=str_,
        mag=mag,
        ipr=ipr,
        imr=imr,
        level=level,
    )


def calculate_effective_resistance(iRes: float | int) -> EffectiveResistance:
    """
    Calculate effective resistance from internal resistance:
        Res = (0.8 * iRes) / (100 + iRes)

    Returns EffectiveResistance(percent=int, ratio=float).
    Example: iPR=65 -> ratio=0.31515..., percent=32.
             iMR=105 -> ratio=0.40975..., percent=41.
    """
    denom = 100.0 + float(iRes)
    if denom <= 0:
        ratio = 0.0
    else:
        ratio = (0.8 * float(iRes)) / denom

    # Percentage rounded to nearest integer (as in OwO in-game display)
    percent = int(round(ratio * 100.0))
    return EffectiveResistance(percent=percent, ratio=ratio)


def calculate_ehp(hp: float | int, pr: float | int, mr: float | int) -> EHPResult:
    """
    Calculate Effective Hit Points (EHP):
        EHP_physical = hp / (1 - pr)
        EHP_magical  = hp / (1 - mr)

    pr and mr can be supplied either as ratios (0.0 to 1.0) or percentages (e.g. 50 or 60).
    """
    pr_ratio = float(pr) / 100.0 if float(pr) > 1.0 else float(pr)
    mr_ratio = float(mr) / 100.0 if float(mr) > 1.0 else float(mr)

    denom_pr = 1.0 - pr_ratio
    denom_mr = 1.0 - mr_ratio

    ehp_phys = float("inf") if denom_pr <= 0 else float(hp) / denom_pr
    ehp_mag = float("inf") if denom_mr <= 0 else float(hp) / denom_mr

    return EHPResult(physical=ehp_phys, magical=ehp_mag)
