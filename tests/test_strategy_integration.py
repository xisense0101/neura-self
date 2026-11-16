"""
Integration tests for the OwO Strategy Engine in NeuraSelf.

Validates:
1. Module imports for all `owo_strategy` packages (schemas, ingestion, simulator, optimizer).
2. Cog lifecycle and commands in `cogs.strategy_engine` using mock `commands.Bot`.
3. Discord message listeners and telemetry ingestion for OwO responses:
   - `owo team`
   - `owo weapon inv`
   - `owo weapon <id>`
   - `owo zoo`
   - message edit updates
   - rejection of unauthorized authors
4. Optimization, evaluation, boss raid simulation, and safe shard dismantling pipeline.
5. Flask Dashboard REST API endpoints in `dashboard/app.py`:
   - GET `/api/strategy/state`
   - POST `/api/strategy/optimize`
   - POST `/api/strategy/boss`
   - POST `/api/strategy/shards`
6. Regression safety for core NeuraSelf cogs and architecture.
"""

from __future__ import annotations

import pytest
pytestmark = pytest.mark.skip(reason="Strategy Engine feature paused (Coming Soon)")

import asyncio
import json
import os
import shutil
import tempfile
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ext import commands

# -----------------------------------------------------------------------------
# OwO Identity Constants & Mock Objects
# -----------------------------------------------------------------------------
OWO_BOT_ID = 408785106942164992


class MockAuthor:
    """Simulated Discord user/bot author."""
    def __init__(self, author_id: int | str, name: str = "OwO", bot: bool = True):
        self.id = int(author_id)
        self.name = name
        self.bot = bot

    def __str__(self) -> str:
        return self.name


class MockField:
    """Simulated Discord Embed Field."""
    def __init__(self, name: str, value: str, inline: bool = False):
        self.name = name
        self.value = value
        self.inline = inline


class MockEmbed:
    """Simulated Discord Embed."""
    def __init__(
        self,
        title: str = "",
        description: str = "",
        fields: list[MockField] | None = None,
        footer_text: str = "",
        author_name: str = "",
    ):
        self.title = title
        self.description = description
        self.fields = fields or []
        self.footer = type("MockFooter", (), {"text": footer_text})() if footer_text else None
        self.author = type("MockEmbedAuthor", (), {"name": author_name})() if author_name else None


class MockMessage:
    """Simulated Discord Message."""
    def __init__(
        self,
        content: str = "",
        embeds: list[MockEmbed] | None = None,
        author: MockAuthor | None = None,
        channel: Any = None,
    ):
        self.content = content
        self.embeds = embeds or []
        self.author = author or MockAuthor(OWO_BOT_ID)
        self.channel = channel or MockChannel()

    async def edit(self, content: str | None = None, embed: MockEmbed | None = None) -> None:
        if content is not None:
            self.content = content
        if embed is not None:
            self.embeds = [embed]


class MockChannel:
    """Simulated Discord Messageable Channel."""
    def __init__(self):
        self.sent_messages: list[MockMessage] = []

    async def send(self, content: str | None = None, embed: MockEmbed | None = None) -> MockMessage:
        msg = MockMessage(content=content or "", embeds=[embed] if embed else [], channel=self)
        self.sent_messages.append(msg)
        return msg


