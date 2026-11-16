"""Unit tests for native OwO Discord message and embed parsers."""

import unittest
import pytest
import sys
import os

# Ensure neura-self workspace is on sys.path
sys.path.insert(0, "/home/xisense/neura-self")

from owo_strategy.ingestion.owo_parser import (
    OWO_BOT_ID,
    ParsedPassive,
    ParsedTeam,
    ParsedWeaponInspect,
    ParsedWeaponInv,
    ParsedZoo,
    TeamSlot,
    WeaponInvRow,
    ZooEntry,
    is_owo_bot,
    normalize_animal_name,
    normalize_weapon_name,
    parse_owo_message,
    parse_owo_team,
    parse_owo_weapon_inspect,
    parse_owo_weapon_inv,
    parse_owo_zoo,
)
from owo_strategy.schemas.models import OwnedAnimal, OwnedWeapon


# Helper Discord mock objects
class MockAuthor:
    def __init__(self, author_id: int | str, name: str = "OwO"):
        self.id = author_id
        self.name = name


class MockField:
    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value


class MockEmbed:
    def __init__(self, title: str = "", description: str = "", fields: list[MockField] | None = None, footer_text: str = ""):
        self.title = title
        self.description = description
        self.fields = fields or []
        self.footer = type("MockFooter", (), {"text": footer_text})() if footer_text else None


class MockMessage:
    def __init__(self, content: str = "", embeds: list[MockEmbed] | None = None, author: MockAuthor | None = None):
        self.content = content
        self.embeds = embeds or []
        self.author = author or MockAuthor(OWO_BOT_ID)


# ==============================================================================
# 1. Bot Verification Tests
# ==============================================================================

class TestBotVerification(unittest.TestCase):
    def test_official_owo_bot_id(self):
        assert is_owo_bot(408785106942164992) is True
        assert is_owo_bot("408785106942164992") is True
        assert is_owo_bot(MockAuthor(408785106942164992)) is True
        assert is_owo_bot({"id": "408785106942164992"}) is True

    def test_other_bot_rejected(self):
        assert is_owo_bot(123456789012345678) is False
        assert is_owo_bot("123456789012345678") is False
        assert is_owo_bot(MockAuthor(123456789)) is False

    def test_permissive_none(self):
        assert is_owo_bot(None) is True


# ==============================================================================
# 2. `owo team` Parser Tests
# ==============================================================================

