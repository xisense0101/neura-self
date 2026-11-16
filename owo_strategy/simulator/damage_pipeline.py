"""
6-Stage Damage Pipeline.

Based on OwO battle mechanics documented at https://owo.bwep.net/battleSystem/math.

Pipeline Stages:
  Stage 1: BaseDamage = RelevantStat * WeaponModifier
  Stage 2: RandomVariance = BaseDamage + random.randint(-50, 50) (or 0 for deterministic testing)
  Stage 3: PositiveModifiers = BaseDamage + sum(BaseDamage * mod) (AtkUp, Crit, Enrage, Sprout)
  Stage 4: NegativeModifiers = PositiveModifiers * prod(1 - mod) (Taunt, DefUp, Resonance)
  Stage 5: Resistance = NegativeModifiers * (1 - Res_percent)
  Stage 6: Redirect = Resistance * prod(1 - RedirectMod) (Safeguard, Tether, Leech)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


@dataclass
class DamageResult:
    """Detailed breakdown of damage through the 6-stage pipeline."""
    stage1_base: float
    stage2_variance: float
    stage3_positive: float
    stage4_negative: float
    stage5_resistance: float
    stage6_redirect: float
    final_damage: float
    variance_applied: int = 0
    redirected_breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def base_damage(self) -> float:
        return self.stage1_base

    @property
    def random_variance(self) -> float:
        return self.stage2_variance

    @property
    def positive_modifiers(self) -> float:
        return self.stage3_positive

    @property
    def negative_modifiers(self) -> float:
        return self.stage4_negative

    @property
    def resistance(self) -> float:
        return self.stage5_resistance

    @property
    def redirect(self) -> float:
        return self.stage6_redirect

    def __getitem__(self, key: str) -> Any:
        normalized = key.lower().replace("_", "")
        key_map = {
            "stage1": self.stage1_base,
            "stage1base": self.stage1_base,
            "base": self.stage1_base,
            "basedamage": self.stage1_base,
            "stage2": self.stage2_variance,
            "stage2variance": self.stage2_variance,
            "randomvariance": self.stage2_variance,
            "variance": self.variance_applied,
            "stage3": self.stage3_positive,
            "stage3positive": self.stage3_positive,
            "positivemodifiers": self.stage3_positive,
            "pos": self.stage3_positive,
            "stage4": self.stage4_negative,
            "stage4negative": self.stage4_negative,
            "negativemodifiers": self.stage4_negative,
            "neg": self.stage4_negative,
            "stage5": self.stage5_resistance,
            "stage5resistance": self.stage5_resistance,
            "resistance": self.stage5_resistance,
            "res": self.stage5_resistance,
            "stage6": self.stage6_redirect,
            "stage6redirect": self.stage6_redirect,
            "redirect": self.stage6_redirect,
            "final": self.final_damage,
            "finaldamage": self.final_damage,
        }
        if normalized in key_map:
            return key_map[normalized]
        raise KeyError(key)


def _normalize_modifiers(
    mods: Sequence[float] | Mapping[str, float] | Iterable[float] | None
) -> list[tuple[str, float]]:
    """Convert modifiers into a list of (label, float_value) pairs."""
    if mods is None:
        return []
    if isinstance(mods, Mapping):
        return [(k, float(v)) for k, v in mods.items()]
    result: list[tuple[str, float]] = []
    for i, item in enumerate(mods):
        if isinstance(item, tuple) and len(item) == 2:
            result.append((str(item[0]), float(item[1])))
        else:
            result.append((f"mod_{i}", float(item)))
    return result


def calculate_damage_pipeline(
    relevant_stat: float | int = 0,
    weapon_modifier: float = 1.0,
    base_damage: float | int | None = None,
    variance: int | None = None,
    deterministic: bool = True,
    rng: random.Random | None = None,
    positive_modifiers: Sequence[float] | Mapping[str, float] | Iterable[float] | None = None,
    negative_modifiers: Sequence[float] | Mapping[str, float] | Iterable[float] | None = None,
    res_percent: float | int = 0.0,
    redirect_modifiers: Sequence[float] | Mapping[str, float] | Iterable[float] | None = None,
) -> DamageResult:
    """
    Execute the 6-stage damage calculation pipeline from Basement math.mdx:

      Stage 1: BaseDamage = RelevantStat * WeaponModifier
      Stage 2: RandomVariance = BaseDamage + random.randint(-50, 50) (or 0 for deterministic)
      Stage 3: PositiveModifiers = BaseDamage + sum(BaseDamage * mod) (AtkUp, Crit, Enrage, Sprout)
      Stage 4: NegativeModifiers = PositiveModifiers * prod(1 - mod) (Taunt, DefUp, Resonance)
      Stage 5: Resistance = NegativeModifiers * (1 - Res_percent)
      Stage 6: Redirect = Resistance * prod(1 - RedirectMod) (Safeguard, Tether, Leech)

    Example from Basement math.mdx:
      Eagle Lvl 50 with Bow:
        RelevantStat = 750 (STR), WeaponModifier = 1.6 -> BaseDamage = 1200
        Variance = 0 -> RandomVariance = 1200
        Pos (+AtkUp 0.25) -> 1200 + (1200 * 0.25) = 1500
        Neg (Taunt 0.5, Resonance 0.1) -> 1500 * (1 - 0.5) * (1 - 0.1) = 675
        Res (60% PR / 0.6) -> 675 * (1 - 0.6) = 270
        Redirect (Safeguard 0.4, Tether 0.4) -> 270 * (1 - 0.4) * (1 - 0.4) = 97.2
    """
    # Stage 1: Base Damage
    if base_damage is not None:
        stage1 = float(base_damage)
    else:
        stage1 = float(relevant_stat) * float(weapon_modifier)

    # Stage 2: Random Variance (-50 to +50)
    if variance is not None:
        applied_variance = int(variance)
    elif rng is not None:
        applied_variance = rng.randint(-50, 50)
    elif deterministic:
        applied_variance = 0
    else:
        applied_variance = random.randint(-50, 50)

    stage2 = stage1 + float(applied_variance)

    # Stage 3: Positive Modifiers
    pos_mods = _normalize_modifiers(positive_modifiers)
    # Buffs scale additively off Base Damage
    pos_sum = sum(stage1 * mod_val for _, mod_val in pos_mods)
    stage3 = stage2 + pos_sum

    # Stage 4: Negative Modifiers (multiplicative reduction)
    neg_mods = _normalize_modifiers(negative_modifiers)
    stage4 = stage3
    for _, mod_val in neg_mods:
        stage4 *= (1.0 - mod_val)

    # Stage 5: Resistance
    res = float(res_percent)
    if res > 1.0:
        res = res / 100.0
    stage5 = stage4 * (1.0 - res)

    # Stage 6: Redirect Modifiers (multiplicative reduction)
    red_mods = _normalize_modifiers(redirect_modifiers)
    stage6 = stage5
    redirected_breakdown: dict[str, float] = {}

    current_val = stage5
    for label, mod_val in red_mods:
        intercepted = current_val * mod_val
        redirected_breakdown[label] = intercepted
        current_val *= (1.0 - mod_val)
    stage6 = current_val

    # Final Damage is the un-redirected damage delivered to the target
    final_damage = stage6

    return DamageResult(
        stage1_base=stage1,
        stage2_variance=stage2,
        stage3_positive=stage3,
        stage4_negative=stage4,
        stage5_resistance=stage5,
        stage6_redirect=stage6,
        final_damage=final_damage,
        variance_applied=applied_variance,
        redirected_breakdown=redirected_breakdown,
    )