# =============================================================================
# 1. Strategy Engine Module Imports & Catalogs
# =============================================================================
class TestStrategyModuleImports:
    """Verify all owo_strategy subpackages, classes, and catalogs load properly."""

    def test_schemas_import(self):
        from owo_strategy.schemas import (
            BattlePet,
            OwnedAnimal,
            OwnedWeapon,
            PetStats,
            TeamConfig,
        )
        from owo_strategy.schemas.models import (
            OwnedAnimal as OA2,
            OwnedWeapon as OW2,
        )

        assert OwnedAnimal is OA2
        assert OwnedWeapon is OW2

        animal = OwnedAnimal(name="lion", level=50, equipped_weapon_id="664DFC")
        assert animal.name == "lion"
        assert animal.level == 50
        assert animal.to_dict()["equipped_weapon_id"] == "664DFC"

        weapon = OwnedWeapon(id="664DFC", weapon_name="Great Sword", quality_val=95.5)
        assert weapon.id == "664DFC"
        assert weapon.quality_val == 95.5
        assert weapon.to_dict()["weapon_name"] == "Great Sword"

    def test_ingestion_import(self):
        from owo_strategy.ingestion import (
            OWO_BOT_ID as IMPORTED_BOT_ID,
            ParsedTeam,
            ParsedWeaponInspect,
            ParsedWeaponInv,
            ParsedZoo,
            is_owo_bot,
            parse_neon_inventory,
            parse_owo_message,
            parse_owo_team,
            parse_owo_weapon_inspect,
            parse_owo_weapon_inv,
            parse_owo_zoo,
            parse_team_message,
            parse_weapon_inventory_message,
            sync_catalogs_from_neon,
        )

        assert int(IMPORTED_BOT_ID) == OWO_BOT_ID
        assert is_owo_bot(OWO_BOT_ID) is True
        assert callable(parse_owo_message)
        assert callable(parse_team_message)
        assert callable(sync_catalogs_from_neon)

    def test_simulator_import(self):
        from owo_strategy.simulator import (
            BattleEngine,
            DamagePipeline,
            Formulas,
            Pet,
            Team,
            Weapon,
        )
        assert callable(BattleEngine)
        assert callable(Pet)
        assert callable(Team)
        assert callable(Weapon)

    def test_optimizer_import(self):
        from owo_strategy.optimizer import (
            BossPreset,
            BossRaidSolver,
            CandidateEvaluation,
            CandidateTeam,
            DismantlePlan,
            MultiLevelScaler,
            NeonUtilExporter,
            OptimizationResult,
            STANDARD_BOSS_PRESETS,
            ShardPlanner,
            TeamOptimizer,
            evaluate_candidate,
            generate_full_report,
        )

        assert callable(TeamOptimizer)
        assert callable(BossRaidSolver)
        assert callable(ShardPlanner)
        assert "standard_cleave" in STANDARD_BOSS_PRESETS

    def test_catalogs_loading(self):
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        catalog_dir = os.path.join(base_path, "owo_strategy", "data")

        # Animals catalog
        animals_file = os.path.join(catalog_dir, "catalog_animals.json")
        assert os.path.exists(animals_file), f"Missing {animals_file}"
        with open(animals_file, "r", encoding="utf-8") as f:
            animals_data = json.load(f)
        assert isinstance(animals_data, (list, dict))
        assert len(animals_data) > 1000, f"Expected >1000 animals, found {len(animals_data)}"

        # Weapons catalog
        weapons_file = os.path.join(catalog_dir, "catalog_weapons.json")
        assert os.path.exists(weapons_file), f"Missing {weapons_file}"
        with open(weapons_file, "r", encoding="utf-8") as f:
            weapons_data = json.load(f)
        assert len(weapons_data) >= 20, f"Expected >=20 weapons, found {len(weapons_data)}"

        # Passives catalog
        passives_file = os.path.join(catalog_dir, "catalog_passives.json")
        assert os.path.exists(passives_file), f"Missing {passives_file}"
        with open(passives_file, "r", encoding="utf-8") as f:
            passives_data = json.load(f)
        assert len(passives_data) >= 15, f"Expected >=15 passives, found {len(passives_data)}"