class TestOwOTeamParser(unittest.TestCase):
    def test_parse_team_plain_text_standard(self):
        """Test realistic plain text OwO team message."""
        raw = """
⚔️ **<@746723893229912165>'s Battle Team**
[1] <:glion:418284974593277954> Lion (Lvl 50) - Weapon: Great Sword [664DFC]
[2] <:gowl:418284974593277954> Owl (Lvl 48) - Weapon: Healing Staff [A1B2C3]
[3] <:gwolf:418284974593277954> Wolf (Lvl 45) - Weapon: None
"""
        parsed = parse_owo_team(raw)
        assert parsed is not None
        assert parsed.user_id == "746723893229912165"
        assert len(parsed.slots) == 3

        # Slot 1
        s1 = parsed.get_slot(1)
        assert s1 is not None
        assert s1.animal_name == "lion"
        assert s1.level == 50
        assert s1.weapon_name == "Great Sword"
        assert s1.weapon_id == "664DFC"
        assert s1.is_empty is False

        # Slot 2
        s2 = parsed.get_slot(2)
        assert s2 is not None
        assert s2.animal_name == "owl"
        assert s2.level == 48
        assert s2.weapon_name == "Healing Staff"
        assert s2.weapon_id == "A1B2C3"
        assert s2.is_empty is False

        # Slot 3
        s3 = parsed.get_slot(3)
        assert s3 is not None
        assert s3.animal_name == "wolf"
        assert s3.level == 45
        assert s3.weapon_name is None
        assert s3.weapon_id is None
        assert s3.is_empty is False

        animals = parsed.animals
        assert len(animals) == 3
        assert animals[0].name == "lion"
        assert animals[0].level == 50
        assert animals[0].equipped_weapon_id == "664DFC"

    def test_parse_team_embed_fields(self):
        """Test realistic Discord embed with 3 fields for 3 slots."""
        embed = MockEmbed(
            title="⚔️ Your Battle Team",
            fields=[
                MockField("Position 1: Dog", "Lvl: 50\nWeapon: Defender's Aegis (`101`)"),
                MockField("Position 2: Cow", "Lvl: 30\nWeapon: Wand of Absorption (`b102`)"),
                MockField("Position 3", "Empty Slot"),
            ]
        )
        msg = MockMessage(embeds=[embed])
        parsed = parse_owo_team(msg)
        assert parsed is not None
        assert len(parsed.slots) == 3

        s1 = parsed.get_slot(1)
        assert s1 is not None
        assert s1.animal_name == "dog"
        assert s1.level == 50
        assert s1.weapon_name == "Defender's Aegis"
        assert s1.weapon_id == "101"

        s2 = parsed.get_slot(2)
        assert s2 is not None
        assert s2.animal_name == "cow"
        assert s2.level == 30
        assert s2.weapon_name == "Wand of Absorption"
        assert s2.weapon_id == "B102"  # Empowered ID normalized to uppercase

        s3 = parsed.get_slot(3)
        assert s3 is not None
        assert s3.is_empty is True
        assert s3.animal_name is None
        assert s3.weapon_id is None

        # Animals list should only contain active pets (2 pets)
        animals = parsed.animals
        assert len(animals) == 2

    def test_parse_team_missing_weapons_and_empty_slots(self):
        """Test team with empty slots and pets without weapons."""
        raw = """
**Team 1**
Slot 1: <:deer:123> Deer (Level 12) - Weapon: None
Slot 2: Empty
Slot 3: None
"""
        parsed = parse_owo_team(raw)
        assert parsed is not None
        assert parsed.team_num == 1
        s1 = parsed.get_slot(1)
        assert s1.animal_name == "deer"
        assert s1.level == 12
        assert s1.weapon_name is None
        assert s1.is_empty is False

        s2 = parsed.get_slot(2)
        assert s2.is_empty is True
        s3 = parsed.get_slot(3)
        assert s3.is_empty is True

    def test_parse_team_custom_numbering_format(self):
        """Test numbered list format: `1.` `2.` `3.`."""
        raw = """
**Battle Team**
1. 🦁 Lion (Lvl 50) | Equipped: Great Sword (ID: 664DFC)
2. 🦉 Owl (Lvl 40) | Equipped: None
3. 🐘 Elephant (Lvl 35) | Equipped: Bow [b55]
"""
        parsed = parse_owo_team(raw)
        assert parsed is not None
        assert parsed.get_slot(1).animal_name == "lion"
        assert parsed.get_slot(1).weapon_id == "664DFC"
        assert parsed.get_slot(2).animal_name == "owl"
        assert parsed.get_slot(2).weapon_name is None
        assert parsed.get_slot(3).animal_name == "elephant"
        assert parsed.get_slot(3).weapon_id == "B55"

    def test_non_team_message_returns_none(self):
        raw = "You found a common weapon crate! Open it with `owo wc`."
        assert parse_owo_team(raw) is None


# ==============================================================================
# 3. `owo weapon inv` Parser Tests
# ==============================================================================

