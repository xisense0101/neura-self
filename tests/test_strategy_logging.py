"""
Test suite for Strategy Engine and Dashboard Logging optimizations in NeuraSelf.
Verifies:
1. Terminal deduplication (preventing duplicate logs on Discord message edits and battles).
2. Clean single-log emission for equip sequences during autopilot and manual commands.
3. Structured event logging into state.command_logs across dashboard strategy endpoints.
4. Retention and rendering of strategy logs in /api/stats.
5. Harmonized log category colors and CSS tags.
"""

import json
import os
import shutil
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
pytestmark = pytest.mark.skip(reason="Strategy Engine feature paused (Coming Soon)")

from discord.ext import commands

try:
    from cogs.strategy_engine import StrategyEngine
except ModuleNotFoundError:
    StrategyEngine = None
from core.bot import NeuraBot
import core.state as state
from modules.neura_logs import neura_logger
from owo_strategy.optimizer import CandidateTeam
from owo_strategy.schemas import OwnedAnimal, OwnedWeapon


@pytest.fixture
def temp_strategy_env():
    temp_dir = tempfile.mkdtemp(prefix="neura_log_test_")
    os.makedirs(os.path.join(temp_dir, "config"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "data"), exist_ok=True)

    bot = commands.Bot(command_prefix="!", self_bot=True)
    bot.base_dir = temp_dir
    bot.user_id = "1451414972377862228"
    bot.username = "TestStrategist"
    bot.owo_bot_id = "408785106942164992"
    bot.log = MagicMock()
    bot.neura_enqueue = AsyncMock()
    bot.get_cmd_priority = MagicMock(return_value=2)
    bot.config = {
        "strategy": {
            "enabled": True,
            "auto_equip": True,
            "auto_dismantle": False,
            "dry_run": True,
        }
    }

    cog = StrategyEngine(bot)
    yield cog, bot, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestStrategyLoggingDeduplication:
    """Verify duplicate suppression on message edits and repeated team telemetry."""

    @pytest.mark.asyncio
    async def test_team_telemetry_no_duplicate_on_message_edit(self, temp_strategy_env):
        cog, bot, _ = temp_strategy_env

        class MockAuthor:
            id = 408785106942164992
            name = "OwO"

        class MockMessage:
            def __init__(self, msg_id, content="", embeds=None):
                self.id = msg_id
                self.author = MockAuthor()
                self.content = content
                self.embeds = embeds or []
                self.reactions = []

        class MockField:
            def __init__(self, name, value):
                self.name = name
                self.value = value

        class MockEmbed:
            def __init__(self, title, desc, fields=None):
                self.title = title
                self.description = desc
                self.author = None
                self.footer = None
                self.fields = fields or []

        # Battle/Team embed with valid animals: lion, owl, elephant
        fields = [
            MockField("1. lion", "<:shield:1> Defender's Aegis (101)\nLevel 50"),
            MockField("2. owl", "<:bow:1> Compound Bow (103)\nLevel 50"),
            MockField("3. elephant", "<:sword:1> Great Sword (106)\nLevel 50"),
        ]
        embed = MockEmbed("OwO Team", "Active Battle Team", fields=fields)
        msg_initial = MockMessage(msg_id=990001, embeds=[embed])
        msg_edited = MockMessage(msg_id=990001, embeds=[embed])

        # Initial message received
        await cog._handle_owo_telemetry(msg_initial)
        initial_calls = [c for c in bot.log.call_args_list if c[0][0] == "STRATEGY" and "Updated active team" in c[0][1]]
        assert len(initial_calls) == 1
        assert "lion" in initial_calls[0][0][1]

        # OwO edits the exact same message (e.g. adding components or reactions)
        await cog._handle_owo_telemetry(msg_edited)
        edited_calls = [c for c in bot.log.call_args_list if c[0][0] == "STRATEGY" and "Updated active team" in c[0][1]]
        # Must still be exactly 1 call (no duplicate on edit!)
        assert len(edited_calls) == 1

        # A third message with the SAME team arrives (e.g. another battle)
        msg_battle = MockMessage(msg_id=990002, embeds=[embed])
        await cog._handle_owo_telemetry(msg_battle)
        third_calls = [c for c in bot.log.call_args_list if c[0][0] == "STRATEGY" and "Updated active team" in c[0][1]]
        assert len(third_calls) == 1

        # Now OwO sends an updated team with a different composition
        new_fields = [
            MockField("1. cat", "<:shield:1> Defender's Aegis (101)\nLevel 50"),
            MockField("2. owl", "<:bow:1> Compound Bow (103)\nLevel 50"),
            MockField("3. elephant", "<:sword:1> Great Sword (106)\nLevel 50"),
        ]
        msg_new_team = MockMessage(msg_id=990003, embeds=[MockEmbed("OwO Team", "Active Battle Team", fields=new_fields)])
        await cog._handle_owo_telemetry(msg_new_team)
        updated_calls = [c for c in bot.log.call_args_list if c[0][0] == "STRATEGY" and "Updated active team" in c[0][1]]
        assert len(updated_calls) == 2
        assert "cat" in updated_calls[1][0][1]

    @pytest.mark.asyncio
    async def test_autopilot_tick_emits_single_equip_log(self, temp_strategy_env):
        cog, bot, _ = temp_strategy_env

        # Run autopilot tick
        await cog._autopilot_tick()

        # Check strategy logs
        strat_logs = [c[0][1] for c in bot.log.call_args_list if c[0][0] == "STRATEGY"]
        autopilot_logs = [msg for msg in strat_logs if "Autopilot: Enqueued" in msg]
        generic_equip_logs = [msg for msg in strat_logs if msg.startswith("Enqueued") and "equip commands" in msg]

        # There must be exactly 1 autopilot equip log, and NO generic duplicate log
        assert len(autopilot_logs) == 1
        assert len(generic_equip_logs) == 0

    @pytest.mark.asyncio
    async def test_owo_feedback_clean_formatting(self, temp_strategy_env):
        cog, bot, _ = temp_strategy_env

        class MockAuthor:
            id = 408785106942164992
            name = "OwO"

        class MockMessage:
            def __init__(self, content):
                self.id = 990010
                self.author = MockAuthor()
                self.content = content
                self.embeds = []
                self.reactions = []

        # Message with newlines and mentions
        msg_verify = MockMessage("Your team has been updated!\n[Extra info]\n<@1451414972377862228>")
        await cog._handle_owo_telemetry(msg_verify)

        verified_calls = [c for c in bot.log.call_args_list if c[0][0] == "STRATEGY_VERIFIED"]
        assert len(verified_calls) == 1
        # Verification message should be single-line and clean
        assert "\n" not in verified_calls[0][0][1]
        assert "Your team has been updated!" in verified_calls[0][0][1]

        # Rejection message
        msg_reject = MockMessage("You do not own this animal!\nCheck your owo zoo.")
        await cog._handle_owo_telemetry(msg_reject)

        warn_calls = [c for c in bot.log.call_args_list if c[0][0] == "STRATEGY_WARN"]
        assert len(warn_calls) == 1
        assert "\n" not in warn_calls[0][0][1]
        assert "You do not own this animal!" in warn_calls[0][0][1]


