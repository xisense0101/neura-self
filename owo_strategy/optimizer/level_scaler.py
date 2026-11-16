"""
Multi-Level Progression Simulator & NeonUtil Team Mocking Integration.

Enables:
  1. Multi-level scaling analysis (Level 1, 20, 50, 75, 100).
  2. Progression curves for EHP, damage scaling, and benchmark win rates with Wilson CIs.
  3. Exporting team configurations as NeonUtil Discord commands (/team create, /team weapon set, /team battle).
  4. Generating in-game OwO equipping commands.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from owo_strategy.ingestion.owo_parser import normalize_animal_name
from owo_strategy.optimizer.evaluator import (
    extract_dex_stats,
    get_weapon_spec,
    normalize_weapon_slug,
)
from owo_strategy.optimizer.team_optimizer import (
    CandidateTeam,
    calculate_wilson_interval,
    create_sim_weapon,
    get_standard_benchmark_teams,
)
from owo_strategy.simulator.battle_engine import (
    BattleEngine,
    BattleResult,
    create_pet,
    Team,
)
from owo_strategy.simulator.formulas import calculate_pet_stats, PetStats


@dataclass
class PetLevelStats:
    """Individual pet stats at a given level."""
    name: str
    position: int
    level: int
    hp: int
    wp: int
    str: int
    mag: int
    pr_percent: int
    mr_percent: int
    ehp_physical: float
    ehp_magical: float


@dataclass
class LevelProgressionPoint:
    """Team combat performance snapshot at a specific level."""
    level: int
    pet_stats: list[PetLevelStats]
    team_hp: int
    team_ehp_physical: float
    team_ehp_magical: float
    win_rate: float
    wilson_lower: float
    wilson_upper: float
    wins: int
    total_sims: int
    avg_turns: float
    avg_remaining_hp: float


class MultiLevelScaler:
    """
    Simulates candidate team progression across levels 1 through 100 against
    standard benchmark teams scaled to matching levels.
    """

    def __init__(self, benchmark_teams: Optional[list[dict[str, Any]]] = None) -> None:
        self.benchmark_templates = benchmark_teams or get_standard_benchmark_teams()

    def _build_scaled_team(
        self,
        candidate: CandidateTeam,
        level: int,
        team_id: str = "team_a",
        name: str = "Candidate",
    ) -> Team:
        pets = []
        for pos in range(3):
            animal = candidate.animals[pos]
            weapon = candidate.weapons[pos]
            a_name = getattr(animal, "name", None) or (
                animal.get("name") if isinstance(animal, Mapping) else str(animal)
            )
            dex = extract_dex_stats(animal)
            sim_w = create_sim_weapon(weapon)

            pet = create_pet(
                name=a_name,
                dex_stats=dex,
                level=level,
                weapon=sim_w,
                position=pos,
                team_id=team_id,
            )
            pets.append(pet)
        return Team(team_id=team_id, name=name, pets=pets)

    def _build_scaled_benchmark(
        self,
        bmark: dict[str, Any],
        level: int,
        team_id: str = "team_b",
    ) -> Team:
        b_candidate = CandidateTeam(animals=bmark["animals"], weapons=bmark["weapons"])
        return self._build_scaled_team(b_candidate, level=level, team_id=team_id, name=bmark["name"])

    def simulate_level(
        self,
        candidate: CandidateTeam,
        level: int,
        sims_per_benchmark: int = 10,
        base_seed: int = 5000,
    ) -> LevelProgressionPoint:
        """Simulate candidate performance at a specific level."""
        # Calculate raw pet stats and EHPs at this level
        pet_stats_list: list[PetLevelStats] = []
        total_hp = 0
        total_ehp_p = 0.0
        total_ehp_m = 0.0

        for pos in range(3):
            animal = candidate.animals[pos]
            a_name = getattr(animal, "name", None) or (
                animal.get("name") if isinstance(animal, Mapping) else str(animal)
            )
            dex = extract_dex_stats(animal)
            stats = calculate_pet_stats(level=level, dex_stats=dex)
            pet_stats_list.append(
                PetLevelStats(
                    name=a_name,
                    position=pos + 1,
                    level=level,
                    hp=stats.hp,
                    wp=stats.wp,
                    str=stats.str,
                    mag=stats.mag,
                    pr_percent=stats.pr_percent,
                    mr_percent=stats.mr_percent,
                    ehp_physical=stats.ehp_physical,
                    ehp_magical=stats.ehp_magical,
                )
            )
            total_hp += stats.hp
            total_ehp_p += stats.ehp_physical
            total_ehp_m += stats.ehp_magical

        # Run simulated matches against scaled benchmarks
        total_sims = 0
        wins = 0
        total_turns = 0
        total_remaining_hp = 0.0

        for b_idx, bmark in enumerate(self.benchmark_templates):
            for s_idx in range(sims_per_benchmark):
                seed = base_seed + (level * 1000) + (b_idx * 100) + s_idx
                team_a = self._build_scaled_team(candidate, level=level, team_id="team_a")
                team_b = self._build_scaled_benchmark(bmark, level=level, team_id="team_b")

                engine = BattleEngine(
                    team_a=team_a,
                    team_b=team_b,
                    seed=seed,
                )
                res = engine.run_battle(max_turns=24)
                total_sims += 1
                total_turns += res.total_turns
                if res.winner == "team_a":
                    wins += 1
                    total_remaining_hp += res.team_a_hp_remaining

        win_rate = (wins / total_sims) if total_sims > 0 else 0.0
        lower, upper = calculate_wilson_interval(wins, total_sims)
        avg_turns = (total_turns / total_sims) if total_sims > 0 else 0.0
        avg_hp = (total_remaining_hp / total_sims) if total_sims > 0 else 0.0

        return LevelProgressionPoint(
            level=level,
            pet_stats=pet_stats_list,
            team_hp=total_hp,
            team_ehp_physical=round(total_ehp_p, 1),
            team_ehp_magical=round(total_ehp_m, 1),
            win_rate=round(win_rate, 4),
            wilson_lower=lower,
            wilson_upper=upper,
            wins=wins,
            total_sims=total_sims,
            avg_turns=round(avg_turns, 1),
            avg_remaining_hp=round(avg_hp, 1),
        )

    def simulate_progression(
        self,
        candidate: CandidateTeam,
        levels: tuple[int, ...] = (1, 20, 50, 75, 100),
        sims_per_benchmark: int = 10,
    ) -> list[LevelProgressionPoint]:
        """Run progression sweep across multiple level tiers."""
        progression: list[LevelProgressionPoint] = []
        for lvl in levels:
            p_point = self.simulate_level(
                candidate,
                level=lvl,
                sims_per_benchmark=sims_per_benchmark,
            )
            progression.append(p_point)
        return progression

    def format_progression_table(self, progression: list[LevelProgressionPoint]) -> str:
        """Format progression list as a clean markdown table."""
        lines = [
            "| Level | Team HP | Phys EHP | Mag EHP | Win Rate | 95% Wilson CI | Avg Turns | Avg Rem HP |",
            "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
        for p in progression:
            ci_str = f"[{p.wilson_lower*100:.1f}%, {p.wilson_upper*100:.1f}%]"
            lines.append(
                f"| **Lvl {p.level}** | {p.team_hp:,} | {p.team_ehp_physical:,.0f} | "
                f"{p.team_ehp_magical:,.0f} | **{p.win_rate*100:.1f}%** | {ci_str} | "
                f"{p.avg_turns:.1f} | {p.avg_remaining_hp:,.0f} |"
            )
        return "\n".join(lines)


class NeonUtilExporter:
    """
    Formats candidate teams into Discord commands for:
      - NeonUtil bot team creation and battle mocking.
      - Official OwO bot team and weapon equip commands.
    """

    @staticmethod
    def generate_neon_create_command(candidate: CandidateTeam, team_name: str = "Alpha") -> str:
        """
        Generate NeonUtil /team create command.
        Example: /team create name:Alpha animal1:giraffbot animal2:flamingo animal3:eagle
        """
        animals = [
            (getattr(a, "name", None) or (a.get("name") if isinstance(a, Mapping) else str(a))).lower()
            for a in candidate.animals
        ]
        return f"/team create name:{team_name} animal1:{animals[0]} animal2:{animals[1]} animal3:{animals[2]}"

    @staticmethod
    def generate_neon_weapon_commands(candidate: CandidateTeam, team_name: str = "Alpha") -> list[str]:
        """
        Generate NeonUtil /team weapon set commands for each slot.
        """
        cmds = []
        for pos, w in enumerate(candidate.weapons):
            spec = get_weapon_spec(w)
            slug = spec.get("slug", "fists")
            cmds.append(f"/team weapon set team:{team_name} slot:{pos+1} weapon:{slug}")
        return cmds

    @staticmethod
    def generate_neon_battle_command(
        team_name: str = "Alpha",
        opponent_team: str = "Classic",
        level: int = 50,
    ) -> str:
        """
        Generate NeonUtil /team battle command to mock match against predefined templates.
        """
        return f"/team battle team1:{team_name} team2:{opponent_team} level:{level}"

    @staticmethod
    def generate_owo_game_commands(
        candidate: CandidateTeam,
        current_team: Optional[Sequence[Any]] = None,
        force_reteam: bool = False,
    ) -> list[str]:
        """
        Generate official OwO bot equip commands for the Discord channel.
        Official OwO syntax:
          owo team remove <pos>          (clears slot first to avoid 'team full' or collision)
          owo team add <animal> <pos>    (where pos is 1, 2, or 3)
          owo weapon <weaponID> <animal> (equips weapon onto target pet)
        """
        cmds: list[str] = []
        target_animals = [
            normalize_animal_name(str(getattr(a, "name", None) or (a.get("name") if isinstance(a, Mapping) else str(a))))
            for a in candidate.animals
        ]

        current_animals: list[str] = []
        if current_team:
            for a in current_team:
                raw_name = str(getattr(a, "name", None) or (a.get("name") if isinstance(a, Mapping) else str(a)))
                cur_name = normalize_animal_name(raw_name)
                if cur_name in ("none", "empty", "no animal", "null"):
                    cur_name = ""
                current_animals.append(cur_name)

        # 1. Determine which slots require changes
        needs_change = [False, False, False]
        for pos_idx in range(3):
            tgt_a = target_animals[pos_idx] if pos_idx < len(target_animals) else ""
            cur_a = current_animals[pos_idx] if pos_idx < len(current_animals) else ""
            if force_reteam or (tgt_a and tgt_a != cur_a):
                needs_change[pos_idx] = True

        # Clear existing occupants for modified slots to prevent 'team full' errors in OwO
        for pos_idx in range(3):
            pos = pos_idx + 1
            cur_a = current_animals[pos_idx] if pos_idx < len(current_animals) else ""
            if needs_change[pos_idx] and cur_a:
                cmds.append(f"owo team remove {pos}")

        # Add target animals into positions
        for pos_idx in range(3):
            pos = pos_idx + 1
            tgt_a = target_animals[pos_idx] if pos_idx < len(target_animals) else ""
            if tgt_a and needs_change[pos_idx]:
                cmds.append(f"owo team add {tgt_a} {pos}")

        # 2. Weapon equips via official 'owo weapon <weaponID> <animal>'
        for pos, w in enumerate(candidate.weapons):
            w_id = getattr(w, "id", None) or (w.get("id") if isinstance(w, Mapping) else None)
            target_pet = target_animals[pos] if pos < len(target_animals) else ""
            if w_id and target_pet:
                cmds.append(f"owo weapon {w_id} {target_pet}")
            elif target_pet:
                spec = get_weapon_spec(w)
                cmds.append(f"# owo weapon <{spec['name']} ID> {target_pet}")

        return cmds

    @classmethod
    def generate_full_export_summary(
        cls,
        candidate: CandidateTeam,
        progression: Optional[list[LevelProgressionPoint]] = None,
        team_name: str = "Alpha",
    ) -> dict[str, Any]:
        """
        Produce a unified export dictionary containing all Discord commands and stats.
        """
        neon_create = cls.generate_neon_create_command(candidate, team_name=team_name)
        neon_weapons = cls.generate_neon_weapon_commands(candidate, team_name=team_name)
        neon_battle = cls.generate_neon_battle_command(team_name=team_name, opponent_team="Classic", level=50)
        owo_cmds = cls.generate_owo_game_commands(candidate)

        res: dict[str, Any] = {
            "team_name": team_name,
            "neon_commands": {
                "create": neon_create,
                "weapons": neon_weapons,
                "mock_battle": neon_battle,
            },
            "owo_commands": owo_cmds,
        }

        if progression:
            res["progression_data"] = [
                {
                    "level": p.level,
                    "team_hp": p.team_hp,
                    "team_ehp_physical": p.team_ehp_physical,
                    "team_ehp_magical": p.team_ehp_magical,
                    "win_rate": p.win_rate,
                    "wilson_ci": [p.wilson_lower, p.wilson_upper],
                    "avg_turns": p.avg_turns,
                }
                for p in progression
            ]

        return res
