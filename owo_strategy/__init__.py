"""OwO Strategy Engine for NeuraSelf.

Provides:
- schemas: Data models (Animal, Weapon, Passive, OwnedAnimal, OwnedWeapon, InventorySnapshot)
- ingestion: Parsers and catalog sync
- simulator: Battle engine and damage pipeline
- optimizer: 3-stage multi-fidelity team optimizer, boss solver, shard planner, level scaler, reporting
"""

from __future__ import annotations

from owo_strategy.schemas.models import (
    Animal,
    Weapon,
    Passive,
    OwnedAnimal,
    OwnedWeapon,
    InventorySnapshot,
    STAT_NAMES,
)
from owo_strategy.simulator.battle_engine import (
    BattleEngine,
    BattleResult,
    BattleEvent,
    Pet,
    Team,
    Weapon as SimWeapon,
    create_pet,
)
from owo_strategy.simulator.damage_pipeline import (
    DamageResult,
    calculate_damage_pipeline,
)
from owo_strategy.simulator.formulas import (
    calculate_effective_resistance,
    calculate_ehp,
    calculate_pet_stats,
    PetStats,
)
from owo_strategy.ingestion.catalog_sync import (
    load_catalog_animals,
    load_catalog_weapons,
    load_catalog_passives,
    sync_all,
)
from owo_strategy.ingestion.neon_parser import (
    parse_neon_inventory,
    parse_neon_weapon_page,
    parse_blueprint,
    parse_weapon_blueprint,
    parse_weapon_row,
    parse_team_message,
    parse_weapon_inventory_message,
)
from owo_strategy.optimizer.evaluator import (
    CandidateEvaluation,
    PetEvaluation,
    evaluate_candidate,
    extract_dex_stats,
    get_weapon_spec,
    normalize_weapon_slug,
    KNOWN_ANIMAL_DEX,
    WEAPON_SPECS,
)
from owo_strategy.optimizer.team_optimizer import (
    CandidateTeam,
    OptimizationResult,
    TeamOptimizer,
    create_sim_weapon,
    calculate_wilson_interval,
)
from owo_strategy.optimizer.boss_solver import (
    BossPreset,
    BossRaidSolver,
    STANDARD_BOSS_PRESETS,
)
from owo_strategy.optimizer.shard_planner import (
    ShardPlanner,
    DismantlePlan,
    ShardPlan,
    SHARD_MILESTONES,
)
from owo_strategy.optimizer.level_scaler import (
    MultiLevelScaler,
    LevelProgressionPoint,
    NeonUtilExporter,
)
from owo_strategy.optimizer.reporting import (
    generate_full_report,
    generate_json_report,
    generate_markdown_report,
    check_missing_blueprints,
)

__all__ = [
    "Animal",
    "Weapon",
    "Passive",
    "OwnedAnimal",
    "OwnedWeapon",
    "InventorySnapshot",
    "STAT_NAMES",
    "BattleEngine",
    "BattleResult",
    "BattleEvent",
    "Pet",
    "Team",
    "SimWeapon",
    "create_pet",
    "DamageResult",
    "calculate_damage_pipeline",
    "calculate_effective_resistance",
    "calculate_ehp",
    "calculate_pet_stats",
    "PetStats",
    "load_catalog_animals",
    "load_catalog_weapons",
    "load_catalog_passives",
    "sync_all",
    "parse_neon_inventory",
    "parse_neon_weapon_page",
    "parse_blueprint",
    "parse_weapon_blueprint",
    "parse_weapon_row",
    "parse_team_message",
    "parse_weapon_inventory_message",
    "CandidateEvaluation",
    "PetEvaluation",
    "evaluate_candidate",
    "extract_dex_stats",
    "get_weapon_spec",
    "normalize_weapon_slug",
    "KNOWN_ANIMAL_DEX",
    "WEAPON_SPECS",
    "CandidateTeam",
    "OptimizationResult",
    "TeamOptimizer",
    "create_sim_weapon",
    "calculate_wilson_interval",
    "BossPreset",
    "BossRaidSolver",
    "STANDARD_BOSS_PRESETS",
    "ShardPlanner",
    "DismantlePlan",
    "ShardPlan",
    "SHARD_MILESTONES",
    "MultiLevelScaler",
    "LevelProgressionPoint",
    "NeonUtilExporter",
    "generate_full_report",
    "generate_json_report",
    "generate_markdown_report",
    "check_missing_blueprints",
]
