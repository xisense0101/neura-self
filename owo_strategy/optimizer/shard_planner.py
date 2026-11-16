"""
Weapon Shard Dismantle & Crafting Planner for OwO Strategy Engine.

Calculates exact shard returns, protects active/top-tier weapons,
and generates batch dismantle commands to reach shard milestones safely.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from owo_strategy.schemas.models import OwnedWeapon


# Shard Dismantle Payouts (Basement & OwO Wiki)
SHARD_DISMANTLE_RATES: dict[str, int] = {
    "common": 1,
    "uncommon": 3,
    "rare": 5,
    "epic": 25,
    "mythic": 300,
    "mythical": 300,
    "legendary": 1_000,
    "fabled": 5_000,
}

# Milestone Targets
SHARD_MILESTONES = {
    "stat_reroll": 100,
    "passive_reroll": 100,
    "weapon_crate": 5_000,
    "boss_weapon_crate": 12_500,
}


def estimate_weapon_tier(quality_val: Optional[float]) -> str:
    """Classify tier by quality percentage."""
    if quality_val is None or quality_val <= 20.0:
        return "common"
    elif quality_val <= 40.0:
        return "uncommon"
    elif quality_val <= 60.0:
        return "rare"
    elif quality_val <= 80.0:
        return "epic"
    elif quality_val < 95.0:
        return "mythic"
    elif quality_val < 100.0:
        return "legendary"
    else:
        return "fabled"


def calculate_dismantle_shard_value(weapon: OwnedWeapon) -> int:
    """
    Calculate the exact Weapon Shard payout when dismantling a weapon.
    Accounts for rarity tier, empowered prefix ('b' -> 1.5x), and unsellable items.
    """
    name_lower = (weapon.weapon_name or "").lower()
    if "rune of the forgotten" in name_lower:
        return 0

    tier = estimate_weapon_tier(weapon.quality_val)
    base_return = SHARD_DISMANTLE_RATES.get(tier, 1)

    # Check for empowered modifier (1.5x)
    is_empowered = False
    if weapon.id and weapon.id.lower().startswith("b"):
        is_empowered = True
    elif "empowered" in name_lower:
        is_empowered = True

    if is_empowered:
        return int(math.floor(base_return * 1.5))
    return base_return


@dataclass
class DismantlePlan:
    """Summary and batch commands for weapon dismantling."""
    current_shards: int
    projected_shards_gained: int
    total_projected_shards: int
    safe_to_dismantle: list[OwnedWeapon]
    protected_weapons: list[OwnedWeapon]
    candidate_weapons: list[OwnedWeapon]
    batch_commands: list[str]
    next_milestone: str
    milestone_progress_percent: float
    dry_run: bool = True


ShardPlan = DismantlePlan


class ShardPlanner:
    """
    Evaluates player weapon inventory and devises safe shard collection plans.
    """

    def __init__(
        self,
        current_shards: int = 0,
        quality_dismantle_threshold: float = 40.0,
        quality_protect_threshold: float = 80.0,
        dry_run: bool = True,
    ) -> None:
        self.current_shards = max(0, current_shards)
        self.dismantle_threshold = quality_dismantle_threshold
        self.protect_threshold = quality_protect_threshold
        self.dry_run = dry_run

    def generate_plan(
        self,
        inventory_weapons: Sequence[OwnedWeapon],
        protected_weapon_ids: Optional[set[str]] = None,
    ) -> DismantlePlan:
        """
        Analyze inventory and produce safe dismantle recommendations.
        """
        protected_ids = set(protected_weapon_ids or set())

        safe_list: list[OwnedWeapon] = []
        protected_list: list[OwnedWeapon] = []
        candidate_list: list[OwnedWeapon] = []

        total_gain = 0

        for w in inventory_weapons:
            w_id = w.id
            q = w.quality_val

            # If weapon is on active team, explicitly locked, or unknown quality
            if w_id in protected_ids or getattr(w, "is_locked", False) or q is None or q >= self.protect_threshold:
                protected_list.append(w)
            elif q <= self.dismantle_threshold or getattr(w, "is_dismantle_candidate", False):
                safe_list.append(w)
                total_gain += calculate_dismantle_shard_value(w)
            else:
                candidate_list.append(w)

        total_projected = self.current_shards + total_gain

        # Determine next milestone
        next_goal = "boss_weapon_crate"
        target_amount = 12_500
        for m_name, amount in SHARD_MILESTONES.items():
            if total_projected < amount:
                next_goal = m_name
                target_amount = amount
                break

        progress = min(100.0, (total_projected / target_amount) * 100.0)

        # Generate chunked Discord commands (max 10 IDs per command)
        batch_cmds = []
        ids = [w.id for w in safe_list if w.id]
        chunk_size = 10
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i : i + chunk_size]
            batch_cmds.append(f"owo dismantle {' '.join(chunk)}")

        return DismantlePlan(
            current_shards=self.current_shards,
            projected_shards_gained=total_gain,
            total_projected_shards=total_projected,
            safe_to_dismantle=safe_list,
            protected_weapons=protected_list,
            candidate_weapons=candidate_list,
            batch_commands=batch_cmds,
            next_milestone=next_goal,
            milestone_progress_percent=round(progress, 1),
            dry_run=self.dry_run,
        )