class TestOwOWeaponInvParser(unittest.TestCase):
    def test_parse_table_format_with_empowered_and_hex_ids(self):
        """Test paginated table format with mixed weapon IDs and wears."""
        raw = """
__**Your Weapons**__ (Page 1/5)
`ID    ` `Quality` `Wear    ` `Name`
`664DFC`  95.5%   Pristine  Great Sword
`A1B2C3`  85.0%   Fine      Healing Staff
`b102  `  78.2%   Worn      Empowered Club
`105   `  54.0%   Decent    Bow
`999FFF` 105.0%   Pristine  Great Sword
"""
        parsed = parse_owo_weapon_inv(raw)
        assert parsed is not None
        assert parsed.current_page == 1
        assert parsed.total_pages == 5
        assert len(parsed.weapons) == 5

        # Row 1: 664DFC
        w1 = parsed.weapons[0]
        assert w1.weapon_id == "664DFC"
        assert w1.quality_val == 95.5
        assert w1.wear == "pristine"
        assert w1.weapon_name == "Great Sword"
        assert w1.empowered is False

        # Row 3: b102 (Empowered)
        w3 = parsed.weapons[2]
        assert w3.weapon_id == "B102"
        assert w3.quality_val == 78.2
        assert w3.wear == "worn"
        assert "Club" in w3.weapon_name
        assert w3.empowered is True

        # Row 4: 105 (Numeric)
        w4 = parsed.weapons[3]
        assert w4.weapon_id == "105"
        assert w4.quality_val == 54.0
        assert w4.wear == "decent"
        assert w4.weapon_name == "Bow"

        # Row 5: 105.0% (Pristine max quality)
        w5 = parsed.weapons[4]
        assert w5.quality_val == 105.0
        assert w5.wear == "pristine"

        # Verify conversion to OwnedWeapon
        owned_list = parsed.to_owned_weapons()
        assert len(owned_list) == 5
        assert isinstance(owned_list[0], OwnedWeapon)
        assert owned_list[0].id == "664DFC"
        assert owned_list[0].quality_val == 95.5

    def test_parse_delimited_bullet_inventory(self):
        """Test bullet delimited weapon inventory listing."""
        raw = """
⚔️ **<@746723893229912165>'s Weapon Inventory** - Page 2 of 4
• `664DFC` • **95.5%** • Pristine • Great Sword
• `B45` • **92.0%** • Fine • Empowered Healing Staff
• `101` • **65.0%** • Worn • Poison Dagger
"""
        parsed = parse_owo_weapon_inv(raw)
        assert parsed is not None
        assert parsed.current_page == 2
        assert parsed.total_pages == 4
        assert len(parsed.weapons) == 3

        assert parsed.weapons[0].weapon_id == "664DFC"
        assert parsed.weapons[0].wear == "pristine"
        assert parsed.weapons[1].weapon_id == "B45"
        assert parsed.weapons[1].empowered is True
        assert parsed.weapons[2].weapon_id == "101"
        assert parsed.weapons[2].weapon_name == "Poison Dagger"

    def test_parse_embed_inventory(self):
        """Test weapon inventory inside a Discord Embed."""
        embed = MockEmbed(
            title="Weapons Inventory",
            description="`664DFC` | 95.5% | Pristine | Great Sword\n`A1B2C3` | 80.0% | Worn | Wand",
            footer_text="Page 3/8"
        )
        msg = MockMessage(embeds=[embed])
        parsed = parse_owo_weapon_inv(msg)
        assert parsed is not None
        assert parsed.current_page == 3
        assert parsed.total_pages == 8
        assert len(parsed.weapons) == 2
        assert parsed.weapons[0].weapon_id == "664DFC"
        assert parsed.weapons[1].weapon_id == "A1B2C3"

    def test_invalid_inv_returns_none(self):
        raw = "Hello world, no weapons here!"
        assert parse_owo_weapon_inv(raw) is None


# ==============================================================================
# 4. `owo weapon <id>` Parser Tests (Inspection)
# ==============================================================================

