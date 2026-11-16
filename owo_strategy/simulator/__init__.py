"""OwO Battle Simulator Package."""

from owo_strategy.simulator import damage_pipeline as DamagePipeline
from owo_strategy.simulator import formulas as Formulas
from owo_strategy.simulator.battle_engine import (
    BattleEngine,
    BattleEvent,
    BattleResult,
    Buff,
    Pet,
    Team,
    TurnLog,
    Weapon,
    create_pet,
)
from owo_strategy.simulator.damage_pipeline import (
    DamageResult,
    calculate_damage_pipeline,
)
from owo_strategy.simulator.formulas import (
    EHPResult,
    EffectiveResistance,
    PetStats,
    calculate_effective_resistance,
    calculate_ehp,
    calculate_pet_stats,
)

__all__ = [
    "BattleEngine",
    "BattleEvent",
    "BattleResult",
    "Buff",
    "Pet",
    "Team",
    "TurnLog",
    "Weapon",
    "create_pet",
    "DamageResult",
    "calculate_damage_pipeline",
    "EHPResult",
    "EffectiveResistance",
    "PetStats",
    "calculate_effective_resistance",
    "calculate_ehp",
    "calculate_pet_stats",
    "DamagePipeline",
    "Formulas",
]
