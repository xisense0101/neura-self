"""
OwO 24-Turn Battle State Machine Engine.

Implements the three-phase state machine documented at https://owo.bwep.net/battleSystem/basics:
  1. Pre-Phase:
     - canAttack evaluated (dead and frozen pets cannot act).
     - Start-of-turn weapons (Defender's Aegis / Shield, Vanguard's Banner) cast buffs if conditions met.
  2. Main-Phase:
     - Strict alternating action order by position: A1 -> B1 -> A2 -> B2 -> A3 -> B3.
     - Dead or incapacitated pets have their turn skipped without altering the sequence.
     - Single-target attacks prioritize enemy taunters; otherwise target matching position or first alive enemy.
     - Damage is resolved via the 6-stage damage pipeline.
  3. End-Phase:
     - Reverse-order resolution of post-turn buffs/debuffs (Poison, Flame, Celebration).
     - Duration countdown on other buffs and debuffs; removal of just_created tags.
     - Passives proc: Hgen (health regen) and Wgen (WP regen).
     - Cleanup of expired buffs (duration <= 0 on alive pets).

Deterministic replayability is guaranteed via `random.Random(seed)`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence

from owo_strategy.simulator.damage_pipeline import DamageResult, calculate_damage_pipeline
from owo_strategy.simulator.formulas import (
    EffectiveResistance,
    PetStats,
    calculate_effective_resistance,
    calculate_pet_stats,
)


@dataclass
class Buff:
    """Represents an active buff or debuff on a pet."""
    slug: str
    duration: int
    value: float = 0.0
    caster: Optional["Pet"] = None
    just_created: bool = True
    stacks: int = 1

    def copy(self) -> Buff:
        return Buff(
            slug=self.slug,
            duration=self.duration,
            value=self.value,
            caster=self.caster,
            just_created=self.just_created,
            stacks=self.stacks,
        )


@dataclass
class Weapon:
    """Represents a weapon equipped by a pet."""
    slug: str
    name: str = ""
    stat_modifier: float = 1.0
    wp_cost: int = 0
    damage_type: str = "physical"  # "physical", "magical", "heal", "buff"
    target_type: str = "single"  # "single", "all_enemies", "all_allies", "self"
    passives: dict[str, float] = field(default_factory=dict)
    buff_slugs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.slug.capitalize()


@dataclass
class Pet:
    """Represents a pet in battle."""
    name: str
    position: int  # 0, 1, or 2
    team_id: str  # "team_a" or "team_b"
    level: int
    max_hp: int
    current_hp: float
    max_wp: int
    current_wp: float
    str: int
    mag: int
    ipr: int
    imr: int
    pr_percent: int
    pr_ratio: float
    mr_percent: int
    mr_ratio: float
    weapon: Optional[Weapon] = None
    passives: dict[str, float] = field(default_factory=dict)
    buffs: list[Buff] = field(default_factory=list)
    can_attack: bool = True

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0

    @property
    def is_dead(self) -> bool:
        return self.current_hp <= 0

    def has_buff(self, slug: str) -> bool:
        return any(b.slug == slug and b.duration > 0 for b in self.buffs)

    def get_buff(self, slug: str) -> Optional[Buff]:
        for b in self.buffs:
            if b.slug == slug and b.duration > 0:
                return b
        return None

    def add_buff(self, buff: Buff) -> None:
        # Check if buff cannot stack (e.g. attup, taunt - refreshes duration or upgrades)
        existing = self.get_buff(buff.slug)
        if existing is not None:
            # Refresh duration and value if new one is higher or equal
            existing.duration = max(existing.duration, buff.duration)
            existing.value = max(existing.value, buff.value)
            existing.caster = buff.caster
            existing.just_created = True
        else:
            self.buffs.append(buff)

    def remove_buff(self, slug: str) -> None:
        self.buffs = [b for b in self.buffs if b.slug != slug]

    def take_damage(self, amount: float, damage_type: str = "physical") -> float:
        actual_damage = max(0.0, float(amount))
        self.current_hp = max(0.0, self.current_hp - actual_damage)
        return actual_damage

    def heal(self, amount: float) -> float:
        if self.is_dead:
            return 0.0
        heal_amt = max(0.0, float(amount))
        # Mortality debuff check
        mort = self.get_buff("mort")
        if mort:
            heal_amt *= max(0.0, 1.0 - mort.value)
        # Sprout passive check
        if "sprout" in self.passives:
            heal_amt += heal_amt * self.passives["sprout"]
        old_hp = self.current_hp
        self.current_hp = min(float(self.max_hp), self.current_hp + heal_amt)
        return self.current_hp - old_hp

    def replenish(self, amount: float) -> float:
        if self.is_dead:
            return 0.0
        replenish_amt = max(0.0, float(amount))
        old_wp = self.current_wp
        self.current_wp = min(float(self.max_wp), self.current_wp + replenish_amt)
        return self.current_wp - old_wp


@dataclass
class Team:
    """Represents a team of 3 pets."""
    team_id: str  # "team_a" or "team_b"
    name: str
    pets: list[Pet] = field(default_factory=list)

    @property
    def is_wiped(self) -> bool:
        return all(p.is_dead for p in self.pets)

    @property
    def alive_pets(self) -> list[Pet]:
        return [p for p in self.pets if p.is_alive]

    @property
    def total_hp(self) -> float:
        return sum(p.current_hp for p in self.pets)

    @property
    def max_total_hp(self) -> float:
        return sum(p.max_hp for p in self.pets)

    def get_taunter(self) -> Optional[Pet]:
        """Return the first alive pet with an active Taunt buff."""
        for pet in self.pets:
            if pet.is_alive and pet.has_buff("taunt"):
                return pet
        return None

    def get_target(self, preferred_pos: int) -> Optional[Pet]:
        """
        Determine target on this team:
          1. Taunting pet (if any).
          2. Pet at matching position (if alive).
          3. First alive pet by position order (0, 1, 2).
        """
        taunter = self.get_taunter()
        if taunter is not None:
            return taunter

        if preferred_pos < len(self.pets) and self.pets[preferred_pos].is_alive:
            return self.pets[preferred_pos]

        for pet in self.pets:
            if pet.is_alive:
                return pet
        return None


@dataclass
class BattleEvent:
    """Represents a recorded event during the battle."""
    turn: int
    phase: str  # "pre", "main", "end"
    actor: Optional[str] = None
    target: Optional[str] = None
    action: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnLog:
    """Log record for a single turn."""
    turn: int
    events: list[BattleEvent] = field(default_factory=list)
    team_a_hp: list[float] = field(default_factory=list)
    team_b_hp: list[float] = field(default_factory=list)


@dataclass
class BattleResult:
    """Overall outcome of a 24-turn battle simulation."""
    winner: str  # "team_a", "team_b", "draw"
    total_turns: int
    team_a_survivors: int
    team_b_survivors: int
    team_a_hp_remaining: float
    team_b_hp_remaining: float
    turn_logs: list[TurnLog] = field(default_factory=list)


def create_pet(
    name: str,
    dex_stats: dict[str, int],
    level: int = 50,
    weapon: Optional[Weapon] = None,
    passives: Optional[dict[str, float]] = None,
    position: int = 0,
    team_id: str = "team_a",
) -> Pet:
    """Factory helper to build a fully initialized Pet."""
    weapon_passives: dict[str, float] = {}
    if weapon and weapon.passives:
        weapon_passives.update(weapon.passives)

    stats = calculate_pet_stats(level, dex_stats, weapon_stat_boosts=weapon_passives)

    all_passives: dict[str, float] = {}
    if passives:
        all_passives.update(passives)
    all_passives.update(weapon_passives)

    return Pet(
        name=name,
        position=position,
        team_id=team_id,
        level=level,
        max_hp=stats.hp,
        current_hp=float(stats.hp),
        max_wp=stats.wp,
        current_wp=float(stats.wp),
        str=stats.str,
        mag=stats.mag,
        ipr=stats.ipr,
        imr=stats.imr,
        pr_percent=stats.pr_percent,
        pr_ratio=stats.pr_ratio,
        mr_percent=stats.mr_percent,
        mr_ratio=stats.mr_ratio,
        weapon=weapon,
        passives=all_passives,
    )


class BattleEngine:
    """
    Simulates battles using the 24-turn Basement state machine.
    Deterministic replayability is guaranteed through random.Random(seed).
    """

    def __init__(
        self,
        team_a: Team,
        team_b: Team,
        seed: Optional[int] = None,
        deterministic_damage: bool = False,
    ) -> None:
        self.team_a = team_a
        self.team_b = team_b
        self.seed = seed
        self.rng = random.Random(seed)
        self.deterministic_damage = deterministic_damage
        self.current_turn = 0
        self.turn_logs: list[TurnLog] = []

    def run_battle(self, max_turns: int = 24) -> BattleResult:
        """Execute full battle up to max_turns (default 24)."""
        for turn_idx in range(1, max_turns + 1):
            self.current_turn = turn_idx
            turn_log = self.run_turn(turn_idx)
            self.turn_logs.append(turn_log)

            if self.team_a.is_wiped or self.team_b.is_wiped:
                break

        # Determine winner
        if self.team_b.is_wiped and not self.team_a.is_wiped:
            winner = "team_a"
        elif self.team_a.is_wiped and not self.team_b.is_wiped:
            winner = "team_b"
        elif self.team_a.is_wiped and self.team_b.is_wiped:
            winner = "draw"
        else:
            # Turn limit reached: highest total remaining HP wins
            if self.team_a.total_hp > self.team_b.total_hp:
                winner = "team_a"
            elif self.team_b.total_hp > self.team_a.total_hp:
                winner = "team_b"
            else:
                winner = "draw"

        return BattleResult(
            winner=winner,
            total_turns=self.current_turn,
            team_a_survivors=len(self.team_a.alive_pets),
            team_b_survivors=len(self.team_b.alive_pets),
            team_a_hp_remaining=self.team_a.total_hp,
            team_b_hp_remaining=self.team_b.total_hp,
            turn_logs=self.turn_logs,
        )

    def run_turn(self, turn_number: int) -> TurnLog:
        """Run all 3 phases of a single turn."""
        self.current_turn = turn_number
        turn_log = TurnLog(turn=turn_number)

        # 1. Pre-Phase
        self._execute_pre_phase(turn_log)

        # 2. Main-Phase (only if both teams have living pets)
        if not self.team_a.is_wiped and not self.team_b.is_wiped:
            self._execute_main_phase(turn_log)

        # 3. End-Phase
        self._execute_end_phase(turn_log)

        # Record HP snapshot
        turn_log.team_a_hp = [p.current_hp for p in self.team_a.pets]
        turn_log.team_b_hp = [p.current_hp for p in self.team_b.pets]

        return turn_log

    def _execute_pre_phase(self, turn_log: TurnLog) -> None:
        """
        Pre-Phase:
          - canAttack checked: dead pets and pets with freeze debuff cannot act.
          - Pets holding Shield or Banner act:
            * Shield: cast Taunt (duration 2) if no active Taunt buff.
            * Banner: cast AttackUp (duration 2) to all allies if no active AttackUp
              or if existing AttackUp expires after this turn (duration <= 1).
        """
        all_pets: list[Pet] = []
        for pos in range(3):
            if pos < len(self.team_a.pets):
                all_pets.append(self.team_a.pets[pos])
            if pos < len(self.team_b.pets):
                all_pets.append(self.team_b.pets[pos])

        # Step 1: canAttack Check
        for pet in all_pets:
            if pet.is_dead:
                pet.can_attack = False
                continue

            freeze = pet.get_buff("freeze")
            if freeze:
                pet.can_attack = False
                freeze.duration -= 1
                turn_log.events.append(
                    BattleEvent(
                        turn=self.current_turn,
                        phase="pre",
                        actor=pet.name,
                        action="frozen",
                        details={"remaining_freeze_duration": freeze.duration},
                    )
                )
                if freeze.duration <= 0:
                    pet.buffs.remove(freeze)
            else:
                pet.can_attack = True

        # Step 2: Start-of-Turn Shield and Banner actions
        for pet in all_pets:
            if not pet.is_alive or not pet.can_attack:
                continue

            if not pet.weapon:
                continue

            weapon = pet.weapon
            team = self.team_a if pet.team_id == "team_a" else self.team_b

            # Shield logic: cast Taunt if no active Taunt buff
            if weapon.slug == "shield":
                if not pet.has_buff("taunt") and pet.current_wp >= weapon.wp_cost:
                    pet.current_wp -= weapon.wp_cost
                    taunt_buff = Buff(
                        slug="taunt",
                        duration=2,
                        value=0.5,  # 50% damage reduction from Taunt
                        caster=pet,
                        just_created=True,
                    )
                    pet.add_buff(taunt_buff)
                    turn_log.events.append(
                        BattleEvent(
                            turn=self.current_turn,
                            phase="pre",
                            actor=pet.name,
                            action="cast_shield",
                            details={"buff": "taunt", "duration": 2, "wp_cost": weapon.wp_cost},
                        )
                    )

            # Banner logic: cast AttackUp to all allies if no AttackUp or expires after this turn
            elif weapon.slug == "banner":
                current_attup = pet.get_buff("attup")
                should_cast = (current_attup is None) or (current_attup.duration <= 1)
                if should_cast and pet.current_wp >= weapon.wp_cost:
                    pet.current_wp -= weapon.wp_cost
                    for ally in team.alive_pets:
                        ally.add_buff(
                            Buff(
                                slug="attup",
                                duration=2,
                                value=0.25,  # 25% Attack Up bonus
                                caster=pet,
                                just_created=True,
                            )
                        )
                    turn_log.events.append(
                        BattleEvent(
                            turn=self.current_turn,
                            phase="pre",
                            actor=pet.name,
                            action="cast_banner",
                            details={"buff": "attup", "targets": [a.name for a in team.alive_pets]},
                        )
                    )

    def _execute_main_phase(self, turn_log: TurnLog) -> None:
        """
        Main-Phase:
          Strict alternating turns by position: A1 -> B1 -> A2 -> B2 -> A3 -> B3.
          If a pet is dead or canAttack is false, its turn is skipped.
        """
        turn_order: list[tuple[Team, Team, int]] = [
            (self.team_a, self.team_b, 0),  # A1
            (self.team_b, self.team_a, 0),  # B1
            (self.team_a, self.team_b, 1),  # A2
            (self.team_b, self.team_a, 1),  # B2
            (self.team_a, self.team_b, 2),  # A3
            (self.team_b, self.team_a, 2),  # B3
        ]

        for acting_team, defending_team, pos in turn_order:
            if defending_team.is_wiped or acting_team.is_wiped:
                break

            if pos >= len(acting_team.pets):
                continue

            actor = acting_team.pets[pos]

            # Dead or incapacitated pets skip action
            if actor.is_dead or not actor.can_attack:
                continue

            self._execute_pet_action(actor, acting_team, defending_team, turn_log)

    def _execute_pet_action(
        self, actor: Pet, acting_team: Team, defending_team: Team, turn_log: TurnLog
    ) -> None:
        """Execute a single pet's action during Main-Phase."""
        weapon = actor.weapon

        # Start-of-turn weapons (Shield, Banner) have already acted in Pre-Phase
        if weapon and weapon.slug in ("shield", "banner"):
            # Shields / Banners do not perform a standard attack in main-phase
            return

        # Determine target(s)
        if weapon and weapon.target_type == "all_enemies":
            targets = defending_team.alive_pets
        else:
            single_target = defending_team.get_target(actor.position)
            targets = [single_target] if single_target else []

        if not targets:
            return

        # Check WP cost: if insufficient, fallback to basic attack (Fists)
        is_using_weapon = False
        if weapon and actor.current_wp >= weapon.wp_cost:
            actor.current_wp -= weapon.wp_cost
            is_using_weapon = True
            mod = weapon.stat_modifier
            dmg_type = weapon.damage_type
        else:
            # Basic physical attack (Fists): 100% STR, 0 WP cost
            mod = 1.0
            dmg_type = "physical"

        for target in targets:
            if target.is_dead:
                continue

            stat = actor.str if dmg_type == "physical" else actor.mag

            # Stage 3 Positive Modifiers
            pos_mods: list[float] = []
            attup = actor.get_buff("attup")
            if attup:
                pos_mods.append(attup.value)
            # Resonance passive: +10% per buff on attacker
            if "resonance" in actor.passives:
                buff_count = len([b for b in actor.buffs if b.duration > 0])
                if buff_count > 0:
                    pos_mods.append(actor.passives["resonance"] * buff_count)
            # Enrage passive: extra damage per 10% missing HP
            if "enrage" in actor.passives:
                missing_ratio = (actor.max_hp - actor.current_hp) / actor.max_hp
                enrage_stacks = int(missing_ratio / 0.1)
                if enrage_stacks > 0:
                    pos_mods.append(actor.passives["enrage"] * enrage_stacks)

            # Stage 4 Negative Modifiers
            neg_mods: list[float] = []
            taunt = target.get_buff("taunt")
            if taunt:
                neg_mods.append(taunt.value)
            defup = target.get_buff("defup")
            if defup:
                neg_mods.append(defup.value)
            # Resonance passive on defender: -10% per debuff on defender
            if "resonance" in target.passives:
                debuff_count = len([b for b in target.buffs if b.slug in ("poison", "flame", "freeze", "mort", "leech", "stinky")])
                if debuff_count > 0:
                    neg_mods.append(target.passives["resonance"] * debuff_count)

            # Stage 5 Resistance
            res = target.pr_percent if dmg_type == "physical" else target.mr_percent

            # Stage 6 Redirect Modifiers (Safeguard, Tether)
            red_mods: list[tuple[str, float]] = []
            if "sg" in target.passives and target.current_wp > 0:
                red_mods.append(("sg", target.passives["sg"]))
            tether = target.get_buff("tether")
            if tether and tether.caster and tether.caster.is_alive:
                red_mods.append(("tether", tether.value))

            damage_res = calculate_damage_pipeline(
                relevant_stat=stat,
                weapon_modifier=mod,
                variance=0 if self.deterministic_damage else None,
                rng=None if self.deterministic_damage else self.rng,
                deterministic=self.deterministic_damage,
                positive_modifiers=pos_mods,
                negative_modifiers=neg_mods,
                res_percent=res,
                redirect_modifiers=red_mods,
            )

            # Apply final damage to target
            target.take_damage(damage_res.final_damage, dmg_type)

            # Handle Safeguard WP consumption
            if "sg" in damage_res.redirected_breakdown:
                absorbed = damage_res.redirected_breakdown["sg"]
                target.current_wp = max(0.0, target.current_wp - absorbed)

            # Handle Tether damage redirection
            if "tether" in damage_res.redirected_breakdown and tether and tether.caster:
                tether_damage = damage_res.redirected_breakdown["tether"]
                tether.caster.take_damage(tether_damage, dmg_type)

            # Lifesteal passive (ls)
            if "ls" in actor.passives and actor.is_alive:
                ls_amt = damage_res.final_damage * actor.passives["ls"]
                actor.heal(ls_amt)

            # Thorns passive (th)
            if "th" in target.passives and actor.is_alive:
                th_amt = damage_res.final_damage * target.passives["th"]
                actor.take_damage(th_amt, "true")

            turn_log.events.append(
                BattleEvent(
                    turn=self.current_turn,
                    phase="main",
                    actor=actor.name,
                    target=target.name,
                    action="attack",
                    details={
                        "weapon": weapon.slug if is_using_weapon and weapon else "fists",
                        "damage": damage_res.final_damage,
                        "pipeline": {
                            "base": damage_res.stage1_base,
                            "pos": damage_res.stage3_positive,
                            "neg": damage_res.stage4_negative,
                            "res": damage_res.stage5_resistance,
                            "redirect": damage_res.stage6_redirect,
                        },
                    },
                )
            )

    def _execute_end_phase(self, turn_log: TurnLog) -> None:
        """
        End-Phase:
          1. Reverse-order resolution of post-turn buffs/debuffs (Poison, Flame, Celebration).
             - Reduces duration by 1.
             - Not proccing on dead pets (dead pets retain them indefinitely).
          2. Other buffs and debuffs lose duration (Taunt, AtkUp, DefUp, etc.).
             - Remove "just_created" tag.
             - Mark duration <= 0 for removal.
          3. Passives proc:
             - Hgen: heal holder.
             - Wgen: replenish holder.
          4. Cleanup of expired buffs on living pets.
        """
        all_pets: list[Pet] = self.team_a.pets + self.team_b.pets

        # Step 1: Post-turn Buffs & Debuffs in REVERSE order of reception
        for pet in all_pets:
            if pet.is_dead:
                # Dead pets do not proc post-turn debuffs and duration is never reduced
                continue

            # Iterate through buffs in reverse order (LIFO)
            for buff in reversed(pet.buffs):
                if pet.is_dead:
                    break

                if buff.slug == "poison":
                    caster_mag = buff.caster.mag if buff.caster else 100
                    poison_dmg = buff.value * caster_mag
                    pet.take_damage(poison_dmg, "true")
                    buff.duration -= 1
                    turn_log.events.append(
                        BattleEvent(
                            turn=self.current_turn,
                            phase="end",
                            actor=pet.name,
                            action="poison_damage",
                            details={"damage": poison_dmg, "remaining_duration": buff.duration},
                        )
                    )

                elif buff.slug == "flame":
                    caster_mag = buff.caster.mag if buff.caster else 100
                    flame_dmg = buff.value * caster_mag
                    pet.take_damage(flame_dmg, "magical")
                    buff.duration -= 1
                    turn_log.events.append(
                        BattleEvent(
                            turn=self.current_turn,
                            phase="end",
                            actor=pet.name,
                            action="flame_damage",
                            details={"damage": flame_dmg, "remaining_duration": buff.duration},
                        )
                    )

                elif buff.slug == "celeb":
                    # Celebration: heal value * iPR as HP, replenish value * iMR as WP
                    heal_amt = buff.value * pet.ipr
                    wp_amt = buff.value * pet.imr
                    pet.heal(heal_amt)
                    pet.replenish(wp_amt)
                    buff.duration -= 1
                    turn_log.events.append(
                        BattleEvent(
                            turn=self.current_turn,
                            phase="end",
                            actor=pet.name,
                            action="celebration",
                            details={"heal": heal_amt, "wp": wp_amt, "remaining_duration": buff.duration},
                        )
                    )

        # Step 2: Duration countdown on all other buffs & debuffs
        post_turn_slugs = {"poison", "flame", "celeb", "freeze"}
        for pet in all_pets:
            if pet.is_dead:
                continue

            for buff in pet.buffs:
                if buff.slug not in post_turn_slugs:
                    buff.just_created = False
                    buff.duration -= 1

        # Step 3: Passives proc (Hgen and Wgen)
        for pet in all_pets:
            if pet.is_dead:
                continue

            if "hgen" in pet.passives:
                hgen_rate = pet.passives["hgen"]
                heal_amount = pet.max_hp * hgen_rate if hgen_rate < 1.0 else hgen_rate
                pet.heal(heal_amount)
                turn_log.events.append(
                    BattleEvent(
                        turn=self.current_turn,
                        phase="end",
                        actor=pet.name,
                        action="hgen_heal",
                        details={"amount": heal_amount},
                    )
                )

            if "wgen" in pet.passives:
                wgen_amount = pet.passives["wgen"]
                pet.replenish(wgen_amount)
                turn_log.events.append(
                    BattleEvent(
                        turn=self.current_turn,
                        phase="end",
                        actor=pet.name,
                        action="wgen_replenish",
                        details={"amount": wgen_amount},
                    )
                )

        # Step 4: Cleanup expired buffs on living pets
        for pet in all_pets:
            if pet.is_alive:
                pet.buffs = [b for b in pet.buffs if b.duration > 0]