# =============================================================================
# 2. Strategy Engine Discord Cog Lifecycle
# =============================================================================
class TestStrategyEngineCog:
    """Test loading and state initialization of cogs.strategy_engine."""

    @pytest.fixture
    def temp_base_dir(self):
        temp_dir = tempfile.mkdtemp(prefix="neura_strategy_test_")
        os.makedirs(os.path.join(temp_dir, "data"), exist_ok=True)
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_cog_instantiation_and_defaults(self, temp_base_dir):
        from cogs.strategy_engine import StrategyEngine

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_base_dir
        bot.owo_bot_id = str(OWO_BOT_ID)

        cog = StrategyEngine(bot)
        assert cog.dry_run is True
        assert len(cog.current_team_animals) == 3
        assert len(cog.current_team_weapons) == 3
        assert len(cog.inventory_animals) >= 10
        assert len(cog.inventory_weapons) >= 10
        assert cog.current_shards > 0
        assert os.path.exists(cog.state_file)

        # Verify state snapshot dictionary
        snap = cog.get_state_snapshot()
        assert "team" in snap
        assert "inventory_animals" in snap
        assert "inventory_weapons" in snap
        assert snap["dry_run"] is True

    @pytest.mark.asyncio
    async def test_bot_cog_registration_and_commands(self, temp_base_dir):
        from cogs.strategy_engine import StrategyEngine

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_base_dir

        cog = StrategyEngine(bot)
        await bot.add_cog(cog)

        retrieved_cog = bot.get_cog("StrategyEngine")
        assert retrieved_cog is cog

        cmd_names = [c.name for c in retrieved_cog.get_commands()]
        assert "owo-eval" in cmd_names
        assert "owo-opt" in cmd_names
        assert "owo-boss" in cmd_names
        assert "owo-shards" in cmd_names
        assert "owo-equip" in cmd_names

    @pytest.mark.asyncio
    async def test_strategy_register_actions(self, temp_base_dir):
        from cogs.strategy_engine import StrategyEngine

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_base_dir
        bot.config = {
            "strategy": {
                "enabled": True,
                "interval": [3600, 7200],
                "auto_equip": True,
            }
        }
        bot.log = MagicMock()
        bot.neura_register_command = AsyncMock()
        bot.get_cmd_priority = MagicMock(return_value=4)

        cog = StrategyEngine(bot)
        await cog.register_actions()

        assert cog.enabled is True
        assert cog.auto_equip is True
        bot.neura_register_command.assert_awaited_once()

        call_args = bot.neura_register_command.await_args
        cmd_id = call_args.args[0] if call_args.args else call_args.kwargs.get("cmd_id")
        action_callable = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("content")
        priority = call_args.kwargs.get("priority", call_args.args[2] if len(call_args.args) > 2 else None)
        delay = call_args.kwargs.get("delay", call_args.args[3] if len(call_args.args) > 3 else None)

        assert cmd_id == "strategy"
        assert action_callable == cog._autopilot_tick
        assert priority == 4
        assert 3600.0 <= delay <= 7200.0

    @pytest.mark.asyncio
    async def test_strategy_register_actions_disabled(self, temp_base_dir):
        from cogs.strategy_engine import StrategyEngine

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_base_dir
        bot.config = {"strategy": {"enabled": False}}
        bot.neura_register_command = AsyncMock()

        cog = StrategyEngine(bot)
        await cog.register_actions()

        assert cog.enabled is False
        bot.neura_register_command.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_autopilot_tick(self, temp_base_dir):
        from cogs.strategy_engine import StrategyEngine

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_base_dir
        bot.log = MagicMock()
        bot.neura_enqueue = AsyncMock()
        bot.get_cmd_priority = MagicMock(return_value=2)

        cog = StrategyEngine(bot)
        cog.enabled = True
        cog.auto_equip = True

        res = await cog._autopilot_tick()

        # Requirement 2: Returns list of enqueued commands or None
        assert res is None or isinstance(res, list)

        # Verify optimization triggered neura_enqueue for owo team and owo weapon
        assert bot.neura_enqueue.await_count >= 3
        enqueued_calls = [call.args[0] for call in bot.neura_enqueue.await_args_list]
        assert any(c.startswith("owo team") for c in enqueued_calls)
        assert any("weapon" in c for c in enqueued_calls)

        # Requirement 3: Verify enqueued equip commands use priority <= 2
        for call in bot.neura_enqueue.await_args_list:
            cmd = call.args[0]
            if cmd.startswith("owo team") or "weapon" in cmd:
                prio = call.kwargs.get("priority", call.args[1] if len(call.args) > 1 else None)
                assert prio is not None and prio <= 2, f"Expected priority <= 2, got {prio}"

    @pytest.mark.asyncio
    async def test_execute_live_equip_priority(self, temp_base_dir):
        from cogs.strategy_engine import StrategyEngine

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_base_dir
        bot.log = MagicMock()
        bot.neura_enqueue = AsyncMock()
        bot.get_cmd_priority = MagicMock(return_value=2)

        cog = StrategyEngine(bot)
        equip_cmds = await cog.execute_live_equip()

        assert isinstance(equip_cmds, list)
        assert len(equip_cmds) >= 3
        assert bot.neura_enqueue.await_count >= 3

        for call in bot.neura_enqueue.await_args_list:
            prio = call.kwargs.get("priority", call.args[1] if len(call.args) > 1 else None)
            assert prio is not None and prio <= 2, f"Equip command priority must be <= 2, got {prio}"

    @pytest.mark.asyncio
    async def test_multi_account_state_isolation(self, temp_base_dir):
        from cogs.strategy_engine import StrategyEngine
        from owo_strategy.schemas.models import OwnedAnimal, OwnedWeapon

        # Bot 1: user_id = "111111"
        bot1 = commands.Bot(command_prefix="!", self_bot=True)
        bot1.base_dir = temp_base_dir
        bot1.user_id = "111111"
        bot1.log = MagicMock()
        cog1 = StrategyEngine(bot1)

        # Bot 2: user_id = "222222"
        bot2 = commands.Bot(command_prefix="!", self_bot=True)
        bot2.base_dir = temp_base_dir
        bot2.user_id = "222222"
        bot2.log = MagicMock()
        cog2 = StrategyEngine(bot2)

        # Verify state file paths are isolated
        expected_file1 = os.path.join(temp_base_dir, "data", "strategy_state_111111.json")
        expected_file2 = os.path.join(temp_base_dir, "data", "strategy_state_222222.json")
        assert cog1.state_file == expected_file1
        assert cog2.state_file == expected_file2
        assert cog1.state_file != cog2.state_file

        # Mutate cog1 state
        cog1.current_team_animals = [OwnedAnimal(name="lion", level=50)]
        cog1.current_team_weapons = [OwnedWeapon(id="W111", weapon_name="Great Sword")]
        cog1.current_shards = 1111
        cog1._save_state()

        # Mutate cog2 state
        cog2.current_team_animals = [OwnedAnimal(name="wolf", level=40)]
        cog2.current_team_weapons = [OwnedWeapon(id="W222", weapon_name="Healing Staff")]
        cog2.current_shards = 2222
        cog2._save_state()

        # Verify both distinct files exist on disk
        assert os.path.exists(expected_file1)
        assert os.path.exists(expected_file2)

        # Verify content isolation without data pollution or collisions
        with open(expected_file1, "r", encoding="utf-8") as f:
            data1 = json.load(f)
        with open(expected_file2, "r", encoding="utf-8") as f:
            data2 = json.load(f)

        assert data1["current_shards"] == 1111
        assert data1["team"]["animals"][0]["name"] == "lion"
        assert data1["team"]["weapons"][0]["id"] == "W111"

        assert data2["current_shards"] == 2222
        assert data2["team"]["animals"][0]["name"] == "wolf"
        assert data2["team"]["weapons"][0]["id"] == "W222"

    def test_database_sanitization(self, temp_base_dir):
        from cogs.strategy_engine import StrategyEngine
        from owo_strategy.schemas.models import OwnedAnimal, OwnedWeapon

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_base_dir
        cog = StrategyEngine(bot)

        # Contaminate inventory with tier names and non-weapon words
        cog.inventory_animals = [
            OwnedAnimal(name="common"),
            OwnedAnimal(name="uncommon"),
            OwnedAnimal(name="rare"),
            OwnedAnimal(name="epic"),
            OwnedAnimal(name="mythic"),
            OwnedAnimal(name="legendary"),
            OwnedAnimal(name="lion"),
            OwnedAnimal(name="tiger"),
        ]
        cog.inventory_weapons = [
            OwnedWeapon(id="COOKIE", weapon_name="Unknown Weapon"),
            OwnedWeapon(id="CUDDLE", weapon_name="Unknown Weapon"),
            OwnedWeapon(id="SHIP", weapon_name="Unknown Weapon"),
            OwnedWeapon(id="PRAY", weapon_name="Unknown Weapon"),
            OwnedWeapon(id="101", weapon_name="Defender's Aegis"),
            OwnedWeapon(id="104", weapon_name="Healing Staff"),
        ]

        cog.sanitize_inventories()

        # Verify tier names are stripped from inventory_animals
        animal_names = [a.name.lower() for a in cog.inventory_animals]
        assert "common" not in animal_names
        assert "mythic" not in animal_names
        assert "rare" not in animal_names
        assert "epic" not in animal_names
        assert "lion" in animal_names
        assert "tiger" in animal_names

        # Verify non-weapon words are stripped from inventory_weapons
        weapon_ids = [w.id.upper() for w in cog.inventory_weapons]
        assert "COOKIE" not in weapon_ids
        assert "CUDDLE" not in weapon_ids
        assert "SHIP" not in weapon_ids
        assert "PRAY" not in weapon_ids
        assert "101" in weapon_ids
        assert "104" in weapon_ids

    def test_load_state_auto_sanitization(self, temp_base_dir):
        from cogs.strategy_engine import StrategyEngine

        state_path = os.path.join(temp_base_dir, "data", "strategy_state.json")
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        contaminated_data = {
            "team": {"animals": [], "weapons": []},
            "inventory_animals": [
                {"name": "common", "level": 50},
                {"name": "mythic", "level": 50},
                {"name": "lion", "level": 50},
            ],
            "inventory_weapons": [
                {"id": "COOKIE", "weapon_name": "Unknown Weapon"},
                {"id": "CUDDLE", "weapon_name": "Unknown Weapon"},
                {"id": "101", "weapon_name": "Defender's Aegis"},
            ],
            "current_shards": 650,
            "last_updated": time.time(),
        }
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(contaminated_data, f)

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_base_dir
        cog = StrategyEngine(bot)

        # Verify auto-sanitization on load
        animal_names = [a.name.lower() for a in cog.inventory_animals]
        weapon_ids = [w.id.upper() for w in cog.inventory_weapons]

        assert "common" not in animal_names
        assert "mythic" not in animal_names
        assert "lion" in animal_names
        assert "COOKIE" not in weapon_ids
        assert "CUDDLE" not in weapon_ids
        assert "101" in weapon_ids

    @pytest.mark.asyncio
    async def test_setup_entrypoint(self, temp_base_dir):
        from cogs.strategy_engine import setup

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_base_dir

        await setup(bot)
        assert bot.get_cog("StrategyEngine") is not None


