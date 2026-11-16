"""Tests for OwO pagination, Discord interaction button clicking, and NeonUtil calculator ingestion."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from owo_strategy.ingestion.neon_parser import (
    parse_neon_calculation_message,
)
from owo_strategy.ingestion.owo_parser import (
    ParsedWeaponInv,
    parse_owo_message,
    parse_owo_weapon_inv,
)
from owo_strategy.optimizer.shard_planner import (
    DismantlePlan,
    ShardPlanner,
)
from owo_strategy.schemas.models import OwnedWeapon
from component_v2_neura.interactions import InteractionManager


SAMPLE_NEON_CALC_EMBED = {
    "author": {"name": "Max qualities for 15 weapons"},
    "description": (
        "🔹 <:epstaff:1083871544931012749><:ratt:1005320984624107591> `G7KEF8`<:max_possible:1064755333484007535> — <:epic:1132373271682220092> `75.8%` 🔐💀\n"
        "🔹 <:rgreatsword:1004937877475565629><:ugslay:1464071613099278346> `G7KEF7`<:max_possible:1064755333484007535> — <:mythic:1132373272651108423> `85.7%` \n"
        "🔹 <:eascept:1004940269038346251><:emag:1005321087015452732> `G7KEF6`<:max_possible:1064755333484007535> — <:mythic:1132373272651108423> `89.7%` 🔐\n"
        "🔹 <:effish:1155693540718952448><:usprout:1005327739106111538> `G7KEF5`<:max_possible:1064755333484007535> — <:mythic:1132373272651108423> `88.0%` \n"
        "🔹 <:rbgaz:1482147130197020702><:rmr:1005326412682633247> `G7JMQ3`<:max_possible:1064755333484007535> — <:epic:1132373271682220092> `69.1%` <:ws:1132387235975667813>\n"
        "🔹 <:cgaxe:1004940378455150703><:uthorns:1005326580626755675> `G7JMPZ`<:max_possible:1064755333484007535> — <:uncommon:1132373268796538882> `34.7%` <a:0_min_quality:1160267235479265413>\n"
    ),
}

SAMPLE_OWO_WEAPON_MSG_PAGE1 = {
    "id": "1571590242065195009",
    "channel_id": "1571415709362163833",
    "author": {"id": "408785106942164992", "username": "OwO"},
    "content": "",
    "components": [
        {
            "type": 17,
            "components": [
                {
                    "type": 10,
                    "content": (
                        "`ID` `Quality` `Wear` `Weapon`\n"
                        "`G7KEF8` ` 61.0%` `worn` Staff of Purity\n"
                        "`G7KEF7` ` 59.3%` `worn` Great Sword\n"
                        "`G7KEF6` ` 76.6%` `worn` Arcane Scepter\n"
                    ),
                },
                {
                    "type": 1,
                    "components": [
                        {"type": 2, "custom_id": "paged_prev", "disabled": True},
                        {"type": 2, "custom_id": "noop", "label": "1/2", "disabled": True},
                        {"type": 2, "custom_id": "paged_next", "disabled": False},
                    ],
                },
            ],
        }
    ],
    "reactions": [
        {"emoji": {"id": "1263895039172677692", "name": "calculate", "animated": True}, "count": 1}
    ],
}


class TestPaginationExtraction:
    def test_extract_noop_label_pagination(self):
        res = parse_owo_weapon_inv(SAMPLE_OWO_WEAPON_MSG_PAGE1)
        assert res is not None
        assert res.current_page == 1
        assert res.total_pages == 2
        assert res.has_next_page is True
        assert len(res.weapons) == 3
        assert res.weapons[0].weapon_id == "G7KEF8"

    def test_single_page_inventory_has_no_next_page(self):
        msg = {
            "content": (
                "`ID` `Quality` `Wear` `Weapon`\n"
                "`G7KEF8` ` 61.0%` `worn` Staff of Purity\n"
                "Page 1 of 1"
            )
        }
        res = parse_owo_weapon_inv(msg)
        assert res is not None
        assert res.current_page == 1
        assert res.total_pages == 1
        assert res.has_next_page is False


class TestNeonCalculationParser:
    def test_parse_neon_calculation_embed(self):
        weapons = parse_neon_calculation_message(SAMPLE_NEON_CALC_EMBED)
        assert len(weapons) == 6

        # Check G7KEF8
        w8 = next(w for w in weapons if w.id == "G7KEF8")
        assert w8.weapon_name == "Staff of Purity"
        assert w8.quality_val == 75.8
        assert w8.quality_is_exact is True
        assert "str" in w8.passives
        assert w8.is_locked is True
        assert w8.is_dismantle_candidate is True
        assert w8.is_shard_candidate is True

        # Check G7KEF7
        w7 = next(w for w in weapons if w.id == "G7KEF7")
        assert w7.weapon_name == "Great Sword"
        assert w7.quality_val == 85.7
        assert "gslay" in w7.passives
        assert w7.is_locked is False

        # Check G7JMPZ (scrap candidate)
        wz = next(w for w in weapons if w.id == "G7JMPZ")
        assert wz.weapon_name == "Glacial Axe"
        assert wz.quality_val == 34.7
        assert wz.is_dismantle_candidate is True
        assert wz.is_shard_candidate is True


class TestShardPlannerProtectionWithNeon:
    def test_locked_weapon_is_protected_regardless_of_quality(self):
        w_low_but_locked = OwnedWeapon(
            id="WLOCK1",
            weapon_name="Glacial Axe",
            quality_val=25.0,  # below 40% dismantle threshold
            is_locked=True,    # marked with 🔐 by Neon
        )
        w_scrap = OwnedWeapon(
            id="WSCRAP",
            weapon_name="Glacial Axe",
            quality_val=30.0,
            is_locked=False,
            is_dismantle_candidate=True,
        )

        planner = ShardPlanner(quality_dismantle_threshold=40.0, quality_protect_threshold=80.0)
        plan = planner.generate_plan([w_low_but_locked, w_scrap])

        # w_low_but_locked must be protected
        assert any(w.id == "WLOCK1" for w in plan.protected_weapons)
        assert not any(w.id == "WLOCK1" for w in plan.safe_to_dismantle)

        # w_scrap must be safe to dismantle
        assert any(w.id == "WSCRAP" for w in plan.safe_to_dismantle)


class TestInteractionManagerFix:
    @pytest.mark.asyncio
    async def test_click_button_session_id_resolution(self):
        bot = MagicMock()
        bot.token = "mock-token"
        bot._connection = MagicMock()
        bot._connection.session_id = "real-gateway-session-123"
        bot.ws = MagicMock()
        # Ensure hasattr(bot.ws, 'session_id') is False to reproduce previous bug
        del bot.ws.session_id

        im = InteractionManager(bot)

        with patch.object(im, "_get_headers", AsyncMock(return_value={"Authorization": "mock"})), \
             patch("aiohttp.ClientSession.post") as mock_post:
            
            mock_resp = MagicMock()
            mock_resp.status = 204
            mock_post.return_value.__aenter__.return_value = mock_resp

            # Should not raise AttributeError and use the real session_id
            success = await im.click_button_raw(
                custom_id="paged_next",
                message_id=123,
                channel_id=456,
                author_id=789,
            )
            assert success is True
            payload = mock_post.call_args[1]["json"]
            assert payload["session_id"] == "real-gateway-session-123"
            assert payload["data"]["custom_id"] == "paged_next"


class TestStrategyEngineTelemetryPaginationAndNeon:
    @pytest.mark.skip(reason="StrategyEngine paused (Coming Soon)")
    @pytest.mark.asyncio
    async def test_owo_weapon_inventory_with_pagination_and_calculate(self, tmp_path):
        from cogs.strategy_engine import StrategyEngine

        bot = MagicMock()
        bot.base_dir = str(tmp_path)
        bot.user_id = "1451414972377862228"
        bot.log = MagicMock()
        bot.neura_enqueue = AsyncMock()
        bot.interactions = MagicMock()
        bot.interactions.click_button = AsyncMock(return_value=True)

        cog = StrategyEngine(bot)

        # Mock Page 1 message from OwO
        msg1 = MagicMock()
        msg1.id = 1571590242065195009
        msg1.channel = MagicMock()
        msg1.channel.id = 1571415709362163833
        msg1.author = MagicMock()
        msg1.author.id = 408785106942164992
        msg1.author.name = "OwO"
        msg1.content = ""
        msg1.reactions = []
        msg1.add_reaction = AsyncMock()
        msg1.flags = MagicMock()
        msg1.flags.value = 0

        # Component v2 with paged_next and noop "1/2"
        btn_next = MagicMock()
        btn_next.custom_id = "paged_next"
        btn_next.disabled = False
        btn_noop = MagicMock()
        btn_noop.custom_id = "noop"
        btn_noop.label = "1/2"
        btn_noop.disabled = True

        row = MagicMock()
        row.children = [btn_noop, btn_next]
        container = MagicMock()
        container.content = (
            "`ID` `Quality` `Wear` `Weapon`\n"
            "`G7KEF8` ` 61.0%` `worn` Staff of Purity\n"
            "`G7KEF7` ` 59.3%` `worn` Great Sword\n"
        )
        container.children = [row]
        msg1.components = [container]

        with patch.object(cog, "_trigger_calculate_reaction", AsyncMock()) as mock_calc, \
             patch.object(cog, "_advance_weapon_page", AsyncMock()) as mock_adv:
            await cog.on_message(msg1)

        # 1. Page 1 weapons ingested
        assert len(cog.inventory_weapons) == 2
        assert any(w.id == "G7KEF8" for w in cog.inventory_weapons)
        assert any(w.id == "G7KEF7" for w in cog.inventory_weapons)

        # 2. Page 2 advancement and calculate reaction were scheduled
        mock_adv.assert_called_once_with(msg1, 1, 2)
        mock_calc.assert_called_once_with(msg1)

        # 3. Test _advance_weapon_page directly with mocked sleep
        with patch("cogs.strategy_engine.asyncio.sleep", AsyncMock()):
            await cog._advance_weapon_page(msg1, 1, 2)
        bot.interactions.click_button.assert_awaited_with("paged_next", msg1)

        # 4. Test _trigger_calculate_reaction directly with mocked sleep
        with patch("cogs.strategy_engine.asyncio.sleep", AsyncMock()):
            await cog._trigger_calculate_reaction(msg1)
        msg1.add_reaction.assert_awaited()

        # 5. Now simulate Page 2 arrival (message edit)
        msg2 = MagicMock()
        msg2.id = 1571590242065195009
        msg2.channel = msg1.channel
        msg2.author = msg1.author
        msg2.reactions = []
        msg2.add_reaction = AsyncMock()
        msg2.flags = msg1.flags

        btn_noop2 = MagicMock()
        btn_noop2.custom_id = "noop"
        btn_noop2.label = "2/2"
        btn_noop2.disabled = True
        row2 = MagicMock()
        row2.children = [btn_noop2]

        container2 = MagicMock()
        container2.content = (
            "`ID` `Quality` `Wear` `Weapon`\n"
            "`G7KEF6` ` 76.6%` `worn` Arcane Scepter\n"
            "`G7KEF5` ` 68.2%` `worn` Foul Fish\n"
        )
        container2.children = [row2]
        msg2.components = [container2]

        with patch.object(cog, "_trigger_calculate_reaction", AsyncMock()), \
             patch.object(cog, "_advance_weapon_page", AsyncMock()):
            await cog.on_message_edit(msg1, msg2)

        # Verify weapons from both Page 1 and Page 2 are present (accumulated!)
        assert len(cog.inventory_weapons) == 4
        assert {w.id for w in cog.inventory_weapons} == {"G7KEF8", "G7KEF7", "G7KEF6", "G7KEF5"}

        # 6. Now simulate NeonUtil calculation response
        neon_msg = MagicMock()
        neon_msg.id = 1571590299999999999
        neon_msg.channel = msg1.channel
        neon_msg.author = MagicMock()
        neon_msg.author.id = 851436490415931422
        neon_msg.author.name = "NeonUtil"
        neon_msg.content = ""
        neon_msg.components = []

        neon_embed = MagicMock()
        neon_embed.author = MagicMock()
        neon_embed.author.name = "Max qualities for 15 weapons"
        neon_embed.description = (
            "🔹 <:epstaff:1083871544931012749><:ratt:1005320984624107591> `G7KEF8`<:max_possible:1064755333484007535> — <:epic:1132373271682220092> `75.8%` 🔐💀\n"
            "🔹 <:eascept:1004940269038346251><:emag:1005321087015452732> `G7KEF6`<:max_possible:1064755333484007535> — <:mythic:1132373272651108423> `89.7%` 🔐\n"
        )
        neon_embed.fields = []
        neon_embed.title = None
        neon_msg.embeds = [neon_embed]

        await cog.on_message(neon_msg)

        # Verify G7KEF8 enriched: quality updated from 61.0 -> 75.8, is_locked=True, is_dismantle_candidate=True
        enriched_g7 = next(w for w in cog.inventory_weapons if w.id == "G7KEF8")
        assert enriched_g7.quality_val == 75.8
        assert enriched_g7.quality_is_exact is True
        assert enriched_g7.is_locked is True
        assert enriched_g7.is_dismantle_candidate is True

        # Verify G7KEF6 enriched: quality updated from 76.6 -> 89.7, is_locked=True
        enriched_g6 = next(w for w in cog.inventory_weapons if w.id == "G7KEF6")
        assert enriched_g6.quality_val == 89.7
        assert enriched_g6.quality_is_exact is True
        assert enriched_g6.is_locked is True