class TestOwOWeaponInspectParser(unittest.TestCase):
    def test_parse_standard_weapon_inspection(self):
        """Test realistic native OwO weapon inspection output."""
        raw = """
**Heather's Pristine Great Sword**
**Name:** Great Sword
**Owner:** Heather
**ID:** `664DFC`
**Shard Value:** 5,000 selling / 12,500 buying
**Quality:** 100.0%
**Wear:** Pristine
**WP Cost:** 100
**Description:** Deals 55% of your STR to all opponents.
**Passives:**
- Mana Tap: 77% (Roll: 77/100)
**Rolls:** 31, 7, 77
"""
        parsed = parse_owo_weapon_inspect(raw)
        assert parsed is not None
        assert parsed.weapon_id == "664DFC"
        assert parsed.weapon_name == "Great Sword"
        assert parsed.quality_val == 100.0
        assert parsed.wear == "pristine"
        assert parsed.wp_cost == 100
        assert parsed.shard_selling == 5000
        assert parsed.shard_buying == 12500
        assert parsed.owner == "Heather"
        assert parsed.stats.get("str") == 55.0
        assert parsed.rolls == [31, 7, 77]
        assert len(parsed.passives) == 1
        assert parsed.passives[0].slug == "mtap"
        assert parsed.passives[0].stat_val == 77.0
        assert parsed.passives[0].roll == 77

        # Verify OwnedWeapon conversion
        owned = parsed.to_owned_weapon()
        assert isinstance(owned, OwnedWeapon)
        assert owned.id == "664DFC"
        assert owned.quality_val == 100.0
        assert owned.wear == "pristine"
        assert len(owned.passives) == 1

    def test_parse_empowered_weapon_inspection_multiple_passives(self):
        """Test inspection of an empowered weapon with multiple passives."""
        raw = """
**Bob's Worn Empowered Club**
**Name:** Empowered Club
**ID:** `b102`
**Quality:** 82.5%
**Wear:** Worn
**WP Cost:** 80
**Description:** Smashes enemies dealing 60% of your STR.
**Passives:**
- Strength: 15% (Roll: 85)
- Mana Tap: 65% (Roll: 65)
"""
        parsed = parse_owo_weapon_inspect(raw)
        assert parsed is not None
        assert parsed.weapon_id == "B102"
        assert parsed.empowered is True
        assert parsed.quality_val == 82.5
        assert parsed.wear == "worn"
        assert len(parsed.passives) == 2
        slugs = [p.slug for p in parsed.passives]
        assert "str" in slugs
        assert "mtap" in slugs

    def test_parse_inspection_embed(self):
        """Test inspection inside Discord embed."""
        embed = MockEmbed(
            title="⚔️ Healing Staff [A1B2C3]",
            fields=[
                MockField("ID", "A1B2C3"),
                MockField("Quality", "85.0%"),
                MockField("Wear", "Fine"),
                MockField("WP Cost", "50"),
                MockField("Passives", "• Resilience: 80%"),
            ]
        )
        msg = MockMessage(embeds=[embed])
        parsed = parse_owo_weapon_inspect(msg)
        assert parsed is not None
        assert parsed.weapon_id == "A1B2C3"
        assert parsed.weapon_name == "Healing Staff"
        assert parsed.quality_val == 85.0
        assert parsed.wear == "fine"
        assert parsed.wp_cost == 50
        assert len(parsed.passives) == 1
        assert parsed.passives[0].slug == "res"


# ==============================================================================
# 5. `owo zoo` Parser Tests
# ==============================================================================

class TestOwOZooParser(unittest.TestCase):
    def test_parse_zoo_custom_emojis_with_counts(self):
        """Test typical OwO zoo response with custom emojis and counts."""
        raw = """
**<@746723893229912165>'s Zoo!** (Zoo Points: 1,250)
<:cbee:1001> 15  <:cbug:1002> 8  <:csnail:1003> 20
<:uchick:1004> 5  <:umouse:1005> 1  <:rcow:1006> 3
<:etiger:1007> 2  <:mdragon:1008> 1  <:ldeer:1009> 4
"""
        parsed = parse_owo_zoo(raw)
        assert parsed is not None
        assert parsed.user_id == "746723893229912165"
        assert parsed.zoo_points == 1250
        assert parsed.total_animals == 59  # 15+8+20+5+1+3+2+1+4 = 59

        # Animal counts check
        assert parsed.get_count("bee") == 15
        assert parsed.get_count("bug") == 8
        assert parsed.get_count("snail") == 20
        assert parsed.get_count("chick") == 5
        assert parsed.get_count("mouse") == 1
        assert parsed.get_count("cow") == 3
        assert parsed.get_count("tiger") == 2
        assert parsed.get_count("dragon") == 1
        assert parsed.get_count("deer") == 4
        assert parsed.get_count("nonexistent") == 0

        # Conversion to OwnedAnimal list
        owned_animals = parsed.to_owned_animals()
        assert len(owned_animals) == 9
        assert any(a.name == "bee" and a.count == 15 for a in owned_animals)

    def test_parse_zoo_plain_text_format(self):
        """Test zoo formatted as plain text animal names with counts."""
        raw = """
**Routo's Zoo**
Common:
Bee: 10, Bug: 5, Snail: 2
Rare:
Cow: 4, Dog: 3
Legendary:
Lion: 1, Owl: 2
Zoo Points: 500
"""
        parsed = parse_owo_zoo(raw)
        assert parsed is not None
        assert parsed.user_name == "Routo"
        assert parsed.zoo_points == 500
        assert parsed.get_count("bee") == 10
        assert parsed.get_count("cow") == 4
        assert parsed.get_count("lion") == 1
        assert parsed.get_count("owl") == 2

    def test_parse_zoo_display_short(self):
        """Test zoo display where each animal appears once without count."""
        raw = """
**Alex's Zoo Display**
<:glion:101> <:gowl:102> <:gdeer:103>
"""
        parsed = parse_owo_zoo(raw)
        assert parsed is not None
        assert parsed.user_name == "Alex"
        assert parsed.get_count("lion") == 1
        assert parsed.get_count("owl") == 1
        assert parsed.get_count("deer") == 1

    def test_invalid_zoo_returns_none(self):
        raw = "You received 500 cowoncy for voting!"
        assert parse_owo_zoo(raw) is None


