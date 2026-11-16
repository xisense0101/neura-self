"""Schemas and models for OwO Strategy Engine."""

from owo_strategy.schemas.models import (
    STAT_NAMES,
    Animal,
    InventorySnapshot,
    OwnedAnimal,
    OwnedWeapon,
    Passive,
    Weapon,
)
from owo_strategy.simulator.formulas import PetStats

# Convenience aliases
BattlePet = OwnedAnimal
TeamConfig = InventorySnapshot

__all__ = [
    "STAT_NAMES",
    "Animal",
    "Weapon",
    "Passive",
    "OwnedWeapon",
    "OwnedAnimal",
    "InventorySnapshot",
    "BattlePet",
    "TeamConfig",
    "PetStats",
]