# =============================================================================
# 3. Discord Message Listeners & Simulated Telemetry
# =============================================================================
class TestStrategyMessageListeners:
    """Test telemetry ingestion from simulated Discord messages and triggers."""

    @pytest.fixture
    def cog_instance(self):
        from cogs.strategy_engine import StrategyEngine

        temp_dir = tempfile.mkdtemp(prefix="neura_listener_test_")
        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_dir
        bot.owo_bot_id = str(OWO_BOT_ID)
        bot.log = MagicMock()

        cog = StrategyEngine(bot)
        yield cog
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_on_message_owo_team_ingestion(self, cog_instance):
        raw_team = """
⚔️ **<@746723893229912165>'s Battle Team**
[1] <:glion:418284974593277954> Lion (Lvl 50) - Weapon: Great Sword [664DFC]
[2] <:gowl:418284974593277954> Owl (Lvl 48) - Weapon: Healing Staff [A1B2C3]
[3] <:gwolf:418284974593277954> Wolf (Lvl 45) - Weapon: None
"""
        msg = MockMessage(content=raw_team, author=MockAuthor(OWO_BOT_ID))
        await cog_instance.on_message(msg)

        team_names = [a.name for a in cog_instance.current_team_animals]
        assert "lion" in team_names
        assert "owl" in team_names
        assert "wolf" in team_names

        w_ids = [w.id for w in cog_instance.current_team_weapons]
        assert "664DFC" in w_ids
        assert "A1B2C3" in w_ids

    @pytest.mark.asyncio
    async def test_on_message_owo_weapon_inv_ingestion(self, cog_instance):
        raw_inv = """
__**Your Weapons**__ (Page 1/2)
`664DFC` 95.5% Pristine Great Sword
`B102` 78.2% Worn Empowered Club
`556677` 88.0% Fine Bow
"""
        msg = MockMessage(content=raw_inv, author=MockAuthor(OWO_BOT_ID))
        await cog_instance.on_message(msg)

        inv_ids = {w.id for w in cog_instance.inventory_weapons}
        assert "664DFC" in inv_ids
        assert "B102" in inv_ids
        assert "556677" in inv_ids

    @pytest.mark.asyncio
    async def test_on_message_owo_weapon_inspect_ingestion(self, cog_instance):
        raw_inspect = """
**Heather's Pristine Great Sword**
**Name:** Great Sword
**Owner:** Heather
**ID:** `999AAA`
**Quality:** 100.0%
**Wear:** Pristine
**WP Cost:** 100
**Passives:**
- Mana Tap: 77% (Roll: 77/100)
**Rolls:** 31, 7, 77
"""
        msg = MockMessage(content=raw_inspect, author=MockAuthor(OWO_BOT_ID))
        await cog_instance.on_message(msg)

        inv_ids = {w.id for w in cog_instance.inventory_weapons}
        assert "999AAA" in inv_ids
        target_w = next(w for w in cog_instance.inventory_weapons if w.id == "999AAA")
        assert target_w.quality_val == 100.0
        assert target_w.wear == "pristine"

    @pytest.mark.asyncio
    async def test_on_message_edit_telemetry_flow(self, cog_instance):
        before = MockMessage(content="Loading battle team...", author=MockAuthor(OWO_BOT_ID))
        after_embed = MockEmbed(
            title="⚔️ Your Battle Team",
            fields=[
                MockField("Position 1: Dino", "Lvl: 50\nWeapon: Defender's Aegis (`D111`)"),
                MockField("Position 2: Snake", "Lvl: 50\nWeapon: Poison Dagger (`D222`)"),
                MockField("Position 3: Cow", "Lvl: 50\nWeapon: None"),
            ]
        )
        after = MockMessage(embeds=[after_embed], author=MockAuthor(OWO_BOT_ID))

        await cog_instance.on_message_edit(before, after)

        team_names = [a.name for a in cog_instance.current_team_animals]
        assert "dino" in team_names
        assert "snake" in team_names
        assert "cow" in team_names

    @pytest.mark.asyncio
    async def test_on_message_unauthorized_author_rejected(self, cog_instance):
        initial_team = list(cog_instance.current_team_animals)
        raw_team = """
⚔️ **<@746723893229912165>'s Battle Team**
[1] <:glion:418284974593277954> Lion (Lvl 50) - Weapon: Great Sword [664DFC]
"""
        fake_msg = MockMessage(content=raw_team, author=MockAuthor(123456789, name="ImpostorBot"))
        await cog_instance.on_message(fake_msg)

        assert cog_instance.current_team_animals == initial_team

    @pytest.mark.asyncio
    async def test_user_chat_command_eval_trigger(self, cog_instance):
        channel = MockChannel()
        cmd_msg = MockMessage(content="!owo-eval", author=MockAuthor(746723893229912165, name="Player", bot=False), channel=channel)

        await cog_instance.on_message(cmd_msg)

        assert len(channel.sent_messages) == 1
        reply = channel.sent_messages[0].content
        assert "OwO Strategy Engine — Team Evaluation" in reply
        assert "Total Team EHP:" in reply
        assert "Benchmark Win Rate:" in reply

    @pytest.mark.asyncio
    async def test_user_chat_command_shards_trigger(self, cog_instance):
        channel = MockChannel()
        cmd_msg = MockMessage(content="owo shards", author=MockAuthor(746723893229912165, name="Player", bot=False), channel=channel)

        await cog_instance.on_message(cmd_msg)

        assert len(channel.sent_messages) == 1
        reply = channel.sent_messages[0].content
        assert "OwO Strategy Engine — Weapon Shard Dismantle Plan" in reply
        assert "dry_run = True" in reply
        assert "Protected Weapons:" in reply

    @pytest.mark.asyncio
    async def test_user_chat_command_equip_trigger(self, cog_instance):
        cog_instance.bot.neura_enqueue = AsyncMock()
        cog_instance.bot.get_cmd_priority = MagicMock(return_value=2)
        channel = MockChannel()
        cmd_msg = MockMessage(
            content="!owo-equip",
            author=MockAuthor(746723893229912165, name="Player", bot=False),
            channel=channel,
        )

        await cog_instance.on_message(cmd_msg)

        assert len(channel.sent_messages) == 1
        reply = channel.sent_messages[0].content
        assert "OwO Strategy Engine — Team Auto-Equip" in reply or "Team Auto-Equipped" in reply
        assert "owo team" in reply
        assert "owo weapon" in reply
        assert cog_instance.bot.neura_enqueue.await_count >= 3
        for call in cog_instance.bot.neura_enqueue.await_args_list:
            prio = call.kwargs.get("priority", call.args[1] if len(call.args) > 1 else None)
            assert prio is not None and prio <= 2