# ==============================================================================
# 6. Unified Dispatcher `parse_owo_message` Tests
# ==============================================================================

class TestUnifiedDispatcher(unittest.TestCase):
    def test_dispatcher_routes_team(self):
        raw = """
⚔️ **<@746723893229912165>'s Battle Team**
[1] <:lion:1> Lion (Lvl 50) - Weapon: Great Sword [664DFC]
[2] <:owl:2> Owl (Lvl 48) - Weapon: None
[3] Empty
"""
        msg = MockMessage(content=raw, author=MockAuthor(OWO_BOT_ID))
        res = parse_owo_message(msg)
        assert isinstance(res, ParsedTeam)
        assert res.get_slot(1).animal_name == "lion"

    def test_dispatcher_routes_weapon_inv(self):
        raw = """
__**Your Weapons**__ (Page 1/2)
`664DFC` 95.5% Pristine Great Sword
`b102` 78.2% Worn Empowered Club
"""
        msg = MockMessage(content=raw, author=MockAuthor(OWO_BOT_ID))
        res = parse_owo_message(msg)
        assert isinstance(res, ParsedWeaponInv)
        assert len(res.weapons) == 2

    def test_dispatcher_routes_weapon_inspect(self):
        raw = """
**Pristine Great Sword**
**Name:** Great Sword
**ID:** `664DFC`
**Quality:** 100.0%
**Wear:** Pristine
**WP Cost:** 100
**Passives:**
- Mana Tap: 77%
"""
        msg = MockMessage(content=raw, author=MockAuthor(OWO_BOT_ID))
        res = parse_owo_message(msg)
        assert isinstance(res, ParsedWeaponInspect)
        assert res.weapon_id == "664DFC"

    def test_dispatcher_routes_zoo(self):
        raw = """
**User's Zoo!** (Zoo Points: 100)
<:cbee:101> 5  <:rcow:102> 2
"""
        msg = MockMessage(content=raw, author=MockAuthor(OWO_BOT_ID))
        res = parse_owo_message(msg)
        assert isinstance(res, ParsedZoo)
        assert res.get_count("bee") == 5

    def test_dispatcher_rejects_unauthorized_author(self):
        raw = """
**User's Zoo!** (Zoo Points: 100)
<:cbee:101> 5
"""
        fake_msg = MockMessage(content=raw, author=MockAuthor(999999999))
        assert parse_owo_message(fake_msg, check_bot_id=True) is None

    def test_dispatcher_unrecognized_returns_none(self):
        msg = MockMessage(content="Random message", author=MockAuthor(OWO_BOT_ID))
        assert parse_owo_message(msg) is None


# ==============================================================================
# 7. Advanced Edge Cases & Model Compatibility Tests
# ==============================================================================

