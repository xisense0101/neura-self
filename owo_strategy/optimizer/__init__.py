"""
OwO Strategy Engine Optimizer Subpackage.

Exposes team optimization, candidate evaluation, boss raid simulation,
and shard dismantling planners.
"""

from .boss_solver import BossPreset, BossRaidSolver, STANDARD_BOSS_PRESETS
from .evaluator import CandidateEvaluation, evaluate_candidate, get_weapon_spec
from .level_scaler import MultiLevelScaler, NeonUtilExporter
from .reporting import generate_full_report
from .shard_planner import DismantlePlan, ShardPlanner
from .team_optimizer import CandidateTeam, OptimizationResult, TeamOptimizer

__all__ = [
    "TeamOptimizer",
    "CandidateTeam",
    "OptimizationResult",
    "evaluate_candidate",
    "CandidateEvaluation",
    "get_weapon_spec",
    "BossRaidSolver",
    "BossPreset",
    "STANDARD_BOSS_PRESETS",
    "ShardPlanner",
    "DismantlePlan",
    "MultiLevelScaler",
    "NeonUtilExporter",
    "generate_full_report",
]