# =============================================================================
# 4. Strategy Engine Optimization & Simulation Pipeline Execution
# =============================================================================
class TestOptimizationPipeline:
    """Validate full pipeline: team evaluation, 3-stage optimization, boss raid, and shard safety."""

    @pytest.fixture
    def cog_engine(self):
        from cogs.strategy_engine import StrategyEngine

        temp_dir = tempfile.mkdtemp(prefix="neura_opt_test_")
        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_dir
        cog = StrategyEngine(bot)
        yield cog
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_evaluate_team_metrics(self, cog_engine):
        eval_data = cog_engine.evaluate_team()

        assert eval_data["is_valid"] is True
        assert eval_data["frontline_ehp"] > 0
        assert eval_data["total_team_ehp"] > 0
        assert 0.0 <= eval_data["win_rate"] <= 100.0
        assert isinstance(eval_data["wilson_ci"], (list, tuple))
        assert len(eval_data["wilson_ci"]) == 2
        assert len(eval_data["pet_breakdown"]) == 3
        for pet in eval_data["pet_breakdown"]:
            assert "animal" in pet
            assert "ehp_physical" in pet
            assert "is_solvent" in pet

    def test_run_optimization_tournament(self, cog_engine):
        result, md_report, json_report = cog_engine.run_optimization(coarse_seeds=3, fine_seeds=6)

        assert result is not None
        assert result.winner is not None
        assert len(result.winner.animal_names) == 3
        assert len(result.winner.weapon_names) == 3
        assert 0.0 <= result.winner.fine_win_rate <= 1.0
        assert result.total_simulations > 0

        # Reports
        assert isinstance(md_report, str)
        assert len(md_report) > 0
        assert isinstance(json_report, dict)
        assert "recommended_team" in json_report or "winner" in json_report

    def test_run_boss_simulation(self, cog_engine):
        report = cog_engine.run_boss_simulation(preset_name="standard_cleave", seeds_count=3)

        assert "boss_name" in report
        assert report["boss_name"] == "Abyssal Behemoth"
        assert report["avg_damage_dealt"] > 0
        assert 0.0 <= report["avg_turns_survived"] <= 24.0
        assert report["composite_score"] >= 0

    def test_run_shard_planner_strict_safety(self, cog_engine):
        plan = cog_engine.run_shard_planner()

        assert plan.dry_run is True
        assert plan.current_shards == cog_engine.current_shards
        assert plan.projected_shards_gained >= 0
        assert len(plan.protected_weapons) >= 3

        # Active team weapons MUST be protected
        active_ids = {w.id for w in cog_engine.current_team_weapons}
        dismantle_ids = {w.id for w in plan.safe_to_dismantle}
        assert active_ids.isdisjoint(dismantle_ids), "Active weapons found in safe_to_dismantle list!"