class TestEdgeCasesAndModels(unittest.TestCase):
    def test_team_single_pet_two_empty_slots(self):
        """Test team when user only has 1 pet configured and 2 empty slots."""
        raw = """
**Starter Team**
[1] <:cchick:123> Chick (Lvl 5) - Weapon: Great Sword
[2] Empty
[3] No pet set
"""
        parsed = parse_owo_team(raw)
        assert parsed is not None
        assert parsed.get_slot(1).animal_name == "chick"
        assert parsed.get_slot(1).level == 5
        assert parsed.get_slot(1).weapon_name == "Great Sword"
        assert parsed.get_slot(1).weapon_id is None
        assert parsed.get_slot(2).is_empty is True
        assert parsed.get_slot(3).is_empty is True
        assert len(parsed.animals) == 1

    def test_team_all_slots_empty(self):
        """Test uninitialized team with 3 empty slots."""
        raw = """
**Battle Team**
Slot 1: Empty
Slot 2: Empty
Slot 3: Empty
"""
        parsed = parse_owo_team(raw)
        assert parsed is not None
        assert all(s.is_empty for s in parsed.slots)
        assert len(parsed.animals) == 0

    def test_team_embed_description_format(self):
        """Test team located inside embed description instead of fields."""
        embed = MockEmbed(
            title="⚔️ Your Battle Team",
            description="""
**__Position 1__**
🐶 **Dog** - Lvl 50
Weapon: Great Sword (`664DFC`)

**__Position 2__**
🐮 **Cow** - Lvl 48
Weapon: None

**__Position 3__**
Empty
"""
        )
        msg = MockMessage(embeds=[embed])
        parsed = parse_owo_team(msg)
        assert parsed is not None
        assert parsed.get_slot(1).animal_name == "dog"
        assert parsed.get_slot(1).weapon_id == "664DFC"
        assert parsed.get_slot(2).animal_name == "cow"
        assert parsed.get_slot(2).weapon_name is None
        assert parsed.get_slot(3).is_empty is True

    def test_weapon_inv_integer_percentages_and_unknown_wear(self):
        """Test inventory with integer percentages and unknown wear."""
        raw = """
**Inventory** (Page 10/10)
`A1B2C3`  80%  Unknown  Great Sword
`102`    100%  Fine     Bow
"""
        parsed = parse_owo_weapon_inv(raw)
        assert parsed is not None
        assert parsed.current_page == 10
        assert parsed.total_pages == 10
        assert len(parsed.weapons) == 2
        assert parsed.weapons[0].quality_val == 80.0
        assert parsed.weapons[0].wear == "unknown"
        assert parsed.weapons[1].quality_val == 100.0
        assert parsed.weapons[1].wear == "fine"

    def test_weapon_inv_empty_page(self):
        """Test inventory page with no weapons."""
        raw = "**Inventory** (Page 1/1)\nYou don't have any weapons in your inventory."
        assert parse_owo_weapon_inv(raw) is None

    def test_weapon_inspect_three_passives_empowered_orb(self):
        """Test inspection of an empowered orb with 3 passives."""
        raw = """
**Empowered Orb of Potency**
**ID:** `b999`
**Quality:** 94.0%
**Wear:** Fine
**WP Cost:** 120
**Passives:**
- Mana Tap: 80% (Roll: 80)
- Discharge: 75% (Roll: 75)
- Thorns: 60% (Roll: 60)
"""
        parsed = parse_owo_weapon_inspect(raw)
        assert parsed is not None
        assert parsed.weapon_id == "B999"
        assert parsed.empowered is True
        assert len(parsed.passives) == 3
        slugs = [p.slug for p in parsed.passives]
        assert slugs == ["mtap", "dis", "thorns"]
        assert parsed.rolls == [80, 75, 60]

    def test_zoo_locked_question_marks_ignored(self):
        """Test that locked animal slots ('?') in zoo grid are ignored."""
        raw = """
**Player's Zoo!** (Zoo Points: 15)
<:cbee:101> 5  ❓ 0  <:rdog:102> 1  ? 0
"""
        parsed = parse_owo_zoo(raw)
        assert parsed is not None
        assert parsed.get_count("bee") == 5
        assert parsed.get_count("dog") == 1
        assert parsed.total_animals == 6

    def test_zoo_duplicate_emojis_accumulated(self):
        """Test that multiple occurrences of an animal are summed."""
        raw = """
**User's Zoo**
<:cbee:101> 5
<:cbee:101> 10
"""
        parsed = parse_owo_zoo(raw)
        assert parsed is not None
        assert parsed.get_count("bee") == 15
        assert parsed.total_animals == 15

    def test_parse_zoo_with_superscripts_and_unicode_emojis(self):
        """Test real OwO zoo format containing superscripts and emoji shortcodes."""
        raw = """🌿 🌱 🌳** Mluehh's zoo! **🌳 🌿 🌱
<:common:416520037713838081>   :bee:⁵⁵  :bug:⁶⁹  :snail:⁶⁶  :beetle:⁵⁷  :butterfly:⁶⁹  
<:uncommon:416520056269176842>   :baby_chick:³³  :mouse2:³⁵  :rooster:³⁸  :rabbit2:²⁸  :chipmunk:²⁷  
<:rare:416520066629107712>   :sheep:¹⁸  :pig2:¹⁵  :cow2:¹²  :dog2:¹⁵  :cat2:⁰⁴  
<:epic:416520722987614208>   :crocodile:⁰⁰  :tiger2:⁰³  :penguin:⁰¹  :elephant:⁰⁰  :whale:⁰¹  
<:mythic:416520808501084162>   :dragon:⁰⁰  :unicorn:⁰⁰  :snowman2:⁰¹  :ghost:⁰⁰  :dove:⁰⁰  
<a:gem:510023576489951232>    <a:gshrimp:510023577295388672>⁰⁰  <a:gspider:510023576775032844>⁰⁰  
<a:legendary:417955061801680909>    <a:gfox:418291892376305664>⁰¹  <a:gowl:418284974593277954>⁰⁰  <a:gsquid:417968419984375808>⁰⁰
**Zoo Points: __165,102__**
	**G-3, L-3, M-11, E-64, R-658, U-1879, C-3547**"""
        parsed = parse_owo_zoo(raw)
        assert parsed is not None
        assert parsed.user_name == "Mluehh"
        assert parsed.zoo_points == 165102
        assert parsed.get_count("bug") == 69
        assert parsed.get_count("tiger") == 3
        assert parsed.get_count("fox") == 1
        assert parsed.get_count("penguin") == 1
        assert parsed.get_count("snowman") == 1
        assert parsed.get_count("cat") == 4
        # Animals with count 0 should be 0
        assert parsed.get_count("crocodile") == 0
        assert parsed.get_count("dragon") == 0
        assert parsed.get_count("owl") == 0

    def test_parse_weapon_inv_discord_components_v2(self):
        """Test parsing weapon inventory delivered via Discord Components V2 structure."""
        message_dict = {
            "content": "",
            "embeds": [],
            "components": [
                {
                    "type": 17,
                    "components": [
                        {
                            "type": 10,
                            "content": "`G7KEF8` <:epic:416520722987614208><:epstaff:1082882871439655054><:ratt:535290420255522855> **Staff of Purity [0]** 61%\n`G7KEF6` <:epic:416520722987614208><:eascept:618001307994685441><:emag:535290422940139520> **Arcane Scepter** 76.6%\n`G7JMQ4` <:epic:416520722987614208><:esythe:618001307562672128><:rresonance:1448548624433938567> **Culling Scythe** 63%"
                        }
                    ]
                }
            ]
        }
        parsed = parse_owo_weapon_inv(message_dict)
        assert parsed is not None
        assert len(parsed.weapons) == 3
        w_map = {w.weapon_id: w for w in parsed.weapons}
        assert "G7KEF8" in w_map
        assert "G7KEF6" in w_map
        assert "G7JMQ4" in w_map
        assert w_map["G7KEF8"].quality_val == 61.0
        assert w_map["G7KEF6"].quality_val == 76.6

    def test_generate_owo_game_commands_positional_syntax(self):
        """Test that generated OwO equip commands use official positional team add/remove syntax."""
        from owo_strategy.optimizer.level_scaler import NeonUtilExporter
        from owo_strategy.optimizer.team_optimizer import CandidateTeam
        from owo_strategy.schemas.models import OwnedAnimal, OwnedWeapon

        current_team = [
            OwnedAnimal(name="bug", level=16),
            OwnedAnimal(name="none", level=0),
            OwnedAnimal(name="none", level=0),
        ]
        candidate = CandidateTeam(
            animals=[
                OwnedAnimal(name="bug", level=16),
                OwnedAnimal(name="tiger", level=1),
                OwnedAnimal(name="fox", level=1),
            ],
            weapons=[
                OwnedWeapon(id="G7KEF8", weapon_name="Staff of Purity"),
                OwnedWeapon(id="G7KEF6", weapon_name="Arcane Scepter"),
                OwnedWeapon(id="G7JMQ4", weapon_name="Culling Scythe"),
            ]
        )
        cmds = NeonUtilExporter.generate_owo_game_commands(candidate, current_team=current_team)
        # Slot 1 is already bug, so it should not generate team add bug 1
        assert "owo team add tiger 2" in cmds
        assert "owo team add fox 3" in cmds
        assert "owo weapon G7KEF8 bug" in cmds
        assert "owo weapon G7KEF6 tiger" in cmds
        assert "owo weapon G7JMQ4 fox" in cmds
        # Ensure it does not generate invalid animal-based team remove
        assert not any("owo team remove " in c and not c[-1].isdigit() for c in cmds)