class TestDashboardStrategyLogging:
    """Verify dashboard endpoints emit structured logs and /api/stats delivers them."""

    def test_logmisc_config_contains_strategy_colors(self):
        repo_dir = os.getcwd() if os.path.exists(os.path.join(os.getcwd(), "config", "logmisc.json")) else os.path.join(os.getcwd(), "neura-self")
        config_path = os.path.join(repo_dir, "config", "logmisc.json")
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        colors = cfg.get("colors", {})
        assert "STRATEGY" in colors
        assert "STRATEGY_VERIFIED" in colors
        assert "STRATEGY_WARN" in colors
        assert colors["STRATEGY"].startswith("#")

    def test_neura_logs_module_has_strategy_colors(self):
        neura_logger._load_config()
        colors = neura_logger.log_config.get("colors", {})
        assert "STRATEGY" in colors
        assert "STRATEGY_VERIFIED" in colors
        assert "STRATEGY_WARN" in colors

    def test_dashboard_css_has_strategy_tags(self):
        repo_dir = os.getcwd() if os.path.exists(os.path.join(os.getcwd(), "dashboard", "static", "css", "pages", "dashboard.css")) else os.path.join(os.getcwd(), "neura-self")
        css_path = os.path.join(repo_dir, "dashboard", "static", "css", "pages", "dashboard.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()
        assert ".tag-strategy" in css_content
        assert ".tag-strategy_verified" in css_content
        assert ".tag-strategy_warn" in css_content

    def test_dashboard_api_strategy_optimize_emits_log(self):
        from dashboard.app import app

        with app.test_client() as client:
            state.command_logs.clear()
            res = client.post("/api/strategy/optimize", json={"coarse_seeds": 2, "fine_seeds": 5})
            assert res.status_code == 200
            data = res.get_json()
            assert data["success"] is True

            strat_logs = [l for l in state.command_logs if l["type"] == "STRATEGY"]
            assert len(strat_logs) >= 1
            assert "Tournament Optimizer completed" in strat_logs[0]["message"]
            assert strat_logs[0]["color"] == "#a855f7"

    def test_api_stats_returns_strategy_logs_for_account(self):
        from dashboard.app import app, stats
        from flask import session

        test_uid = "1451414972377862228"
        state.account_stats[test_uid] = state.get_empty_stats()
        state.command_logs.clear()
        state.log_command("STRATEGY", "Tournament winner computed", "success", bot_name="TestBot", bot_id=test_uid)
        state.log_command("STRATEGY_VERIFIED", "OwO verified equip: success", "success", bot_name="TestBot", bot_id=test_uid)

        with app.test_request_context(f"/api/stats?id={test_uid}"):
            session['logged_in'] = True
            resp = stats()
            data = resp.get_json()
            logs = data.get("logs", [])
            assert len(logs) >= 2
            types = [l["type"] for l in logs]
            assert "STRATEGY" in types
            assert "STRATEGY_VERIFIED" in types