# =============================================================================
# 5. Dashboard Flask API Endpoints
# =============================================================================
class TestDashboardApiEndpoints:
    """Test Flask REST API routes in dashboard/app.py using Flask test client."""

    @pytest.fixture
    def client(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_api_strategy_state_endpoint(self, client):
        resp = client.get("/api/strategy/state")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["dry_run"] is True
        assert "state" in data
        assert "team" in data
        assert "inventory_animals" in data
        assert "inventory_weapons" in data
        assert "evaluation" in data
        assert "is_valid" in data["evaluation"]

    def test_api_strategy_optimize_endpoint(self, client):
        payload = {"coarse_seeds": 2, "fine_seeds": 4}
        resp = client.post("/api/strategy/optimize", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "winner" in data
        assert len(data["winner"]["animals"]) == 3
        assert len(data["winner"]["weapons"]) == 3
        assert "frontline_ehp" in data["winner"]
        assert "animal_details" in data["winner"]
        assert "weapon_details" in data["winner"]
        assert "in_game_commands" in data
        assert len(data["in_game_commands"]) >= 3
        assert "report" in data
        assert "markdown_report" in data

    def test_api_strategy_boss_endpoint(self, client):
        payload = {"preset": "standard_cleave", "seeds": 2}
        resp = client.post("/api/strategy/boss", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["boss_name"] == "Abyssal Behemoth"
        assert data["avg_damage_dealt"] > 0
        assert "composite_score" in data

    def test_api_strategy_shards_endpoint(self, client):
        payload = {"current_shards": 500}
        resp = client.post("/api/strategy/shards", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["dry_run"] is True
        assert data["plan"]["current_shards"] == 500
        assert "batch_commands" in data["plan"]
        assert "safe_to_dismantle_count" in data["plan"]

    def test_api_strategy_equip_endpoint(self, client):
        payload = {"coarse_seeds": 2, "fine_seeds": 4}
        resp = client.post("/api/strategy/equip", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "queued_commands" in data
        assert isinstance(data["queued_commands"], list)
        assert len(data["queued_commands"]) >= 3
        assert any("owo team" in cmd for cmd in data["queued_commands"])
        assert any("owo weapon" in cmd for cmd in data["queued_commands"])
        assert "estimated_duration_seconds" in data
        assert data["estimated_duration_seconds"] >= 12

    def test_api_strategy_dismantle_endpoint(self, client):
        payload = {"current_shards": 500}
        resp = client.post("/api/strategy/dismantle", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["dry_run"] is True
        assert "dismantle_commands" in data
        assert isinstance(data["dismantle_commands"], list)
        assert "weapons_count" in data
        assert "projected_shards" in data


# =============================================================================
# 6. Core NeuraSelf Regression Guard
# =============================================================================
class TestNeuraSelfCoreRegression:
    """Ensure core NeuraSelf cogs and architecture functions remain intact."""

    def test_import_core_cogs_cleanly(self):
        import cogs.auto_open as auto_open_mod
        import cogs.boss as boss_mod
        import cogs.gambling as gambling_mod
        import cogs.grinding as grinding_mod
        import cogs.reactionbot as reactionbot_mod
        import cogs.security as security_mod
        import core.bot as core_bot_mod
        import core.state as core_state_mod

        assert hasattr(gambling_mod, "Gambling")
        assert hasattr(reactionbot_mod, "ReactionBot")
        assert hasattr(grinding_mod, "Grinding")
        assert hasattr(auto_open_mod, "AutoOpen")
        assert hasattr(boss_mod, "Boss")
        assert hasattr(security_mod, "Security")
        assert hasattr(core_bot_mod, "NeuraBot")
        assert hasattr(core_state_mod, "stats")
        assert hasattr(core_state_mod, "log_command")

    @pytest.mark.asyncio
    async def test_cogs_coexistence_with_strategy_engine(self):
        from cogs.auto_open import AutoOpen
        from cogs.gambling import Gambling
        from cogs.grinding import Grinding
        from cogs.reactionbot import ReactionBot
        from cogs.strategy_engine import StrategyEngine

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bot.config = {"accounts": []}

        gambling_cog = Gambling(bot)
        reaction_cog = ReactionBot(bot)
        grinding_cog = Grinding(bot)
        auto_open_cog = AutoOpen(bot)
        strategy_cog = StrategyEngine(bot)

        await bot.add_cog(gambling_cog)
        await bot.add_cog(reaction_cog)
        await bot.add_cog(grinding_cog)
        await bot.add_cog(auto_open_cog)
        await bot.add_cog(strategy_cog)

        assert bot.get_cog("Gambling") is not None
        assert bot.get_cog("ReactionBot") is not None
        assert bot.get_cog("Grinding") is not None
        assert bot.get_cog("AutoOpen") is not None
        assert bot.get_cog("StrategyEngine") is not None

    def test_core_bot_maps_strategy_in_cogs_for_config_changes(self):
        from core.bot import NeuraBot

        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bot.config = {"commands": {}}

        # Test mapping for commands.strategy
        cogs_from_cmd = NeuraBot._cogs_for_config_changes(bot, ["commands.strategy"])
        assert "StrategyEngine" in cogs_from_cmd

        # Test mapping for top-level strategy
        cogs_from_top = NeuraBot._cogs_for_config_changes(bot, ["strategy"])
        assert "StrategyEngine" in cogs_from_top

        # Test mapping for nested path
        cogs_from_nested = NeuraBot._cogs_for_config_changes(bot, ["strategy.interval"])
        assert "StrategyEngine" in cogs_from_nested

        # Verify pruning rules include strategy
        bot.cmd_states = {"strategy": {"in_queue": False}}
        bot.config = {"strategy": {"enabled": False}, "commands": {"strategy": {"enabled": False}}}
        NeuraBot._prune_disabled_scheduler_cmds(bot)
        assert "strategy" not in bot.cmd_states


# =============================================================================
# 7. Autopilot Loop, Auto-Equipping, and Scheduler Hook Tests
# =============================================================================
class TestStrategyAutopilotAndAutoEquip:
    """Validate register_actions, _autopilot_tick, !owo-equip, and shard execution guardrails."""

    @pytest.fixture
    def mock_scheduler_bot(self):
        temp_dir = tempfile.mkdtemp(prefix="neura_scheduler_test_")
        bot = commands.Bot(command_prefix="!", self_bot=True)
        bot.base_dir = temp_dir
        bot.owo_bot_id = str(OWO_BOT_ID)
        bot.log = MagicMock()
        bot.cmd_states = {}
        bot.enqueued_commands = []

        async def fake_enqueue(cmd, priority=3, **kwargs):
            bot.enqueued_commands.append((cmd, priority))

        async def fake_register(cmd_id, content, priority, delay, initial_offset=0):
            bot.cmd_states[cmd_id] = {
                "content": content,
                "priority": priority,
                "delay": delay,
                "initial_offset": initial_offset,
                "last_ran": time.time(),
                "in_queue": False,
            }

        bot.neura_enqueue = fake_enqueue
        bot.neura_register_command = fake_register
        bot.config = {
            "strategy": {
                "enabled": True,
                "interval": [3600, 7200],
                "auto_equip": True,
                "auto_dismantle": False,
                "dry_run": False,
                "dismantle_quality_threshold": 40.0,
                "protect_quality_threshold": 80.0,
                "boss_raid_solver": True,
            }
        }
        yield bot
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_register_actions_registers_with_scheduler(self, mock_scheduler_bot):
        from cogs.strategy_engine import StrategyEngine

        cog = StrategyEngine(mock_scheduler_bot)
        await cog.register_actions()

        assert cog.enabled is True
        assert cog.auto_equip is True
        assert cog.auto_dismantle is False
        assert cog.dry_run is False
        assert cog.dismantle_quality_threshold == 40.0
        assert cog.protect_quality_threshold == 80.0
        assert cog.boss_raid_solver is True

        assert "strategy" in mock_scheduler_bot.cmd_states
        state = mock_scheduler_bot.cmd_states["strategy"]
        assert state["priority"] == 4
        assert state["initial_offset"] == 20
        assert 3600 <= state["delay"] <= 7200
        assert state["content"] == cog._autopilot_tick

    @pytest.mark.asyncio
    async def test_register_actions_disabled_removes_from_scheduler(self, mock_scheduler_bot):
        from cogs.strategy_engine import StrategyEngine

        mock_scheduler_bot.config["strategy"]["enabled"] = False
        mock_scheduler_bot.cmd_states["strategy"] = {"dummy": True}

        cog = StrategyEngine(mock_scheduler_bot)
        await cog.register_actions()

        assert cog.enabled is False
        assert "strategy" not in mock_scheduler_bot.cmd_states

    @pytest.mark.asyncio
    async def test_autopilot_tick_auto_equips_6_commands(self, mock_scheduler_bot):
        from cogs.strategy_engine import StrategyEngine

        cog = StrategyEngine(mock_scheduler_bot)
        await cog.register_actions()
        mock_scheduler_bot.enqueued_commands.clear()

        await cog._autopilot_tick()

        # Check enqueued commands: team add/remove commands + weapon equip commands
        enqueued_cmds = [cmd for cmd, prio in mock_scheduler_bot.enqueued_commands]
        team_cmds = [c for c in enqueued_cmds if c.startswith("owo team add ") or c.startswith("owo team remove ")]
        weapon_cmds = [c for c in enqueued_cmds if c.startswith("owo weapon ") and not c.startswith("owo weapon inv")]

        assert len(team_cmds) == 3
        assert len(weapon_cmds) == 3
        assert any(c == "owo team" for c in enqueued_cmds)

        assert any("giraffbot" in c for c in team_cmds)
        assert any("eagle" in c for c in team_cmds)
        assert any("lion" in c for c in team_cmds)
        assert any("giraffbot" in c for c in weapon_cmds)

        # Verify STRATEGY log entry was emitted
        strategy_logs = [call for call in mock_scheduler_bot.log.call_args_list if call[0][0] == "STRATEGY"]
        assert len(strategy_logs) >= 1
        assert any("Autopilot: Enqueued" in str(call) for call in strategy_logs)

    @pytest.mark.asyncio
    async def test_autopilot_tick_auto_dismantle_when_enabled_and_not_dry_run(self, mock_scheduler_bot):
        from cogs.strategy_engine import StrategyEngine

        mock_scheduler_bot.config["strategy"]["auto_dismantle"] = True
        mock_scheduler_bot.config["strategy"]["dry_run"] = False
        cog = StrategyEngine(mock_scheduler_bot)
        await cog.register_actions()
        mock_scheduler_bot.enqueued_commands.clear()

        await cog._autopilot_tick()

        enqueued_cmds = [cmd for cmd, prio in mock_scheduler_bot.enqueued_commands]
        dismantle_cmds = [c for c in enqueued_cmds if c.startswith("owo dismantle ")]
        assert len(dismantle_cmds) >= 1
        # Low quality weapons from default fallback (e.g. 201, 202, 203) should be dismantled
        assert any("201" in c for c in dismantle_cmds)

    @pytest.mark.asyncio
    async def test_cmd_equip_on_demand(self, mock_scheduler_bot):
        from cogs.strategy_engine import StrategyEngine

        cog = StrategyEngine(mock_scheduler_bot)
        await cog.register_actions()
        mock_scheduler_bot.enqueued_commands.clear()

        channel = MockChannel()
        await cog._cmd_equip(channel)

        enqueued_cmds = [cmd for cmd, prio in mock_scheduler_bot.enqueued_commands]
        assert len(enqueued_cmds) >= 6
        assert len(channel.sent_messages) == 1
        reply = channel.sent_messages[0].content
        assert "OwO Strategy Engine — Team Auto-Equipped" in reply
        assert "Enqueued" in reply

    @pytest.mark.asyncio
    async def test_cmd_shards_with_dry_run_false_and_confirm(self, mock_scheduler_bot):
        from cogs.strategy_engine import StrategyEngine

        mock_scheduler_bot.config["strategy"]["dry_run"] = False
        cog = StrategyEngine(mock_scheduler_bot)
        await cog.register_actions()
        mock_scheduler_bot.enqueued_commands.clear()

        channel = MockChannel()
        await cog._cmd_shards(channel, args="confirm")

        assert len(channel.sent_messages) == 1
        reply = channel.sent_messages[0].content
        assert "EXECUTION MODE:" in reply
        dismantle_cmds = [c for c, _ in mock_scheduler_bot.enqueued_commands if c.startswith("owo dismantle ")]
        assert len(dismantle_cmds) >= 1

    @pytest.mark.asyncio
    async def test_cmd_shards_dry_run_true_safety(self, mock_scheduler_bot):
        from cogs.strategy_engine import StrategyEngine

        mock_scheduler_bot.config["strategy"]["dry_run"] = True
        cog = StrategyEngine(mock_scheduler_bot)
        await cog.register_actions()
        mock_scheduler_bot.enqueued_commands.clear()

        channel = MockChannel()
        await cog._cmd_shards(channel, args="confirm")

        assert len(channel.sent_messages) == 1
        reply = channel.sent_messages[0].content
        assert "SAFETY MODE:" in reply
        assert "dry_run = True" in reply
        # No commands should be enqueued when dry_run is True
        assert len(mock_scheduler_bot.enqueued_commands) == 0

