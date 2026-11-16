"""
3-Stage Multi-Fidelity Tournament Team Optimizer.

Implements the multi-fidelity optimization pipeline for OwO Strategy Engine:
  - Stage 0: Domain & Archetype Filtering (prunes dominated combinations).
  - Stage 1: Analytical Heuristic Screening (ranks candidates using evaluator.py, extracts Top 50).
  - Stage 2: Coarse Simulation Tournament (runs 15 seeds against 3 benchmark teams, extracts Top 10).
  - Stage 3: Fine Monte Carlo Evaluation (runs 100 seeds against 5 benchmark teams, selects Winner with 95% Wilson CI).

Execution finishes comfortably in < 30 seconds.
"""

from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from owo_strategy.optimizer.evaluator import (
    CandidateEvaluation,
    evaluate_candidate,
    extract_dex_stats,
    get_weapon_spec,
    normalize_weapon_slug,
)
from owo_strategy.simulator.battle_engine import (
    BattleEngine,
    BattleResult,
    create_pet,
    Team,
    Weapon as SimWeapon,
)


def calculate_wilson_interval(wins: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Calculate 95% Wilson score confidence interval for a binomial proportion."""
    if total <= 0:
        return 0.0, 0.0
    z = 1.95996  # 95% confidence z-score
    p_hat = wins / total
    denom = 1.0 + (z**2) / total
    center = (p_hat + (z**2) / (2.0 * total)) / denom
    margin = (z * math.sqrt((p_hat * (1.0 - p_hat) / total) + (z**2) / (4.0 * total**2))) / denom
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return round(lower, 4), round(upper, 4)


@dataclass
class CandidateTeam:
    """Represents a candidate team setup."""
    animals: list[Any]  # 3 animals
    weapons: list[Any]  # 3 weapons
    candidate_id: str = ""
    heuristic_score: float = 0.0
    evaluation: Optional[CandidateEvaluation] = None

    # Stage 2 metrics (Coarse tournament)
    coarse_win_rate: float = 0.0
    coarse_wins: int = 0
    coarse_total: int = 0
    coarse_remaining_hp: float = 0.0

    # Stage 3 metrics (Fine Monte Carlo)
    fine_win_rate: float = 0.0
    fine_wins: int = 0
    fine_losses: int = 0
    fine_draws: int = 0
    fine_total: int = 0
    fine_remaining_hp: float = 0.0
    wilson_lower: float = 0.0
    wilson_upper: float = 0.0

    @property
    def animal_names(self) -> list[str]:
        res: list[str] = []
        for a in self.animals:
            name = getattr(a, "name", None) or (a.get("name") if isinstance(a, Mapping) else str(a))
            res.append(str(name))
        return res

    @property
    def weapon_names(self) -> list[str]:
        res: list[str] = []
        for w in self.weapons:
            spec = get_weapon_spec(w)
            res.append(spec["name"])
        return res


@dataclass
class OptimizationResult:
    """Final result container from the 3-stage optimizer."""
    winner: CandidateTeam
    top_candidates: list[CandidateTeam]
    current_team_benchmark: Optional[CandidateTeam] = None
    win_rate_delta: float = 0.0
    stage0_candidates_count: int = 0
    stage1_top50_count: int = 0
    stage2_top10_count: int = 0
    stage3_evaluated_count: int = 0
    total_simulations: int = 0
    execution_time_seconds: float = 0.0


def create_sim_weapon(weapon: Any) -> SimWeapon:
    """Build a simulator Weapon object from inventory weapon representation."""
    spec = get_weapon_spec(weapon)
    slug = spec["slug"]
    name = spec["name"]
    mod = spec.get("base_modifier", 1.0)
    wp_cost = spec.get("wp_cost", 100)
    role = spec.get("role", "carry")
    target_type = spec.get("target_type", "single")

    damage_type = "physical"
    if role == "healer":
        damage_type = "heal"
    elif role in ("tank", "buffer") and mod == 0.0:
        damage_type = "buff"
    elif spec.get("stat_type") == "mag":
        damage_type = "magical"

    passives: dict[str, float] = {}
    raw_passives = getattr(weapon, "passives", None) or (
        weapon.get("passives") if isinstance(weapon, Mapping) else None
    )
    if raw_passives:
        if isinstance(raw_passives, Mapping):
            passives.update({k.lower(): float(v) for k, v in raw_passives.items()})
        elif isinstance(raw_passives, (list, tuple)):
            for p in raw_passives:
                p_slug = getattr(p, "slug", "") or (p.get("slug") if isinstance(p, Mapping) else str(p))
                if p_slug:
                    passives[p_slug.lower()] = 1.0

    buff_slugs: list[str] = []
    if "buff" in spec:
        buff_slugs.append(spec["buff"])

    return SimWeapon(
        slug=slug,
        name=name,
        stat_modifier=mod,
        wp_cost=wp_cost,
        damage_type=damage_type,
        target_type=target_type,
        passives=passives,
        buff_slugs=buff_slugs,
    )


def build_sim_team(candidate: CandidateTeam, team_id: str = "team_a", name: str = "Team") -> Team:
    """Convert a CandidateTeam to a simulator Team."""
    pets = []
    for pos in range(3):
        animal = candidate.animals[pos] if pos < len(candidate.animals) else "giraffbot"
        weapon = candidate.weapons[pos] if pos < len(candidate.weapons) else "shield"

        animal_name = getattr(animal, "name", None) or (
            animal.get("name") if isinstance(animal, Mapping) else str(animal)
        )
        raw_level = getattr(animal, "level", None)
        if raw_level is None and isinstance(animal, Mapping):
            raw_level = animal.get("level")
        if raw_level is not None and int(raw_level) > 1:
            animal_level = int(raw_level)
        else:
            animal_level = 50

        dex = extract_dex_stats(animal)
        sim_w = create_sim_weapon(weapon)

        pet = create_pet(
            name=animal_name,
            dex_stats=dex,
            level=animal_level,
            weapon=sim_w,
            position=pos,
            team_id=team_id,
        )
        pets.append(pet)

    return Team(team_id=team_id, name=name, pets=pets)


def get_standard_benchmark_teams() -> list[dict[str, Any]]:
    """
    Define 5 representative benchmark teams reflecting diverse OwO battle metagames:
      0. Classic Balance: Giraffbot (Shield) + Flamingo (Healing Staff) + Eagle (Bow)
      1. Vanguard Cleave: Cow (Banner) + Fox (Great Sword) + Wolf (Bow)
      2. Arcane Poison: Dino (Shield) + Snake (Poison Dagger) + Deer (Orb)
      3. Glacial Freeze: Owl (Shield) + Lion (Glacial Axe) + Tiger (Culling Scythe)
      4. Sustain Lifesteal: Bear (Shield) + Snake (Vampiric Staff) + Eagle (Bow)
    """
    return [
        {
            "name": "Classic Balance",
            "animals": ["giraffbot", "flamingo", "eagle"],
            "weapons": ["shield", "hstaff", "bow"],
        },
        {
            "name": "Vanguard Cleave",
            "animals": ["cow", "fox", "wolf"],
            "weapons": ["banner", "sword", "bow"],
        },
        {
            "name": "Arcane Poison",
            "animals": ["dino", "snake", "deer"],
            "weapons": ["shield", "dagger", "orb"],
        },
        {
            "name": "Glacial Freeze",
            "animals": ["owl", "lion", "tiger"],
            "weapons": ["shield", "axe", "scythe"],
        },
        {
            "name": "Sustain Lifesteal",
            "animals": ["bear", "snake", "eagle"],
            "weapons": ["shield", "vstaff", "bow"],
        },
    ]


class TeamOptimizer:
    """Multi-fidelity tournament team optimizer."""

    def __init__(
        self,
        benchmark_teams: Optional[list[dict[str, Any]]] = None,
        coarse_seeds: int = 15,
        coarse_benchmarks_count: int = 3,
        fine_seeds: int = 100,
        fine_benchmarks_count: int = 5,
    ) -> None:
        self.benchmark_teams = benchmark_teams or get_standard_benchmark_teams()
        self.coarse_seeds = coarse_seeds
        self.coarse_benchmarks_count = min(coarse_benchmarks_count, len(self.benchmark_teams))
        self.fine_seeds = fine_seeds
        self.fine_benchmarks_count = min(fine_benchmarks_count, len(self.benchmark_teams))

    def _generate_stage0_candidates(
        self,
        animals: Sequence[Any],
        weapons: Sequence[Any],
        current_team: Optional[CandidateTeam] = None,
    ) -> list[CandidateTeam]:
        """
        Stage 0: Domain & Archetype Filtering.
        Prunes dominated combinations by classifying animals and weapons into roles,
        and generating coherent, non-dominated candidate teams.
        """
        # Classify animals
        tank_animals = []
        str_animals = []
        mag_animals = []
        healer_animals = []

        for a in animals:
            dex = extract_dex_stats(a)
            hp_pr_mr = dex.get("hp", 0) + dex.get("pr", 0) + dex.get("mr", 0)
            str_stat = dex.get("str", 0)
            mag_stat = dex.get("mag", 0)

            tank_animals.append((hp_pr_mr, a))
            str_animals.append((str_stat, a))
            mag_animals.append((mag_stat, a))
            healer_animals.append((mag_stat + dex.get("wp", 0), a))

        tank_animals.sort(key=lambda x: x[0], reverse=True)
        str_animals.sort(key=lambda x: x[0], reverse=True)
        mag_animals.sort(key=lambda x: x[0], reverse=True)
        healer_animals.sort(key=lambda x: x[0], reverse=True)

        top_tanks = [x[1] for x in tank_animals[:4]]
        top_str_carries = [x[1] for x in str_animals[:5]]
        top_mag_carries = [x[1] for x in mag_animals[:5]]
        top_healers = [x[1] for x in healer_animals[:4]]

        # Classify weapons
        tank_weapons = []
        str_weapons = []
        mag_weapons = []
        healer_weapons = []

        for w in weapons:
            spec = get_weapon_spec(w)
            role = spec["role"]
            q = spec.get("quality_val", 80.0)

            if role in ("tank", "buffer") or spec["slug"] in ("shield", "banner", "crune"):
                tank_weapons.append((q, w))
            if spec["stat_type"] == "str" and role in ("carry", "disruptor"):
                str_weapons.append((q, w))
            if spec["stat_type"] == "mag" and role in ("carry", "disruptor"):
                mag_weapons.append((q, w))
            if role == "healer" or spec["slug"] == "hstaff":
                healer_weapons.append((q, w))

        tank_weapons.sort(key=lambda x: x[0], reverse=True)
        str_weapons.sort(key=lambda x: x[0], reverse=True)
        mag_weapons.sort(key=lambda x: x[0], reverse=True)
        healer_weapons.sort(key=lambda x: x[0], reverse=True)

        top_tank_w = [x[1] for x in tank_weapons[:4]]
        top_str_w = [x[1] for x in str_weapons[:5]]
        top_mag_w = [x[1] for x in mag_weapons[:5]]
        top_healer_w = [x[1] for x in healer_weapons[:3]]

        # Fallbacks if a role category is empty in inventory
        if not top_tank_w and weapons:
            top_tank_w = [weapons[0]]
        if not top_str_w and weapons:
            top_str_w = [weapons[0]]
        if not top_mag_w and weapons:
            top_mag_w = [weapons[0]]

        candidates: list[CandidateTeam] = []
        seen_keys: set[str] = set()

        def _get_item_id(item: Any, fallback_prefix: str) -> str:
            item_id = getattr(item, "id", None) or getattr(item, "animal_id", None)
            if not item_id and isinstance(item, Mapping):
                item_id = item.get("id") or item.get("animal_id")
            if not item_id:
                name = getattr(item, "name", None) or (item.get("name") if isinstance(item, Mapping) else str(item))
                item_id = f"{fallback_prefix}_{name}"
            return str(item_id)

        def add_candidate(a_list: list[Any], w_list: list[Any]):
            # Verify no duplicate animals and no duplicate weapons
            a_ids = [_get_item_id(a, "a") for a in a_list]
            w_ids = [_get_item_id(w, "w") for w in w_list]
            if len(set(a_ids)) != 3 or len(set(w_ids)) != 3:
                return
            cand_key = f"{','.join(a_ids)}|{','.join(w_ids)}"
            if cand_key in seen_keys:
                return
            seen_keys.add(cand_key)
            candidates.append(CandidateTeam(animals=a_list, weapons=w_list, candidate_id=cand_key))

        # Template 1: Classic Balanced (Tank + Healer + STR Carry)
        for t_a in top_tanks:
            for t_w in top_tank_w:
                for h_a in top_healers:
                    for h_w in top_healer_w:
                        for c_a in top_str_carries:
                            for c_w in top_str_w:
                                add_candidate([t_a, h_a, c_a], [t_w, h_w, c_w])

        # Template 2: Dual Carry Shield (Tank + STR Carry + MAG Carry)
        for t_a in top_tanks:
            for t_w in top_tank_w:
                for c1_a in top_str_carries:
                    for c1_w in top_str_w:
                        for c2_a in top_mag_carries:
                            for c2_w in top_mag_w:
                                add_candidate([t_a, c1_a, c2_a], [t_w, c1_w, c2_w])

        # Template 3: Dual STR Carry (Tank + STR Cleave/Axe + STR Sniper)
        for t_a in top_tanks:
            for t_w in top_tank_w:
                for i in range(len(top_str_carries)):
                    for j in range(i + 1, len(top_str_carries)):
                        c1_a = top_str_carries[i]
                        c2_a = top_str_carries[j]
                        for m in range(len(top_str_w)):
                            for n in range(len(top_str_w)):
                                if m != n:
                                    add_candidate([t_a, c1_a, c2_a], [t_w, top_str_w[m], top_str_w[n]])

        # Include Current Team if provided
        if current_team:
            c_key = f"current_{','.join(current_team.animal_names)}|{','.join(current_team.weapon_names)}"
            current_team.candidate_id = c_key
            candidates.append(current_team)

        return candidates

    def _simulate_matches(
        self,
        candidate: CandidateTeam,
        benchmark_indices: list[int],
        seed_range: range,
    ) -> tuple[int, int, int, float]:
        """Simulate candidate against benchmark teams over seeds. Returns (wins, losses, draws, avg_remaining_hp)."""
        wins = 0
        losses = 0
        draws = 0
        total_hp_rem = 0.0

        for b_idx in benchmark_indices:
            b_data = self.benchmark_teams[b_idx]
            b_candidate = CandidateTeam(animals=b_data["animals"], weapons=b_data["weapons"])

            for s in seed_range:
                # Build fresh simulator teams for clean state
                team_a = build_sim_team(candidate, team_id="team_a", name="Candidate")
                team_b = build_sim_team(b_candidate, team_id="team_b", name=b_data["name"])

                engine = BattleEngine(team_a, team_b, seed=s)
                res: BattleResult = engine.run_battle(max_turns=24)

                if res.winner == "team_a":
                    wins += 1
                elif res.winner == "team_b":
                    losses += 1
                else:
                    draws += 1
                total_hp_rem += res.team_a_hp_remaining

        total_games = len(benchmark_indices) * len(seed_range)
        avg_hp = total_hp_rem / total_games if total_games > 0 else 0.0
        return wins, losses, draws, avg_hp

    def evaluate_fine_monte_carlo(
        self,
        candidate: CandidateTeam,
        benchmark_indices: Optional[list[int]] = None,
        seeds_count: Optional[int] = None,
    ) -> CandidateTeam:
        """Run fine Monte Carlo benchmark evaluation on a candidate team."""
        indices = benchmark_indices if benchmark_indices is not None else list(range(len(self.benchmark_teams)))
        seeds = range(seeds_count if seeds_count is not None else self.fine_seeds)
        wins, losses, draws, avg_hp = self._simulate_matches(
            candidate=candidate,
            benchmark_indices=indices,
            seed_range=seeds,
        )
        total_games = len(indices) * len(seeds)
        candidate.fine_wins = wins
        candidate.fine_losses = losses
        candidate.fine_draws = draws
        candidate.fine_total = total_games
        candidate.fine_win_rate = wins / total_games if total_games > 0 else 0.0
        candidate.fine_remaining_hp = avg_hp
        lower, upper = calculate_wilson_interval(wins, total_games)
        candidate.wilson_lower = lower
        candidate.wilson_upper = upper
        return candidate

    def optimize(
        self,
        inventory_animals: Sequence[Any],
        inventory_weapons: Sequence[Any],
        current_team: Optional[CandidateTeam] = None,
        level: int = 50,
    ) -> OptimizationResult:
        """
        Execute full 3-Stage Multi-Fidelity Tournament optimization pipeline.
        Must execute in < 30 seconds.
        """
        start_time = time.time()
        sim_count = 0

        # Stage 0: Domain & Archetype Filtering
        stage0_candidates = self._generate_stage0_candidates(
            animals=inventory_animals,
            weapons=inventory_weapons,
            current_team=current_team,
        )
        stage0_count = len(stage0_candidates)

        # Stage 1: Analytical Heuristic Screening
        valid_screened: list[CandidateTeam] = []
        for cand in stage0_candidates:
            eval_res = evaluate_candidate(cand.animals, cand.weapons, level=level)
            cand.evaluation = eval_res
            cand.heuristic_score = eval_res.score
            if eval_res.is_valid:
                valid_screened.append(cand)

        # Fallback if no combinations strictly satisfy role constraints
        if not valid_screened and stage0_candidates:
            stage0_candidates.sort(key=lambda c: getattr(c, "heuristic_score", 0), reverse=True)
            valid_screened = stage0_candidates[:50]

        # Sort descending by heuristic score and extract Top 50
        valid_screened.sort(key=lambda c: c.heuristic_score, reverse=True)
        top50 = valid_screened[:50]
        if not top50 and current_team:
            top50 = [current_team]
        top50_count = len(top50)

        # Stage 2: Coarse Simulation Tournament (15 seeds against 3 benchmarks)
        coarse_benchmarks = list(range(self.coarse_benchmarks_count))
        coarse_seeds = range(101, 101 + self.coarse_seeds)
        coarse_total_games = len(coarse_benchmarks) * len(coarse_seeds)

        for cand in top50:
            wins, losses, draws, avg_hp = self._simulate_matches(
                candidate=cand,
                benchmark_indices=coarse_benchmarks,
                seed_range=coarse_seeds,
            )
            sim_count += coarse_total_games
            cand.coarse_wins = wins
            cand.coarse_total = coarse_total_games
            cand.coarse_win_rate = wins / coarse_total_games
            cand.coarse_remaining_hp = avg_hp

        # Sort by coarse win rate (tie-breaker: average remaining HP)
        top50.sort(key=lambda c: (c.coarse_win_rate, c.coarse_remaining_hp), reverse=True)
        top10 = top50[:10]
        top10_count = len(top10)

        # Stage 3: Fine Monte Carlo Evaluation (100 seeds against 5 benchmarks)
        fine_benchmarks = list(range(self.fine_benchmarks_count))
        fine_seeds = range(201, 201 + self.fine_seeds)
        fine_total_games = len(fine_benchmarks) * len(fine_seeds)

        for cand in top10:
            wins, losses, draws, avg_hp = self._simulate_matches(
                candidate=cand,
                benchmark_indices=fine_benchmarks,
                seed_range=fine_seeds,
            )
            sim_count += fine_total_games
            cand.fine_wins = wins
            cand.fine_losses = losses
            cand.fine_draws = draws
            cand.fine_total = fine_total_games
            cand.fine_win_rate = wins / fine_total_games
            cand.fine_remaining_hp = avg_hp
            lower, upper = calculate_wilson_interval(wins, fine_total_games)
            cand.wilson_lower = lower
            cand.wilson_upper = upper

        # Rank Top 10 by (fine_win_rate, wilson_lower, remaining_hp) descending
        top10.sort(key=lambda c: (c.fine_win_rate, c.wilson_lower, c.fine_remaining_hp), reverse=True)
        if not top10:
            if top50:
                top10 = top50[:10]
            elif current_team:
                top10 = [current_team]
            else:
                top10 = [CandidateTeam(animals=list(inventory_animals[:3]), weapons=list(inventory_weapons[:3]))]
        winner = top10[0]

        # Evaluate current_team on Fine Monte Carlo if supplied
        current_team_benchmark = None
        win_rate_delta = 0.0
        if current_team:
            # Check if current_team was already in top10
            matched = next((c for c in top10 if c.candidate_id == current_team.candidate_id), None)
            if matched:
                current_team_benchmark = matched
            else:
                # Benchmark current team across the fine evaluation
                wins, losses, draws, avg_hp = self._simulate_matches(
                    candidate=current_team,
                    benchmark_indices=fine_benchmarks,
                    seed_range=fine_seeds,
                )
                sim_count += fine_total_games
                current_team.fine_wins = wins
                current_team.fine_losses = losses
                current_team.fine_draws = draws
                current_team.fine_total = fine_total_games
                current_team.fine_win_rate = wins / fine_total_games
                current_team.fine_remaining_hp = avg_hp
                lower, upper = calculate_wilson_interval(wins, fine_total_games)
                current_team.wilson_lower = lower
                current_team.wilson_upper = upper
                current_team_benchmark = current_team

            win_rate_delta = winner.fine_win_rate - current_team_benchmark.fine_win_rate

        elapsed = time.time() - start_time

        return OptimizationResult(
            winner=winner,
            top_candidates=top10,
            current_team_benchmark=current_team_benchmark,
            win_rate_delta=round(win_rate_delta, 4),
            stage0_candidates_count=stage0_count,
            stage1_top50_count=top50_count,
            stage2_top10_count=top10_count,
            stage3_evaluated_count=len(top10),
            total_simulations=sim_count,
            execution_time_seconds=round(elapsed, 3),
        )
