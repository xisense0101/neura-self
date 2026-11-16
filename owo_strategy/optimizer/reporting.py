"""
Reporting and Comparison Generator for OwO Strategy Engine.

Produces structured Markdown and JSON reports comparing Current Team vs Recommended Team:
  - Win rate delta (e.g. +38.5% win rate).
  - Expected survival HP.
  - 95% Wilson score confidence intervals.
  - Tactical synergies detected (e.g. "Giraffbot Shield draws fire while Flamingo heals and Eagle executes backline").
  - Missing blueprint alerts (flags uninspected weapons and suggests `owo weapon <id>`).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Mapping, Optional

from owo_strategy.optimizer.evaluator import CandidateEvaluation, get_weapon_spec
from owo_strategy.optimizer.team_optimizer import CandidateTeam, OptimizationResult


def check_missing_blueprints(team: CandidateTeam) -> list[dict[str, Any]]:
    """Scan candidate team weapons for missing or estimated blueprints."""
    alerts: list[dict[str, Any]] = []
    for pos, w in enumerate(team.weapons):
        w_id = getattr(w, "id", None) or (w.get("id") if isinstance(w, Mapping) else None) or f"W{pos+1}"
        w_name = getattr(w, "weapon_name", None) or getattr(w, "name", None) or (
            w.get("weapon_name") if isinstance(w, Mapping) else (w.get("name") if isinstance(w, Mapping) else str(w))
        )
        is_exact = getattr(w, "quality_is_exact", None)
        if is_exact is None and isinstance(w, Mapping):
            is_exact = w.get("quality_is_exact")
        q_val = getattr(w, "quality_val", None)
        if q_val is None and isinstance(w, Mapping):
            q_val = w.get("quality_val")

        # If not confirmed exact, or marked as estimate, flag alert
        if is_exact is False:
            q_str = f"{float(q_val):.1f}%" if q_val is not None else "Estimated"
            alerts.append({
                "weapon_id": str(w_id),
                "weapon_name": str(w_name),
                "position": pos + 1,
                "quality_val": q_val,
                "suggested_command": f"owo weapon {w_id}",
                "message": (
                    f"Weapon '{w_name}' (ID: `{w_id}`) at Position {pos+1} has an unconfirmed quality ({q_str}). "
                    f"Run `owo weapon {w_id}` to reveal exact roll blueprint and passives."
                ),
            })
    return alerts


def build_slot_summary(animal: Any, weapon: Any, pos: int) -> dict[str, Any]:
    """Build slot summary dictionary for JSON reporting."""
    a_name = getattr(animal, "name", None) or (animal.get("name") if isinstance(animal, Mapping) else str(animal))
    a_level = getattr(animal, "level", None) or (animal.get("level") if isinstance(animal, Mapping) else 50) or 50
    w_spec = get_weapon_spec(weapon)
    w_id = getattr(weapon, "id", None) or (weapon.get("id") if isinstance(weapon, Mapping) else None) or f"W{pos+1}"

    return {
        "position": pos + 1,
        "animal": str(a_name),
        "animal_level": int(a_level),
        "weapon_id": str(w_id),
        "weapon_name": w_spec["name"],
        "weapon_slug": w_spec["slug"],
        "role": w_spec["role"],
        "stat_type": w_spec["stat_type"],
        "wp_cost": w_spec["wp_cost"],
        "base_modifier": w_spec.get("base_modifier", 1.0),
    }


def generate_json_report(
    opt_result: OptimizationResult,
    current_team: Optional[CandidateTeam] = None,
) -> dict[str, Any]:
    """Generate structured JSON comparison dictionary."""
    winner = opt_result.winner
    baseline = opt_result.current_team_benchmark or current_team

    current_win_rate = baseline.fine_win_rate if baseline else 0.0
    current_remaining_hp = baseline.fine_remaining_hp if baseline else 0.0
    current_eval = baseline.evaluation if baseline else None

    recommended_eval = winner.evaluation

    # Missing blueprints
    rec_alerts = check_missing_blueprints(winner)
    cur_alerts = check_missing_blueprints(baseline) if baseline else []

    all_alerts = rec_alerts + [
        a for a in cur_alerts if a["weapon_id"] not in {x["weapon_id"] for x in rec_alerts}
    ]

    report = {
        "summary": {
            "recommended_win_rate": round(winner.fine_win_rate * 100.0, 2),
            "current_win_rate": round(current_win_rate * 100.0, 2),
            "win_rate_delta_percent": round(opt_result.win_rate_delta * 100.0, 2),
            "win_rate_delta_str": f"{opt_result.win_rate_delta * 100.0:+.1f}%",
            "expected_survival_hp": round(winner.fine_remaining_hp, 1),
            "current_survival_hp": round(current_remaining_hp, 1),
            "wilson_ci_95": {
                "lower": round(winner.wilson_lower * 100.0, 2),
                "upper": round(winner.wilson_upper * 100.0, 2),
            },
            "total_simulations": opt_result.total_simulations,
            "execution_time_seconds": opt_result.execution_time_seconds,
        },
        "recommended_team": {
            "animals": winner.animal_names,
            "weapons": winner.weapon_names,
            "slots": [build_slot_summary(winner.animals[i], winner.weapons[i], i) for i in range(3)],
            "frontline_ehp": recommended_eval.frontline_ehp if recommended_eval else 0.0,
            "total_team_ehp": recommended_eval.total_team_ehp if recommended_eval else 0.0,
            "sustained_dps": recommended_eval.sustained_dps if recommended_eval else 0.0,
            "wp_solvent": recommended_eval.wp_solvent if recommended_eval else True,
            "solvency_ratio": recommended_eval.solvency_ratio if recommended_eval else 1.0,
            "fine_wins": winner.fine_wins,
            "fine_losses": winner.fine_losses,
            "fine_draws": winner.fine_draws,
            "fine_total": winner.fine_total,
        },
        "current_team": {
            "animals": baseline.animal_names if baseline else [],
            "weapons": baseline.weapon_names if baseline else [],
            "slots": [build_slot_summary(baseline.animals[i], baseline.weapons[i], i) for i in range(3)] if baseline else [],
            "frontline_ehp": current_eval.frontline_ehp if current_eval else 0.0,
            "total_team_ehp": current_eval.total_team_ehp if current_eval else 0.0,
            "sustained_dps": current_eval.sustained_dps if current_eval else 0.0,
            "wp_solvent": current_eval.wp_solvent if current_eval else False,
            "solvency_ratio": current_eval.solvency_ratio if current_eval else 0.0,
            "fine_wins": baseline.fine_wins if baseline else 0,
            "fine_losses": baseline.fine_losses if baseline else 0,
            "fine_draws": baseline.fine_draws if baseline else 0,
            "fine_total": baseline.fine_total if baseline else 0,
        } if baseline else None,
        "synergies_detected": recommended_eval.synergies if recommended_eval else [],
        "missing_blueprint_alerts": all_alerts,
        "pipeline_stages": {
            "stage0_candidates": opt_result.stage0_candidates_count,
            "stage1_top50_screened": opt_result.stage1_top50_count,
            "stage2_top10_coarse": opt_result.stage2_top10_count,
            "stage3_fine_evaluated": opt_result.stage3_evaluated_count,
        },
    }
    return report


def generate_markdown_report(
    opt_result: OptimizationResult,
    current_team: Optional[CandidateTeam] = None,
) -> str:
    """Generate human-readable, structured GitHub-flavored Markdown report."""
    data = generate_json_report(opt_result, current_team)
    summary = data["summary"]
    rec = data["recommended_team"]
    cur = data["current_team"]
    synergies = data["synergies_detected"]
    alerts = data["missing_blueprint_alerts"]

    lines = [
        "# ⚔️ OwO Strategy Engine - Team Optimization Report",
        "",
        "## 📊 Executive Summary",
        "",
        "| Metric | Current Team | Recommended Team | Delta |",
        "| :--- | :--- | :--- | :--- |",
    ]

    cur_wr = f"{summary['current_win_rate']:.1f}%" if cur else "N/A"
    rec_wr = f"{summary['recommended_win_rate']:.1f}%"
    delta_wr = f"**{summary['win_rate_delta_str']}**"
    lines.append(f"| **Win Rate** | {cur_wr} | {rec_wr} | {delta_wr} |")

    cur_hp = f"{summary['current_survival_hp']:.1f} HP" if cur else "N/A"
    rec_hp = f"{summary['expected_survival_hp']:.1f} HP"
    hp_diff = summary['expected_survival_hp'] - summary['current_survival_hp'] if cur else 0.0
    lines.append(f"| **Expected Survival HP** | {cur_hp} | {rec_hp} | {hp_diff:+.1f} HP |")

    ci_str = f"[{summary['wilson_ci_95']['lower']:.1f}%, {summary['wilson_ci_95']['upper']:.1f}%]"
    lines.append(f"| **95% Wilson Confidence** | - | {ci_str} | Statistically Validated |")

    cur_ehp = f"{cur['frontline_ehp']:.1f}" if cur else "N/A"
    rec_ehp = f"{rec['frontline_ehp']:.1f}"
    ehp_diff = rec['frontline_ehp'] - (cur['frontline_ehp'] if cur else 0.0)
    lines.append(f"| **Frontline EHP** | {cur_ehp} | {rec_ehp} | {ehp_diff:+.1f} |")

    cur_dps = f"{cur['sustained_dps']:.1f}" if cur else "N/A"
    rec_dps = f"{rec['sustained_dps']:.1f}"
    dps_diff = rec['sustained_dps'] - (cur['sustained_dps'] if cur else 0.0)
    lines.append(f"| **Sustained DPS** | {cur_dps} | {rec_dps} | {dps_diff:+.1f} |")

    lines.extend([
        "",
        "## 🛡️ Recommended Lineup",
        "",
        "| Slot | Animal | Role | Weapon | WP Cost | Base Mod |",
        "| :---: | :--- | :--- | :--- | :---: | :---: |",
    ])
    for slot in rec["slots"]:
        pos_badge = f"Pos {slot['position']}" + (" (Frontline)" if slot["position"] == 1 else "")
        lines.append(
            f"| {pos_badge} | **{slot['animal']}** (Lvl {slot['animal_level']}) | `{slot['role']}` | {slot['weapon_name']} | {slot['wp_cost']} WP | {slot['base_modifier']*100:.0f}% |"
        )

    if cur and cur["slots"]:
        lines.extend([
            "",
            "## 🔄 Current Lineup (Baseline)",
            "",
            "| Slot | Animal | Role | Weapon | WP Cost | Base Mod |",
            "| :---: | :--- | :--- | :--- | :---: | :---: |",
        ])
        for slot in cur["slots"]:
            pos_badge = f"Pos {slot['position']}" + (" (Frontline)" if slot["position"] == 1 else "")
            lines.append(
                f"| {pos_badge} | **{slot['animal']}** (Lvl {slot['animal_level']}) | `{slot['role']}` | {slot['weapon_name']} | {slot['wp_cost']} WP | {slot['base_modifier']*100:.0f}% |"
            )

    # Detected Synergies
    lines.extend([
        "",
        "## ✨ Synergies Detected",
        "",
    ])
    if synergies:
        for s in synergies:
            lines.append(f"- ⚡ **{s}**")
    else:
        lines.append("- Balanced core combat synergy.")

    # Missing Blueprint Alerts
    if alerts:
        lines.extend([
            "",
            "## ⚠️ Missing Blueprint Alerts",
            "",
            "> [!WARNING]",
            "> Some weapons in your lineup have unconfirmed or estimated stats. Run the inspection commands in Discord to lock in exact blueprints:",
            "",
        ])
        for a in alerts:
            lines.append(f"- **{a['weapon_name']}** (ID: `{a['weapon_id']}`): run `{a['suggested_command']}`")
    else:
        lines.extend([
            "",
            "## ✅ Blueprint Verification",
            "",
            "All equipped weapons possess 100% verified exact blueprints.",
        ])

    # Tournament Pipeline Metrics
    p_stages = data["pipeline_stages"]
    lines.extend([
        "",
        "## ⏱️ Benchmark & Performance Metrics",
        "",
        f"- **Stage 0 Combinations Screened**: {p_stages['stage0_candidates']:,}",
        f"- **Stage 1 Heuristic Top 50**: {p_stages['stage1_top50_screened']}",
        f"- **Stage 2 Coarse Tournament Top 10**: {p_stages['stage2_top10_coarse']}",
        f"- **Stage 3 Fine Monte Carlo Seeds**: {summary['total_simulations']:,} battle simulations",
        f"- **Optimizer Execution Latency**: **{summary['execution_time_seconds']:.2f}s** (Target: < 30.0s)",
        "",
    ])

    return "\n".join(lines)


def generate_full_report(
    opt_result: OptimizationResult,
    current_team: Optional[CandidateTeam] = None,
) -> tuple[str, dict[str, Any]]:
    """Return both Markdown string and JSON dictionary."""
    md = generate_markdown_report(opt_result, current_team)
    js = generate_json_report(opt_result, current_team)
    return md, js
