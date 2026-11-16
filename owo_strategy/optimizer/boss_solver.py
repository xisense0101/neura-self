"""
Guild Boss Raid Solver for OwO Strategy Engine.

Simulates battles against massive HP guild bosses and optimizes team
loadouts specifically for:
  1. Maximum Accumulated Boss Damage over 24 turns.
  2. Maximum Survival Turn Count (surviving past turn 18-24).
  3. Sustained Frontline Tanking & Healing (Shield Taunt + Healing Staff overheal).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from owo_strategy.simulator.battle_engine import (
    BattleEngine,
    BattleResult,
    create_pet,
    Team,
    Weapon as SimWeapon,
)
from owo_strategy.simulator.formulas import calculate_pet_stats, PetStats
from owo_strategy.optimizer.evaluator import get_weapon_spec, extract_dex_stats
from owo_strategy.optimizer.team_optimizer import create_sim_weapon


@dataclass
class BossPreset:
    """Represents a Guild Boss combatant profile."""
    name: str
    hp: int
    attack_power: int
    attack_type: str = "physical"  # "physical", "magical", "mixed"
    pr: float = 0.40  # 40% physical resistance
    mr: float = 0.40  # 40% magical resistance
    aoe: bool = True  # Whether boss attacks all allies
    aoe_multiplier: float = 0.45
    single_multiplier: float = 1.0


STANDARD_BOSS_PRESETS: dict[str, BossPreset] = {
    "standard_cleave": BossPreset(
        name="Abyssal Behemoth",
        hp=2_500_000,
        attack_power=950,
        attack_type="physical",
        pr=0.45,
        mr=0.40,
        aoe=True,
        aoe_multiplier=0.40,
    ),
    "single_nuker": BossPreset(
        name="Infernal Executioner",
        hp=1_800_000,
        attack_power=1400,
        attack_type="mixed",
        pr=0.50,
        mr=0.35,
        aoe=False,
        single_multiplier=1.2,
    ),
    "magic_sorcerer": BossPreset(
        name="Voidweaver Archon",
        hp=3_000_000,
        attack_power=1100,
        attack_type="magical",
        pr=0.30,
        mr=0.55,
        aoe=True,
        aoe_multiplier=0.50,
    ),
}


@dataclass
class BossSimulationResult:
    """Results from simulating a team against a guild boss."""
    total_damage_dealt: float
    turns_survived: int
    full_24_turns: bool
    remaining_team_hp: float
    score: float
    details: str = ""


class BossRaidSolver:
    """
    Evaluates and ranks team compositions specifically for Guild Boss encounters.
    """

    def __init__(self, boss_preset: Optional[BossPreset] = None) -> None:
        self.boss = boss_preset or STANDARD_BOSS_PRESETS["standard_cleave"]

    def _create_boss_pet(self) -> Any:
        """Create the boss combatant using battle_engine create_pet."""
        return create_pet(
            name=self.boss.name,
            dex_stats={"hp": 50, "str": 30, "pr": 10, "wp": 20, "mag": 30, "mr": 10},
            level=100,
            weapon=SimWeapon(
                slug="sword" if self.boss.attack_type == "physical" else "wand",
                name=f"{self.boss.name}'s Wrath",
                stat_modifier=1.0,
                wp_cost=0,
                damage_type=self.boss.attack_type if self.boss.attack_type != "mixed" else "physical",
                target_type="all" if self.boss.aoe else "single",
            ),
            position=0,
            team_id="team_b",
        )

    def simulate_boss_fight(
        self,
        candidate_animals: list[Any],
        candidate_weapons: list[Any],
        level: int = 50,
        seed: int = 42,
    ) -> BossSimulationResult:
        """
        Simulate a 24-turn guild boss fight with deterministic replay.
        """
        # Create Player Team
        team_pets = []
        for i in range(3):
            animal = candidate_animals[i] if i < len(candidate_animals) else "giraffbot"
            weapon = candidate_weapons[i] if i < len(candidate_weapons) else "shield"
            a_name = getattr(animal, "name", str(animal)).lower()
            dex = extract_dex_stats(animal)
            sim_w = create_sim_weapon(weapon)

            p = create_pet(
                name=a_name,
                dex_stats=dex,
                level=level,
                weapon=sim_w,
                position=i,
                team_id="team_a",
            )
            team_pets.append(p)

        player_team = Team(team_id="team_a", name="Player Raid Team", pets=team_pets)

        # Create Boss Combatant (Boss sits at pos 1 with dummy support)
        boss_pet = self._create_boss_pet()
        # Scale boss HP directly to raid levels
        boss_pet.max_hp = self.boss.hp
        boss_pet.current_hp = float(self.boss.hp)
        boss_pet.str = self.boss.attack_power

        boss_team = Team(team_id="team_b", name="Guild Boss", pets=[boss_pet])

        # Run Battle Simulation
        engine = BattleEngine(
            team_a=player_team,
            team_b=boss_team,
            seed=seed,
        )
        res = engine.run_battle(max_turns=24)

        # Calculate metrics
        damage_dealt = max(0.0, float(self.boss.hp - boss_pet.current_hp))
        survived_turns = res.total_turns
        all_alive = any(p.is_alive for p in player_team.pets)
        full_24 = (survived_turns >= 24) and all_alive
        team_hp_left = sum(p.current_hp for p in player_team.pets if p.is_alive)

        # Survival multiplier: surviving all 24 turns earns massive score multiplier
        survival_bonus = 1.0 + (0.04 * survived_turns) + (0.5 if full_24 else 0.0)
        score = damage_dealt * survival_bonus

        details = (
            f"Dealt {damage_dealt:,.0f} dmg over {survived_turns} turns. "
            f"Survival: {'Full 24 turns survived' if full_24 else f'Wiped at turn {survived_turns}'}. "
            f"Remaining HP: {team_hp_left:,.0f}."
        )

        return BossSimulationResult(
            total_damage_dealt=damage_dealt,
            turns_survived=survived_turns,
            full_24_turns=full_24,
            remaining_team_hp=team_hp_left,
            score=score,
            details=details,
        )

    def evaluate_lineup_monte_carlo(
        self,
        candidate_animals: list[Any],
        candidate_weapons: list[Any],
        level: int = 50,
        seeds_count: int = 25,
    ) -> dict[str, Any]:
        """
        Run Monte Carlo simulations across multiple seeds against the boss.
        """
        results = []
        for s in range(seeds_count):
            r = self.simulate_boss_fight(
                candidate_animals, candidate_weapons, level=level, seed=1000 + s
            )
            results.append(r)

        avg_damage = sum(r.total_damage_dealt for r in results) / len(results)
        avg_turns = sum(r.turns_survived for r in results) / len(results)
        full_24_rate = sum(1 for r in results if r.full_24_turns) / len(results)
        avg_score = sum(r.score for r in results) / len(results)

        return {
            "boss_name": self.boss.name,
            "preset_slug": getattr(self.boss, "slug", getattr(self.boss, "name", "standard_cleave")),
            "avg_damage_dealt": round(avg_damage, 1),
            "avg_turns_survived": round(avg_turns, 1),
            "full_24_turns_rate_percent": round(full_24_rate * 100, 1),
            "composite_score": round(avg_score, 1),
            "sample_details": results[0].details,
        }
