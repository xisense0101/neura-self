"""
Analytical Heuristic Evaluator for OwO Strategy Engine.

Provides fast, sub-millisecond heuristic scoring and archetype validation
for candidate teams (3 animals + 3 weapons) according to Basement mechanics:
  - Effective HP (EHP) across frontline/tank.
  - Theoretical sustained DPS output across 8 turns.
  - WP solvency (verifies weapons don't run dry on WP before turn 8).
  - Role archetype validation: at least 1 tank/disruptor (Shield/Banner/High EHP)
    and at least 1 offensive carry.
  - Discards invalid pairings (e.g. pure STR weapons on pure MAG pets).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from owo_strategy.simulator.formulas import (
    calculate_effective_resistance,
    calculate_ehp,
    calculate_pet_stats,
    PetStats,
)


# Canonical base stat database for common OwO animals
KNOWN_ANIMAL_DEX: dict[str, dict[str, int]] = {
    "giraffbot": {"hp": 10, "str": 1, "pr": 3, "wp": 2, "mag": 1, "mr": 3},
    "owl": {"hp": 10, "str": 1, "pr": 3, "wp": 1, "mag": 2, "mr": 3},
    "cow": {"hp": 8, "str": 2, "pr": 3, "wp": 3, "mag": 1, "mr": 3},
    "dino": {"hp": 8, "str": 5, "pr": 2, "wp": 2, "mag": 1, "mr": 2},
    "eagle": {"hp": 4, "str": 13, "pr": 1, "wp": 1, "mag": 1, "mr": 1},
    "fox": {"hp": 4, "str": 9, "pr": 1, "wp": 3, "mag": 1, "mr": 2},
    "lion": {"hp": 5, "str": 11, "pr": 1, "wp": 2, "mag": 1, "mr": 1},
    "tiger": {"hp": 4, "str": 12, "pr": 1, "wp": 2, "mag": 1, "mr": 1},
    "wolf": {"hp": 4, "str": 10, "pr": 1, "wp": 2, "mag": 2, "mr": 1},
    "flamingo": {"hp": 3, "str": 1, "pr": 1, "wp": 3, "mag": 11, "mr": 1},
    "snake": {"hp": 3, "str": 2, "pr": 1, "wp": 2, "mag": 12, "mr": 1},
    "deer": {"hp": 3, "str": 1, "pr": 1, "wp": 3, "mag": 11, "mr": 1},
    "frog": {"hp": 5, "str": 2, "pr": 1, "wp": 5, "mag": 7, "mr": 1},
    "dove": {"hp": 4, "str": 1, "pr": 2, "wp": 4, "mag": 8, "mr": 2},
    "rabbit": {"hp": 4, "str": 3, "pr": 2, "wp": 4, "mag": 6, "mr": 2},
    "cat": {"hp": 5, "str": 6, "pr": 2, "wp": 3, "mag": 3, "mr": 2},
    "dog": {"hp": 5, "str": 5, "pr": 2, "wp": 3, "mag": 3, "mr": 2},
    "bear": {"hp": 8, "str": 8, "pr": 2, "wp": 1, "mag": 1, "mr": 1},
    "elephant": {"hp": 10, "str": 3, "pr": 3, "wp": 2, "mag": 1, "mr": 2},
}

# Weapon specifications based on Basement data
WEAPON_SPECS: dict[str, dict[str, Any]] = {
    "shield": {
        "slug": "shield",
        "name": "Defender's Aegis",
        "role": "tank",
        "stat_type": "defense",
        "base_modifier": 0.0,
        "wp_cost": 120,
        "buff": "taunt",
        "target_type": "self",
        "description": "Applies Taunt reducing incoming damage by 50%",
    },
    "banner": {
        "slug": "banner",
        "name": "Vanguard's Banner",
        "role": "buffer",
        "stat_type": "buff",
        "base_modifier": 0.0,
        "wp_cost": 235,
        "buff": "attup",
        "target_type": "all_allies",
        "description": "Applies Attack Up (+25% damage) to all allies",
    },
    "bow": {
        "slug": "bow",
        "name": "Bow",
        "role": "carry",
        "stat_type": "str",
        "base_modifier": 1.60,
        "wp_cost": 120,
        "target_type": "single",
        "description": "Deals 160% STR to an opponent",
    },
    "sword": {
        "slug": "sword",
        "name": "Great Sword",
        "role": "carry",
        "stat_type": "str",
        "base_modifier": 0.55,
        "wp_cost": 100,
        "target_type": "all_enemies",
        "description": "Deals 55% STR to all opponents (Cleave)",
    },
    "scythe": {
        "slug": "scythe",
        "name": "Culling Scythe",
        "role": "carry",
        "stat_type": "str",
        "base_modifier": 1.70,
        "wp_cost": 140,
        "target_type": "single",
        "description": "Deals 170% STR to an opponent",
    },
    "axe": {
        "slug": "axe",
        "name": "Glacial Axe",
        "role": "disruptor",
        "stat_type": "str",
        "base_modifier": 1.50,
        "wp_cost": 160,
        "buff": "freeze",
        "target_type": "single",
        "description": "Deals 150% STR and freezes target next turn",
    },
    "hstaff": {
        "slug": "hstaff",
        "name": "Healing Staff",
        "role": "healer",
        "stat_type": "mag",
        "base_modifier": 1.60,
        "wp_cost": 150,
        "target_type": "lowest_ally",
        "description": "Heals 160% MAG to lowest health ally (can overheal)",
    },
    "orb": {
        "slug": "orb",
        "name": "Orb of Potency",
        "role": "carry",
        "stat_type": "mag",
        "base_modifier": 1.60,
        "wp_cost": 130,
        "target_type": "single",
        "description": "Deals 160% MAG to an opponent",
    },
    "fstaff": {
        "slug": "fstaff",
        "name": "Flame Staff",
        "role": "carry",
        "stat_type": "mag",
        "base_modifier": 1.20,
        "wp_cost": 130,
        "buff": "flame",
        "target_type": "single",
        "description": "Deals 120% MAG and applies Flame debuff",
    },
    "vstaff": {
        "slug": "vstaff",
        "name": "Vampiric Staff",
        "role": "carry",
        "stat_type": "mag",
        "base_modifier": 1.30,
        "wp_cost": 120,
        "target_type": "single",
        "description": "Deals 130% MAG with Lifesteal",
    },
    "dagger": {
        "slug": "dagger",
        "name": "Poison Dagger",
        "role": "disruptor",
        "stat_type": "mag",
        "base_modifier": 1.10,
        "wp_cost": 110,
        "buff": "poison",
        "target_type": "single",
        "description": "Deals 110% MAG and applies Poison true damage",
    },
    "crune": {
        "slug": "crune",
        "name": "Rune of Celebration",
        "role": "tank",
        "stat_type": "utility",
        "base_modifier": 0.0,
        "wp_cost": 120,
        "buff": "celeb",
        "target_type": "self",
        "description": "Celebration end-of-turn HP & WP regen",
    },
}


def normalize_weapon_slug(raw_name_or_slug: str) -> str:
    """Resolve weapon alias or full name to canonical slug."""
    s = str(raw_name_or_slug).lower().strip()
    s_clean = s.replace("'", "").replace("-", " ")
    mapping = {
        "shield": "shield",
        "defenders aegis": "shield",
        "defender's aegis": "shield",
        "aegis": "shield",
        "banner": "banner",
        "vanguards banner": "banner",
        "vanguard's banner": "banner",
        "bow": "bow",
        "sword": "sword",
        "great sword": "sword",
        "greatsword": "sword",
        "gsword": "sword",
        "scythe": "scythe",
        "culling scythe": "scythe",
        "axe": "axe",
        "glacial axe": "axe",
        "hstaff": "hstaff",
        "healing staff": "hstaff",
        "heal staff": "hstaff",
        "healstaff": "hstaff",
        "orb": "orb",
        "orb of potency": "orb",
        "potency orb": "orb",
        "fstaff": "fstaff",
        "flame staff": "fstaff",
        "fire staff": "fstaff",
        "vstaff": "vstaff",
        "vampiric staff": "vstaff",
        "vamp staff": "vstaff",
        "dagger": "dagger",
        "pd": "dagger",
        "poison dagger": "dagger",
        "crune": "crune",
        "rune of celebration": "crune",
    }
    for k, v in mapping.items():
        if k in s_clean:
            return v
    return s_clean.replace(" ", "")


def extract_dex_stats(animal: Any) -> dict[str, int]:
    """Extract normalized dex_stats dictionary [hp, str, pr, wp, mag, mr]."""
    if hasattr(animal, "stats_dict"):
        return animal.stats_dict
    if hasattr(animal, "dex_stats"):
        ds = animal.dex_stats
        if isinstance(ds, dict):
            return {k.lower(): int(v) for k, v in ds.items()}
        if isinstance(ds, (list, tuple)):
            names = ("hp", "str", "pr", "wp", "mag", "mr")
            return {names[i]: int(ds[i]) for i in range(min(len(names), len(ds)))}
    if isinstance(animal, Mapping):
        if "stats_dict" in animal:
            return animal["stats_dict"]
        if "dex_stats" in animal:
            ds = animal["dex_stats"]
            if isinstance(ds, dict):
                return {k.lower(): int(v) for k, v in ds.items()}
            names = ("hp", "str", "pr", "wp", "mag", "mr")
            return {names[i]: int(ds[i]) for i in range(min(len(names), len(ds)))}
        if "hp" in animal and "str" in animal:
            return {k: int(animal[k]) for k in ("hp", "str", "pr", "wp", "mag", "mr") if k in animal}
    # Look up by name
    name = getattr(animal, "name", None) or (animal.get("name") if isinstance(animal, Mapping) else str(animal))
    name_clean = str(name).lower().strip()
    if name_clean in KNOWN_ANIMAL_DEX:
        return dict(KNOWN_ANIMAL_DEX[name_clean])
    for k, v in KNOWN_ANIMAL_DEX.items():
        if k in name_clean:
            return dict(v)
    return {"hp": 5, "str": 5, "pr": 2, "wp": 3, "mag": 5, "mr": 2}


def get_weapon_spec(weapon: Any) -> dict[str, Any]:
    """Retrieve weapon spec mapping from string, object, or dict."""
    if weapon is None:
        return {
            "slug": "fists",
            "name": "Fists",
            "role": "unarmed",
            "stat_type": "str",
            "base_modifier": 1.0,
            "wp_cost": 0,
            "target_type": "single",
        }
    slug_raw = getattr(weapon, "slug", "")
    if not slug_raw:
        slug_raw = getattr(weapon, "weapon_name", "") or getattr(weapon, "name", "")
    if not slug_raw and isinstance(weapon, Mapping):
        slug_raw = weapon.get("slug", "") or weapon.get("weapon_name", "") or weapon.get("name", "")
    if not slug_raw:
        slug_raw = str(weapon)

    slug = normalize_weapon_slug(slug_raw)
    spec = dict(WEAPON_SPECS.get(slug, {
        "slug": slug,
        "name": slug.capitalize(),
        "role": "carry",
        "stat_type": "str",
        "base_modifier": 1.0,
        "wp_cost": 100,
        "target_type": "single",
    }))

    # Adjust for quality if available
    quality_val = getattr(weapon, "quality_val", None)
    if quality_val is None and isinstance(weapon, Mapping):
        quality_val = weapon.get("quality_val") or weapon.get("quality")
    if quality_val is not None:
        try:
            q = float(quality_val)
            # Higher quality reduces WP cost and increases damage modifier
            q_factor = 0.85 + 0.15 * (q / 100.0)
            spec["base_modifier"] = round(spec["base_modifier"] * q_factor, 3)
            cost_factor = 1.25 - 0.25 * (q / 100.0)
            spec["wp_cost"] = max(10, int(round(spec["wp_cost"] * cost_factor)))
            spec["quality_val"] = q
        except (ValueError, TypeError):
            pass

    return spec


@dataclass
class PetEvaluation:
    """Evaluation metrics for a single pet + weapon slot."""
    animal_name: str
    weapon_name: str
    weapon_slug: str
    role: str
    level: int
    hp: int
    wp: int
    str: int
    mag: int
    ehp_physical: float
    ehp_magical: float
    ehp_avg: float
    action_damage: float
    sustained_dps: float
    turns_solvent: float
    is_solvent: bool
    is_pairing_valid: bool
    invalid_reason: Optional[str] = None


@dataclass
class CandidateEvaluation:
    """Comprehensive analytical evaluation of a candidate team."""
    is_valid: bool
    score: float
    frontline_ehp: float
    total_team_ehp: float
    sustained_dps: float
    wp_solvent: bool
    solvency_ratio: float
    has_tank: bool
    has_carry: bool
    has_healer: bool
    has_banner: bool
    reasons: list[str] = field(default_factory=list)
    synergies: list[str] = field(default_factory=list)
    pet_evaluations: list[PetEvaluation] = field(default_factory=list)


def evaluate_candidate(
    animals: Sequence[Any],
    weapons: Sequence[Any],
    level: int = 50,
) -> CandidateEvaluation:
    """
    Perform fast analytical heuristic scoring on a candidate (3 animals + 3 weapons).

    Evaluation Criteria:
      1. Effective HP (EHP) across frontline/tank (Position 0).
      2. Theoretical sustained DPS output across 8 turns.
      3. WP solvency: verifies weapons don't run dry on WP before turn 8.
      4. Role archetype validation: at least 1 tank/disruptor (Shield/Banner/High EHP)
         and at least 1 offensive carry.
      5. Discard invalid pairings (e.g. pure STR weapons on pure MAG pets).
    """
    reasons: list[str] = []
    synergies: list[str] = []
    pet_evals: list[PetEvaluation] = []

    if len(animals) != 3 or len(weapons) != 3:
        return CandidateEvaluation(
            is_valid=False,
            score=-1.0,
            frontline_ehp=0.0,
            total_team_ehp=0.0,
            sustained_dps=0.0,
            wp_solvent=False,
            solvency_ratio=0.0,
            has_tank=False,
            has_carry=False,
            has_healer=False,
            has_banner=False,
            reasons=["Candidate must have exactly 3 animals and 3 weapons"],
        )

    has_tank = False
    has_carry = False
    has_healer = False
    has_banner = False
    any_pairing_invalid = False

    total_team_ehp = 0.0
    total_sustained_dps = 0.0
    min_solvency_ratio = 1.0
    team_wp_solvent = True

    # Check for team-wide buffs first (e.g., Vanguard's Banner in any slot)
    weapon_specs = [get_weapon_spec(w) for w in weapons]
    team_has_banner = any(w["slug"] == "banner" for w in weapon_specs)
    if team_has_banner:
        has_banner = True
        has_tank = True  # Banner acts as team buffer/disruptor
        synergies.append("Vanguard's Banner provides team-wide Attack Up (+25% damage)")

    for pos in range(3):
        animal = animals[pos]
        weapon = weapons[pos]
        w_spec = weapon_specs[pos]

        animal_name = getattr(animal, "name", None) or (
            animal.get("name") if isinstance(animal, Mapping) else str(animal)
        )
        raw_level = getattr(animal, "level", None)
        if raw_level is None and isinstance(animal, Mapping):
            raw_level = animal.get("level")
        if raw_level is not None and int(raw_level) > 1:
            animal_level = int(raw_level)
        else:
            animal_level = level

        dex = extract_dex_stats(animal)

        # Extract passives from weapon if present
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

        stats: PetStats = calculate_pet_stats(animal_level, dex, weapon_stat_boosts=passives)

        ehp_avg = (stats.ehp_physical + stats.ehp_magical) / 2.0
        total_team_ehp += ehp_avg

        # Check Invalid Pairings
        is_pairing_valid = True
        invalid_reason = None
        str_bias = dex.get("str", 1)
        mag_bias = dex.get("mag", 1)

        # Pure STR pet equipped with pure MAG weapon
        if w_spec["stat_type"] == "mag" and str_bias >= 8 and mag_bias <= 2:
            is_pairing_valid = False
            invalid_reason = f"Pure STR animal '{animal_name}' (STR {str_bias}, MAG {mag_bias}) paired with MAG weapon '{w_spec['name']}'"
            any_pairing_invalid = True
            reasons.append(invalid_reason)

        # Pure MAG pet equipped with pure STR weapon
        elif w_spec["stat_type"] == "str" and mag_bias >= 8 and str_bias <= 2:
            is_pairing_valid = False
            invalid_reason = f"Pure MAG animal '{animal_name}' (MAG {mag_bias}, STR {str_bias}) paired with STR weapon '{w_spec['name']}'"
            any_pairing_invalid = True
            reasons.append(invalid_reason)

        # WP Solvency Calculation
        wp_cost = w_spec["wp_cost"]
        wp_regen = passives.get("wgen", 0.0) * 50.0  # Energize passive
        if w_spec["slug"] == "crune":
            wp_regen += stats.imr * 0.5  # Celebration WP regen
        net_wp_drain = max(0.0, wp_cost - wp_regen)

        if net_wp_drain == 0.0:
            turns_solvent = 999.0
            solvency_ratio = 1.0
            is_solvent = True
        else:
            turns_solvent = stats.wp / net_wp_drain
            solvency_ratio = min(1.0, turns_solvent / 8.0)
            is_solvent = turns_solvent >= 8.0

        if not is_solvent:
            team_wp_solvent = False
        if solvency_ratio < min_solvency_ratio:
            min_solvency_ratio = solvency_ratio

        # Theoretical Sustained DPS Output Calculation
        relevant_stat = stats.str if w_spec["stat_type"] == "str" else stats.mag
        mod = w_spec["base_modifier"]

        # Bonus modifiers (Crit, Attack Up)
        pos_multiplier = 1.0
        if team_has_banner:
            pos_multiplier += 0.25
        if "crit" in passives:
            pos_multiplier += 0.20  # Average expected crit boost

        # Multi-target Cleave (Great Sword hits 3 targets)
        target_multiplier = 3.0 if w_spec["target_type"] == "all_enemies" else 1.0

        action_damage = relevant_stat * mod * pos_multiplier * target_multiplier
        unarmed_basic_attack = stats.str * 1.0 * pos_multiplier

        # 8-turn sustained DPS accounting for WP dry turns
        sustainable_turns = min(8.0, turns_solvent)
        dry_turns = max(0.0, 8.0 - sustainable_turns)

        if w_spec["role"] in ("tank", "buffer"):
            # Shields and Banners do not deal direct weapon attack damage
            dps = 0.0
        elif w_spec["role"] == "healer":
            # Healer output sustains team survival rather than enemy damage
            dps = 0.0
            has_healer = True
        else:
            total_8_turn_damage = (sustainable_turns * action_damage) + (dry_turns * unarmed_basic_attack)
            dps = total_8_turn_damage / 8.0
            total_sustained_dps += dps

        # Role Archetype Identification
        is_carry_stat = (w_spec["stat_type"] == "str" and str_bias >= 5) or (
            w_spec["stat_type"] == "mag" and mag_bias >= 5
        )
        if pos == 0:
            # Position 0 Frontline / Tank check:
            # Must have a Shield/Banner/CRune, or be a natural high EHP tank (>=3500 EHP or tank dex >= 14)
            tank_dex_sum = dex.get("hp", 0) + dex.get("pr", 0) + dex.get("mr", 0)
            if w_spec["slug"] in ("shield", "banner", "crune"):
                has_tank = True
            elif ehp_avg >= 3500.0 or (tank_dex_sum >= 14 and ehp_avg >= 2800.0):
                has_tank = True
        else:
            if w_spec["slug"] in ("shield", "banner"):
                has_tank = True

        if w_spec["role"] in ("carry", "disruptor") and (is_carry_stat or action_damage >= 150.0):
            has_carry = True

        pet_evals.append(
            PetEvaluation(
                animal_name=animal_name,
                weapon_name=w_spec["name"],
                weapon_slug=w_spec["slug"],
                role=w_spec["role"],
                level=animal_level,
                hp=stats.hp,
                wp=stats.wp,
                str=stats.str,
                mag=stats.mag,
                ehp_physical=stats.ehp_physical,
                ehp_magical=stats.ehp_magical,
                ehp_avg=ehp_avg,
                action_damage=round(action_damage, 1),
                sustained_dps=round(dps, 1),
                turns_solvent=round(turns_solvent, 1),
                is_solvent=is_solvent,
                is_pairing_valid=is_pairing_valid,
                invalid_reason=invalid_reason,
            )
        )

    # Frontline EHP (Position 0)
    frontline_raw_ehp = pet_evals[0].ehp_avg
    frontline_has_shield = weapon_specs[0]["slug"] == "shield"
    # Shield Taunt buff reduces incoming damage by 50%, effectively doubling EHP
    frontline_effective_ehp = frontline_raw_ehp * (2.0 if frontline_has_shield else 1.0)

    # Detect Synergies
    if frontline_has_shield:
        synergies.append(
            f"{pet_evals[0].animal_name} with Defender's Aegis draws fire with Taunt (50% damage reduction)"
        )
    if frontline_has_shield and has_healer:
        healer_pet = next((p for p in pet_evals if p.role == "healer"), None)
        if healer_pet:
            synergies.append(
                f"{healer_pet.animal_name} Healing Staff overheals {pet_evals[0].animal_name}'s high frontline EHP"
            )
    if has_carry:
        carry_pet = next((p for p in pet_evals if p.role in ("carry", "disruptor") and p.sustained_dps > 0), None)
        if carry_pet:
            synergies.append(
                f"{carry_pet.animal_name} equipped with {carry_pet.weapon_name} delivers sustained DPS ({carry_pet.sustained_dps:.0f} DPS)"
            )
    if any(p.weapon_slug == "sword" for p in pet_evals) and team_has_banner:
        synergies.append("Great Sword cleave amplified by Vanguard's Banner Attack Up")

    # Archetype Validation
    if not has_tank:
        reasons.append("Missing Tank/Disruptor: team needs at least 1 Defender's Aegis, Vanguard's Banner, or High EHP Frontline (>=1800)")
    if not has_carry:
        reasons.append("Missing Offensive Carry: team needs at least 1 offensive weapon matched with high stat carry (>=350 action damage)")
    if not team_wp_solvent:
        reasons.append(f"WP Insolvent: weapon runs dry before turn 8 (solvency ratio {min_solvency_ratio:.1%})")

    is_valid = (not any_pairing_invalid) and has_tank and has_carry

    # Calculate Heuristic Composite Score
    if not is_valid:
        score = -1.0
    else:
        # Heuristic weights:
        # - DPS contributes directly to killing enemies
        # - Frontline EHP ensures the team survives to deal damage
        # - Solvency ratio penalizes running dry before turn 8
        # - Synergy bonuses reward archetype cohesion
        synergy_score = len(synergies) * 150.0
        solvency_score = 500.0 * min_solvency_ratio

        score = (
            (total_sustained_dps * 1.2)
            + (frontline_effective_ehp / 8.0)
            + (total_team_ehp / 25.0)
            + solvency_score
            + synergy_score
        )

    return CandidateEvaluation(
        is_valid=is_valid,
        score=round(score, 2),
        frontline_ehp=round(frontline_effective_ehp, 1),
        total_team_ehp=round(total_team_ehp, 1),
        sustained_dps=round(total_sustained_dps, 1),
        wp_solvent=team_wp_solvent,
        solvency_ratio=round(min_solvency_ratio, 3),
        has_tank=has_tank,
        has_carry=has_carry,
        has_healer=has_healer,
        has_banner=has_banner,
        reasons=reasons,
        synergies=synergies,
        pet_evaluations=pet_evals,
    )
