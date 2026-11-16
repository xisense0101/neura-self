"""Data models and schemas for OwO Strategy Engine."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


STAT_NAMES = ("hp", "str", "pr", "wp", "mag", "mr")


@dataclass
class Animal:
    """Represents a base animal in the OwO database."""

    id: str | int
    name: str
    rank: str
    dex_stats: dict[str, int] | list[int]
    aliases: list[str] = field(default_factory=list)
    animated: bool = False

    @property
    def stats_dict(self) -> dict[str, int]:
        """Return dex stats normalized as a dictionary."""
        if isinstance(self.dex_stats, dict):
            return dict(self.dex_stats)
        if isinstance(self.dex_stats, (list, tuple)):
            return {
                name: int(self.dex_stats[i]) if i < len(self.dex_stats) else 0
                for i, name in enumerate(STAT_NAMES)
            }
        return {name: 0 for name in STAT_NAMES}

    @property
    def stats_list(self) -> list[int]:
        """Return dex stats normalized as a list [hp, str, pr, wp, mag, mr]."""
        if isinstance(self.dex_stats, (list, tuple)):
            return [int(val) for val in self.dex_stats]
        if isinstance(self.dex_stats, dict):
            return [int(self.dex_stats.get(name, 0)) for name in STAT_NAMES]
        return [0] * len(STAT_NAMES)

    @property
    def hp(self) -> int:
        return self.stats_dict.get("hp", 0)

    @property
    def str(self) -> int:
        return self.stats_dict.get("str", 0)

    @property
    def pr(self) -> int:
        return self.stats_dict.get("pr", 0)

    @property
    def wp(self) -> int:
        return self.stats_dict.get("wp", 0)

    @property
    def mag(self) -> int:
        return self.stats_dict.get("mag", 0)

    @property
    def mr(self) -> int:
        return self.stats_dict.get("mr", 0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Animal:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            rank=str(data.get("rank", "")),
            dex_stats=data.get("dex_stats", {}),
            aliases=list(data.get("aliases", [])),
            animated=bool(data.get("animated", False)),
        )


@dataclass
class Weapon:
    """Represents a weapon catalog entry."""

    id: int | str | None
    name: str
    wp_cost_range: tuple[float, float] | list[float] | None
    stat_ranges: list[dict[str, Any]]
    passive_slots: int
    description: str
    active_ability: str | dict[str, Any] | list[str] | None = None
    slug: str = ""
    aliases: list[str] = field(default_factory=list)
    buff_slugs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Weapon:
        return cls(
            id=data.get("id"),
            name=str(data.get("name", "")),
            wp_cost_range=data.get("wp_cost_range"),
            stat_ranges=list(data.get("stat_ranges", [])),
            passive_slots=int(data.get("passive_slots", 1)),
            description=str(data.get("description", "")),
            active_ability=data.get("active_ability"),
            slug=str(data.get("slug", "")),
            aliases=list(data.get("aliases", [])),
            buff_slugs=list(data.get("buff_slugs", [])),
        )


@dataclass
class Passive:
    """Represents a weapon passive ability."""

    name: str
    stat_boosts: list[dict[str, Any]]
    description: str
    effect_type: str = "passive"
    slug: str = ""
    aliases: list[str] = field(default_factory=list)
    buff_slugs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Passive:
        return cls(
            name=str(data.get("name", "")),
            stat_boosts=list(data.get("stat_boosts", [])),
            description=str(data.get("description", "")),
            effect_type=str(data.get("effect_type", "passive")),
            slug=str(data.get("slug", "")),
            aliases=list(data.get("aliases", [])),
            buff_slugs=list(data.get("buff_slugs", [])),
        )


@dataclass
class OwnedWeapon:
    """Represents an instantiated weapon owned by a player."""

    id: str
    weapon_name: str
    quality_val: float | None = None
    quality_is_exact: bool = False
    wear: str = "worn"
    stats: dict[str, Any] = field(default_factory=dict)
    passives: list[Any] = field(default_factory=list)
    raw_line: str = ""
    blueprint: str = ""
    is_locked: bool = False
    max_possible_quality: float | None = None
    is_dismantle_candidate: bool = False
    is_shard_candidate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OwnedWeapon:
        return cls(
            id=str(data.get("id", "")).upper(),
            weapon_name=str(data.get("weapon_name", "")),
            quality_val=float(data["quality_val"]) if data.get("quality_val") is not None else None,
            quality_is_exact=bool(data.get("quality_is_exact", False)),
            wear=str(data.get("wear", "worn")),
            stats=dict(data.get("stats", {})),
            passives=list(data.get("passives", [])),
            raw_line=str(data.get("raw_line", "")),
            blueprint=str(data.get("blueprint", "")),
            is_locked=bool(data.get("is_locked", False)),
            max_possible_quality=float(data["max_possible_quality"]) if data.get("max_possible_quality") is not None else None,
            is_dismantle_candidate=bool(data.get("is_dismantle_candidate", False)),
            is_shard_candidate=bool(data.get("is_shard_candidate", False)),
        )


@dataclass
class OwnedAnimal:
    """Represents an animal instance in user inventory."""

    name: str
    count: int = 1
    level: int = 1
    equipped_weapon_id: str | None = None
    animal_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OwnedAnimal:
        return cls(
            name=str(data.get("name", "")),
            count=int(data.get("count", 1)),
            level=int(data.get("level", 1)),
            equipped_weapon_id=data.get("equipped_weapon_id"),
            animal_id=data.get("animal_id"),
        )


@dataclass
class InventorySnapshot:
    """Represents a frozen snapshot of player inventory."""

    snapshot_id: str
    animals: list[OwnedAnimal] = field(default_factory=list)
    weapons: list[OwnedWeapon] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "animals": [a.to_dict() for a in self.animals],
            "weapons": [w.to_dict() for w in self.weapons],
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InventorySnapshot:
        return cls(
            snapshot_id=str(data.get("snapshot_id", "")),
            animals=[
                OwnedAnimal.from_dict(item) if isinstance(item, dict) else item
                for item in data.get("animals", [])
            ],
            weapons=[
                OwnedWeapon.from_dict(item) if isinstance(item, dict) else item
                for item in data.get("weapons", [])
            ],
            timestamp=float(data.get("timestamp", time.time())),
        )


__all__ = [
    "STAT_NAMES",
    "Animal",
    "Weapon",
    "Passive",
    "OwnedWeapon",
    "OwnedAnimal",
    "InventorySnapshot",
]
