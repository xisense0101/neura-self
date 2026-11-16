"""
Native OwO Discord Message and Embed Parsers.

Parses native responses from the OwO bot (ID: 408785106942164992):
- `owo team`: Extract 3 team slots (animal name, level, equipped weapon name and ID).
  Handles both text format and embed field format.
- `owo weapon inv`: Parse paginated weapon inventory tables/lists.
  Extracts weapon ID (6-char alphanumeric, numeric, or 'b' prefix empowered like 'b102'),
  quality percentage, wear, and weapon name.
- `owo weapon <id>`: Parse individual weapon inspection response (rolls, blueprints, passives).
- `owo zoo`: Parse owned animals list/counts and zoo points.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

try:
    from owo_strategy.schemas.models import OwnedAnimal, OwnedWeapon
except ImportError:
    try:
        from schemas.models import OwnedAnimal, OwnedWeapon
    except ImportError:
        OwnedAnimal = None  # type: ignore
        OwnedWeapon = None  # type: ignore

# OwO Discord Bot Identity
OWO_BOT_ID = 408785106942164992

# Regular expressions
CUSTOM_EMOJI_RE = re.compile(r"<a?:([A-Za-z0-9_]+):(\d+)>")
LEVEL_RE = re.compile(r"\b(?:lvl|level|lv)[\.:\s]*([0-9]{1,3})\b", re.IGNORECASE)
PERCENT_RE = re.compile(r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%", re.IGNORECASE)
WEAPON_ID_HEX_RE = re.compile(r"\b([0-9A-Fa-f]{6})\b")
WEAPON_ID_EMPOWERED_RE = re.compile(r"\b([bB][0-9]{1,5})\b")
WEAPON_ID_NUMERIC_RE = re.compile(r"\b([0-9]{2,5})\b")
WEAR_RE = re.compile(r"\b(pristine|fine|decent|worn|unknown)\b", re.IGNORECASE)

# Animal rank prefixes used in OwO emojis (e.g. cbee, uchick, rsheep, etiger, mdragon, ldeer, etc.)
ANIMAL_RANK_PREFIXES = (
    "cp",  # custom patreon
    "c",   # common
    "u",   # uncommon
    "r",   # rare
    "e",   # epic
    "m",   # mythic / mythical
    "l",   # legendary
    "g",   # gem
    "f",   # fabled
    "b",   # bot
    "s",   # special
    "h",   # hidden
    "d",   # distorted
    "p",   # patreon
)

# Canonical weapon dictionary and aliases
CANONICAL_WEAPON_LABELS: dict[str, str] = {
    "sword": "Great Sword",
    "hstaff": "Healing Staff",
    "bow": "Bow",
    "shield": "Defender's Aegis",
    "rune": "Rune of the Forgotten",
    "dagger": "Poison Dagger",
    "wand": "Wand of Absorption",
    "orb": "Orb of Potency",
    "fstaff": "Flame Staff",
    "estaff": "Energy Staff",
    "sstaff": "Spirit Staff",
    "ascept": "Arcane Scepter",
    "rstaff": "Resurrection Staff",
    "vstaff": "Vampiric Staff",
    "axe": "Glacial Axe",
    "scythe": "Culling Scythe",
    "club": "Empowered Club",
    "aedge": "Arbiter's Edge",
    "pstaff": "Staff of Purity",
    "cstaff": "Staff of Corruption",
    "ffish": "Foul Fish",
    "bgaze": "Bleeding Gaze",
    "banner": "Vanguard's Banner",
    "lsythe": "Leeching Scythe",
    "crossbow": "Wounding Crossbow",
    "claw": "Conduit Claw",
    "bhstaff": "Briar-Heart Staff",
    "stithe": "Soul Tithe",
    "crune": "Rune of Celebration",
    "lrune": "Rune of Luck",
}

WEAPON_ALIASES: dict[str, str] = {
    "sword": "sword",
    "great sword": "sword",
    "greatsword": "sword",
    "gsword": "sword",
    "great_sword": "sword",
    "healing staff": "hstaff",
    "healstaff": "hstaff",
    "healingstaff": "hstaff",
    "hstaff": "hstaff",
    "bow": "bow",
    "compound bow": "bow",
    "shield": "shield",
    "defender's aegis": "shield",
    "defenders aegis": "shield",
    "aegis": "shield",
    "rune of the forgotten": "rune",
    "rune": "rune",
    "poison dagger": "dagger",
    "dagger": "dagger",
    "pdagger": "dagger",
    "wand of absorption": "wand",
    "wand": "wand",
    "awand": "wand",
    "orb of potency": "orb",
    "orb": "orb",
    "flame staff": "fstaff",
    "fstaff": "fstaff",
    "energy staff": "estaff",
    "estaff": "estaff",
    "spirit staff": "sstaff",
    "sstaff": "sstaff",
    "arcane scepter": "ascept",
    "arcane": "ascept",
    "scepter": "ascept",
    "ascept": "ascept",
    "resurrection staff": "rstaff",
    "rstaff": "rstaff",
    "vampiric staff": "vstaff",
    "vampstaff": "vstaff",
    "vstaff": "vstaff",
    "mvampstaff": "vstaff",
    "great axe": "axe",
    "glacial axe": "axe",
    "axe": "axe",
    "gaxe": "axe",
    "glaxe": "axe",
    "culling scythe": "scythe",
    "scythe": "scythe",
    "sythe": "scythe",
    "csythe": "scythe",
    "esythe": "scythe",
    "empowered club": "club",
    "club": "club",
    "arbiter's edge": "aedge",
    "arbiters edge": "aedge",
    "aedge": "aedge",
    "staff of purity": "pstaff",
    "purity staff": "pstaff",
    "pstaff": "pstaff",
    "epstaff": "pstaff",
    "staff of corruption": "cstaff",
    "corruption staff": "cstaff",
    "cstaff": "cstaff",
    "ecstaff": "cstaff",
    "foul fish": "ffish",
    "fish": "ffish",
    "ffish": "ffish",
    "bleeding gaze": "bgaze",
    "bgaze": "bgaze",
    "bgaz": "bgaze",
    "vanguard's banner": "banner",
    "vanguard banner": "banner",
    "war banner": "banner",
    "banner": "banner",
    "vban": "banner",
    "leeching scythe": "lsythe",
    "lsythe": "lsythe",
    "lsyth": "lsythe",
    "wounding crossbow": "crossbow",
    "crossbow": "crossbow",
    "woundb": "crossbow",
    "conduit claw": "claw",
    "claw": "claw",
    "cclaw": "claw",
    "briar-heart staff": "bhstaff",
    "briar heart staff": "bhstaff",
    "bhstaff": "bhstaff",
    "soul tithe": "stithe",
    "stithe": "stithe",
    "rune of celebration": "crune",
    "crune": "crune",
    "rune of luck": "lrune",
    "lrune": "lrune",
}

# Known passive mappings
PASSIVE_ALIASES: dict[str, str] = {
    "strength": "str",
    "str": "str",
    "attack": "str",
    "att": "str",
    "magic": "mag",
    "mag": "mag",
    "health point": "hp",
    "health": "hp",
    "hp": "hp",
    "weapon point": "wp",
    "wp": "wp",
    "physical resistance": "pr",
    "physical resist": "pr",
    "pr": "pr",
    "magical resistance": "mr",
    "magical resist": "mr",
    "mr": "mr",
    "lifesteal": "lifesteal",
    "thorns": "thorns",
    "mana tap": "mtap",
    "manatap": "mtap",
    "mtap": "mtap",
    "absolve": "absolve",
    "safeguard": "safe",
    "safe": "safe",
    "sg": "safe",
    "critical": "crit",
    "crit": "crit",
    "discharge": "dis",
    "dis": "dis",
    "kamikaze": "kami",
    "kami": "kami",
    "regeneration": "regen",
    "regen": "regen",
    "resilience": "res",
    "res": "res",
    "counter": "counter",
    "swiftness": "speed",
    "speed": "speed",
    "lucky": "luck",
    "luck": "luck",
    "precision": "prec",
    "prec": "prec",
}

PASSIVE_LABELS: dict[str, str] = {
    "str": "Strength",
    "mag": "Magic",
    "hp": "Health Point",
    "wp": "Weapon Point",
    "pr": "Physical Resistance",
    "mr": "Magical Resistance",
    "lifesteal": "Lifesteal",
    "thorns": "Thorns",
    "mtap": "Mana Tap",
    "absolve": "Absolve",
    "safe": "Safeguard",
    "crit": "Critical",
    "dis": "Discharge",
    "kami": "Kamikaze",
    "regen": "Regeneration",
    "res": "Resilience",
    "counter": "Counter",
    "speed": "Swiftness",
    "luck": "Lucky",
    "prec": "Precision",
}

# Common animal names for detection in plain text (base names)
STANDARD_ANIMAL_NAMES = (
    "bee", "bug", "snail", "slug", "beetle", "butterfly",
    "chick", "mouse", "chicken", "rabbit", "chipmunk",
    "sheep", "pig", "cow", "dog", "cat",
    "crocodile", "tiger", "penguin", "elephant", "whale",
    "dragon", "unicorn", "snowman", "ghost", "dove",
    "deer", "fox", "lion", "owl", "squid", "wolf", "dino",
    "camel", "fish", "monkey", "lizard", "gorilla", "frog",
    "eagle", "boar", "flamingo", "snake", "panda", "bear",
    "zebra", "cheetah", "koala", "hedgehog", "sloth",
    "otter", "raccoon", "hamster", "seal", "turtle",
    "giraffbot",
)


def is_owo_bot(author: Any) -> bool:
    """Check if the message author matches the official OwO Discord Bot ID."""
    if author is None:
        return True
    author_id = getattr(author, "id", author)
    if isinstance(author_id, dict):
        author_id = author_id.get("id")
    try:
        return int(author_id) == OWO_BOT_ID
    except (ValueError, TypeError):
        return str(author_id) == str(OWO_BOT_ID)


def normalize_animal_name(raw_name: str) -> str:
    """Normalize raw animal string or emoji name into canonical animal slug."""
    cleaned = raw_name.strip().lower()
    # Strip non-alphanumeric except underscore
    cleaned = re.sub(r"[^a-z0-9_]", "", cleaned)

    # Strip trailing numbers like tiger2 -> tiger, mouse2 -> mouse, rabbit2 -> rabbit, cat2 -> cat
    cleaned = re.sub(r"\d+$", "", cleaned)

    # If it directly matches known animal
    if cleaned in STANDARD_ANIMAL_NAMES:
        return cleaned

    # Check rank prefix removal (e.g. cbee -> bee, rsheep -> sheep, glion -> lion, gfox -> fox, etc.)
    for animal in STANDARD_ANIMAL_NAMES:
        if cleaned.endswith(animal):
            prefix = cleaned[:-len(animal)]
            if not prefix or prefix in ANIMAL_RANK_PREFIXES:
                return animal

    return cleaned


def normalize_weapon_name(raw_name: str) -> tuple[str, str]:
    """
    Normalize weapon name.
    Returns (slug, display_name).
    """
    clean = raw_name.strip().lower()
    clean = re.sub(r"^(?:pristine|fine|decent|worn|unknown)\s+", "", clean)

    for alias, slug in WEAPON_ALIASES.items():
        if alias in clean or clean in alias:
            return slug, CANONICAL_WEAPON_LABELS.get(slug, slug.title())

    return clean, raw_name.strip().title()


def _extract_components_text(components: Any, depth: int = 0, visited: set[int] | None = None) -> list[str]:
    """Recursively extract plain text from Discord Components V2 with loop protection."""
    texts: list[str] = []
    if not components or depth > 8:
        return texts

    if visited is None:
        visited = set()
    comp_id = id(components)
    if comp_id in visited:
        return texts
    visited.add(comp_id)

    if isinstance(components, (list, tuple)):
        for item in components:
            texts.extend(_extract_components_text(item, depth + 1, visited))
    elif isinstance(components, dict):
        if components.get("content"):
            texts.append(str(components["content"]))
        if components.get("label"):
            texts.append(str(components["label"]))
        if components.get("components"):
            texts.extend(_extract_components_text(components["components"], depth + 1, visited))
    else:
        # Check concrete attributes safely without triggering endless MagicMock recursion
        content = getattr(components, "content", None)
        if content and isinstance(content, (str, int, float)):
            texts.append(str(content))
        label = getattr(components, "label", None)
        if label and isinstance(label, (str, int, float)):
            texts.append(str(label))
        children = getattr(components, "children", None)
        if children and isinstance(children, (list, tuple)):
            texts.extend(_extract_components_text(children, depth + 1, visited))
        sub_comps = getattr(components, "components", None)
        if sub_comps and isinstance(sub_comps, (list, tuple)):
            texts.extend(_extract_components_text(sub_comps, depth + 1, visited))
    return texts


def _extract_message_data(message: Any) -> dict[str, Any]:
    """
    Extract content, embed titles, descriptions, components, and fields from any message input.
    Supports discord.Message, discord.Embed, dict, or raw string.
    """
    content = ""
    embeds_data: list[dict[str, Any]] = []
    components_text: list[str] = []
    author_id = None

    if isinstance(message, str):
        content = message
    elif isinstance(message, dict):
        content = str(message.get("content", ""))
        author_id = message.get("author", {}).get("id") if isinstance(message.get("author"), dict) else message.get("author")
        raw_embeds = message.get("embeds", [])
        if "fields" in message or "title" in message or "description" in message:
            # message is itself an embed dict
            embeds_data.append(message)
        for emb in raw_embeds:
            if isinstance(emb, dict):
                embeds_data.append(emb)
            else:
                embeds_data.append(_extract_embed_obj(emb))
        if message.get("components"):
            components_text = _extract_components_text(message["components"])
    else:
        # Object-like (discord.Message or discord.Embed)
        content = str(getattr(message, "content", ""))
        author = getattr(message, "author", None)
        if author is not None:
            author_id = getattr(author, "id", None)

        # Check if message itself is an embed (Embed object passed directly, not a Message)
        if (
            not hasattr(message, "embeds")
            and not hasattr(message, "components")
            and (hasattr(message, "fields") or hasattr(message, "title") or hasattr(message, "description"))
        ):
            embeds_data.append(_extract_embed_obj(message))

        # Check embeds attribute
        raw_embeds = getattr(message, "embeds", [])
        if isinstance(raw_embeds, (list, tuple)):
            for emb in raw_embeds:
                embeds_data.append(_extract_embed_obj(emb))

        # Check components attribute
        raw_components = getattr(message, "components", [])
        if raw_components and isinstance(raw_components, (list, tuple)):
            components_text = _extract_components_text(raw_components)

    # Combine text for holistic matching
    all_text_parts = [content]
    for emb in embeds_data:
        author_emb = emb.get("author")
        if isinstance(author_emb, dict):
            auth_name = author_emb.get("name", "")
            if auth_name and isinstance(auth_name, (str, int, float)):
                all_text_parts.append(str(auth_name))
        elif isinstance(author_emb, (str, int, float)) and author_emb:
            all_text_parts.append(str(author_emb))

        t = emb.get("title")
        if t and isinstance(t, (str, int, float)):
            all_text_parts.append(str(t))
        d = emb.get("description")
        if d and isinstance(d, (str, int, float)):
            all_text_parts.append(str(d))
        for f in emb.get("fields", []):
            if isinstance(f, dict):
                fn = f.get("name")
                if fn and isinstance(fn, (str, int, float)):
                    all_text_parts.append(str(fn))
                fv = f.get("value")
                if fv and isinstance(fv, (str, int, float)):
                    all_text_parts.append(str(fv))

        footer = emb.get("footer")
        if isinstance(footer, dict):
            ft_text = footer.get("text", "")
            if ft_text and isinstance(ft_text, (str, int, float)):
                all_text_parts.append(str(ft_text))
        elif isinstance(footer, (str, int, float)) and footer:
            all_text_parts.append(str(footer))

    if components_text:
        all_text_parts.extend(components_text)

    all_text = "\n".join(str(part) for part in all_text_parts if part and not str(part).startswith("<MagicMock"))

    return {
        "content": content,
        "embeds": embeds_data,
        "components_text": components_text,
        "author_id": author_id,
        "all_text": all_text,
    }


def _extract_embed_obj(emb: Any) -> dict[str, Any]:
    """Helper to convert discord.Embed object to dict."""
    if isinstance(emb, dict):
        return emb
    res: dict[str, Any] = {
        "title": str(getattr(emb, "title", "") or "") if isinstance(getattr(emb, "title", ""), (str, int, float)) else "",
        "description": str(getattr(emb, "description", "") or "") if isinstance(getattr(emb, "description", ""), (str, int, float)) else "",
        "author": getattr(getattr(emb, "author", None), "name", "") or "",
        "footer": getattr(getattr(emb, "footer", None), "text", "") or "",
        "fields": [],
    }
    raw_fields = getattr(emb, "fields", [])
    if isinstance(raw_fields, (list, tuple)):
        for f in raw_fields:
            if isinstance(f, dict):
                res["fields"].append({"name": str(f.get("name", "")), "value": str(f.get("value", ""))})
            else:
                name_val = getattr(f, "name", "")
                val_val = getattr(f, "value", "")
                res["fields"].append({
                    "name": str(name_val) if isinstance(name_val, (str, int, float)) else "",
                    "value": str(val_val) if isinstance(val_val, (str, int, float)) else "",
                })
    return res
    return res


# ==============================================================================
# 1. `owo team` Parser
# ==============================================================================

@dataclass
class TeamSlot:
    """Represents one of the 3 slots in an OwO battle team."""
    slot_num: int
    animal_name: str | None = None
    level: int = 1
    weapon_name: str | None = None
    weapon_id: str | None = None
    is_empty: bool = False
    raw_text: str = ""

    def to_owned_animal(self) -> Any:
        if self.is_empty or not self.animal_name or OwnedAnimal is None:
            return None
        return OwnedAnimal(
            name=self.animal_name,
            level=self.level,
            equipped_weapon_id=self.weapon_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_num": self.slot_num,
            "animal_name": self.animal_name,
            "level": self.level,
            "weapon_name": self.weapon_name,
            "weapon_id": self.weapon_id,
            "is_empty": self.is_empty,
            "raw_text": self.raw_text,
        }


@dataclass
class ParsedTeam:
    """Represents the parsed outcome of an `owo team` response."""
    user_id: str | int | None = None
    user_name: str | None = None
    team_num: int = 1
    slots: list[TeamSlot] = field(default_factory=list)
    raw_message: str = ""

    @property
    def animals(self) -> list[Any]:
        return [slot.to_owned_animal() for slot in self.slots if slot.to_owned_animal() is not None]

    @property
    def weapons(self) -> list[Any]:
        res = []
        for slot in self.slots:
            if not slot.is_empty and slot.weapon_id and OwnedWeapon is not None:
                res.append(
                    OwnedWeapon(
                        id=slot.weapon_id,
                        weapon_name=slot.weapon_name or "Great Sword",
                        quality_val=85.0,
                        quality_is_exact=False,
                    )
                )
        return res

    def get_slot(self, slot_num: int) -> TeamSlot | None:
        for slot in self.slots:
            if slot.slot_num == slot_num:
                return slot
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "team_num": self.team_num,
            "slots": [s.to_dict() for s in self.slots],
        }


def parse_owo_team(message: Any) -> ParsedTeam | None:
    """
    Parse native OwO `owo team` response into 3 team slots.
    Handles both Discord embed field format and plain text message format.
    """
    data = _extract_message_data(message)
    all_text = data["all_text"]

    if not all_text:
        return None

    # Check for team indicators
    team_keywords = ("team", "slot", "position")
    has_keyword = any(kw in all_text.lower() for kw in team_keywords)
    if not has_keyword and not re.search(r"\[[1-3]\]", all_text):
        return None

    # Extract user ID and username if present
    user_id = data["author_id"]
    user_name = None
    user_match = re.search(r"<@!?(\d{15,22})>", all_text)
    if user_match:
        user_id = user_id or user_match.group(1)
    name_match = re.search(r"\*\*([A-Za-z0-9_ -]+)'s\s+(?:battle\s+)?team", all_text, re.IGNORECASE)
    if name_match:
        user_name = name_match.group(1).strip()

    team_num = 1
    tnum_match = re.search(r"team\s*([1-3])\b", all_text, re.IGNORECASE)
    if tnum_match:
        team_num = int(tnum_match.group(1))

    parsed_slots: dict[int, TeamSlot] = {}

    # Strategy A: Check embed fields
    embed_fields = []
    for emb in data["embeds"]:
        embed_fields.extend(emb.get("fields", []))

    if embed_fields:
        for field_data in embed_fields:
            fname = field_data.get("name", "")
            fval = field_data.get("value", "")
            full_field = f"{fname}\n{fval}".strip()

            slot_idx = _detect_slot_num(fname) or _detect_slot_num(full_field)
            if slot_idx and slot_idx not in parsed_slots:
                parsed_slots[slot_idx] = _parse_slot_text(slot_idx, full_field)

            # Also check for battle embed format: "{Username}'s Team" with 3 pet lines
            if "team" in fname.lower() and "enemy" not in fname.lower() and not parsed_slots:
                lines = [l.strip() for l in fval.splitlines() if l.strip()]
                if len(lines) >= 1:
                    for idx, line in enumerate(lines[:3], start=1):
                        slot = _parse_battle_pet_line(idx, line)
                        if slot:
                            parsed_slots[idx] = slot

    # Strategy B: If < 3 slots found via fields, parse text blocks
    if len(parsed_slots) < 3:
        # Check for bracket headers: [1], [2], [3] or 1., 2., 3.
        bracket_re = re.compile(
            r"^[ \t]*(?:\[|`|#+\s*)?([1-3])(?:\]|`|\.|\:|\))(.*?)(?=^[ \t]*(?:\[|`|#+\s*)?[1-3](?:\]|`|\.|\:|\))|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        for m in bracket_re.finditer(all_text):
            slot_idx = int(m.group(1))
            slot_content = m.group(2).strip()
            if slot_idx not in parsed_slots:
                parsed_slots[slot_idx] = _parse_slot_text(slot_idx, slot_content)

    # Strategy C: Check for Position / Slot headers: "Position 1:", "Slot 1:", "**__Position 1__**"
    if len(parsed_slots) < 3:
        pos_re = re.compile(
            r"^[ \t]*(?:[*_#`\s]*)(?:position|slot|team\s*slot)[\s_*`\-:]*([1-3])(?:[*_`\-:\s]*)(.+?)(?=^[ \t]*(?:[*_#`\s]*)(?:position|slot|team\s*slot)[\s_*`\-:]*[1-3]|\Z)",
            re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        for m in pos_re.finditer(all_text):
            slot_idx = int(m.group(1))
            slot_content = m.group(2).strip()
            if slot_idx not in parsed_slots:
                parsed_slots[slot_idx] = _parse_slot_text(slot_idx, slot_content)

    # Fill in any missing slots as empty slots
    final_slots: list[TeamSlot] = []
    for i in (1, 2, 3):
        if i in parsed_slots:
            final_slots.append(parsed_slots[i])
        else:
            final_slots.append(TeamSlot(slot_num=i, is_empty=True, raw_text="Empty"))

    # If all slots are empty and there were no slot markers at all, return None
    if all(s.is_empty for s in final_slots) and not re.search(r"(?:slot|position)[\s_*`\-:]*[1-3]|\[[1-3]\]", all_text, re.IGNORECASE):
        return None

    return ParsedTeam(
        user_id=user_id,
        user_name=user_name,
        team_num=team_num,
        slots=final_slots,
        raw_message=all_text,
    )


def _detect_slot_num(text: str) -> int | None:
    """Detect if string denotes slot 1, 2, or 3."""
    m = re.search(r"(?:slot|position|team\s*slot)[\s_*\-:`]*([1-3])", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(?:\[|`|\b)([1-3])(?:\]|`|\.|\b)", text)
    if m2:
        return int(m2.group(1))
    return None


def _parse_slot_text(slot_num: int, text: str) -> TeamSlot:
    """Parse pet, level, and weapon out of a single slot text block."""
    cleaned = text.strip()

    # Check for empty slot
    empty_patterns = (
        r"\bempty\b",
        r"\bno\s+pet\b",
        r"\bnone\b",
        r"\bnot\s+set\b",
        r"\bempty\s+slot\b",
    )
    if any(re.search(pat, cleaned, re.IGNORECASE) for pat in empty_patterns) and not re.search(LEVEL_RE, cleaned):
        return TeamSlot(slot_num=slot_num, is_empty=True, raw_text=cleaned)

    # 1. Level extraction
    level = 1
    lvl_match = LEVEL_RE.search(cleaned)
    if lvl_match:
        level = int(lvl_match.group(1))

    # 2. Animal name extraction
    animal_name = None
    lines = cleaned.splitlines()
    first_line = lines[0] if lines else cleaned

    # Check bold animal on the first line (e.g. "[1] :cow2: **cow**")
    bold_first = re.search(r"\*\*([A-Za-z0-9_]+)\*\*", first_line)
    if bold_first:
        cand_name = normalize_animal_name(bold_first.group(1))
        if cand_name in STANDARD_ANIMAL_NAMES or len(cand_name) >= 3:
            animal_name = cand_name

    if not animal_name:
        # Check custom emojis on first line
        emoji_first = CUSTOM_EMOJI_RE.search(first_line)
        if emoji_first:
            animal_name = normalize_animal_name(emoji_first.group(1))

    if not animal_name:
        # Check unicode shortcodes on first line (e.g. :cow2:, :bug:, :tiger2:)
        shortcode_first = re.search(r":([A-Za-z0-9_]+):", first_line)
        if shortcode_first:
            animal_name = normalize_animal_name(shortcode_first.group(1))

    if not animal_name:
        # Check standard animal names on first line
        for candidate in STANDARD_ANIMAL_NAMES:
            pattern = r"\b" + re.escape(candidate) + r"\b"
            if re.search(pattern, first_line, re.IGNORECASE):
                animal_name = normalize_animal_name(candidate)
                break

    if not animal_name:
        # Fallback to checking whole block (excluding known stat keywords)
        for candidate in STANDARD_ANIMAL_NAMES:
            pattern = r"\b" + re.escape(candidate) + r"\b"
            if re.search(pattern, cleaned, re.IGNORECASE):
                animal_name = normalize_animal_name(candidate)
                break

    # 3. Weapon extraction
    weapon_name = None
    weapon_id = None

    weapon_blob = ""
    for l in reversed(lines):
        # Exclude stat lines with <:hp:, <:att:, <:mag:, <:wp:, <:pr:, <:mr:
        if any(stat in l for stat in ("<:hp:", "<:att:", "<:mag:", "<:wp:", "<:pr:", "<:mr:")):
            continue
        if re.search(r"`\s*[A-Za-z0-9]{3,8}\s*`", l) or re.search(r"(?:weapon|equipped)", l, re.IGNORECASE) or any(w in l.lower() for w in ("sword", "staff", "bow", "scythe", "axe", "scepter", "dagger", "shield", "wand")):
            weapon_blob = l.strip()
            break
    if not weapon_blob:
        weapon_line_match = re.search(r"(?:weapon|equipped)[\.:\s]*([^\n]+)", cleaned, re.IGNORECASE)
        weapon_blob = weapon_line_match.group(1).strip() if weapon_line_match else ""

    if weapon_blob and "none" not in weapon_blob.lower() and "no weapon" not in weapon_blob.lower():
        # Weapon ID: check backtick first `664DFC` or `G7KEF8` or `b102`
        id_backtick = re.search(r"`\s*([A-Za-z0-9]{3,8})\s*`", weapon_blob)
        if id_backtick:
            weapon_id = id_backtick.group(1).upper()
        else:
            # Check bracket [664DFC]
            id_bracket = re.search(r"\[\s*([A-Za-z0-9]{3,8})\s*\]", weapon_blob)
            if id_bracket:
                weapon_id = id_bracket.group(1).upper()
            else:
                # Check empowered b-prefix
                id_emp = WEAPON_ID_EMPOWERED_RE.search(weapon_blob)
                if id_emp:
                    weapon_id = id_emp.group(1).upper()
                else:
                    # Check 6-char hex
                    id_hex = WEAPON_ID_HEX_RE.search(weapon_blob)
                    if id_hex:
                        weapon_id = id_hex.group(1).upper()
                    else:
                        id_label = re.search(r"ID:\s*([A-Za-z0-9]+)", weapon_blob, re.IGNORECASE)
                        if id_label:
                            weapon_id = id_label.group(1).upper()

        # Weapon Name
        for alias, slug in WEAPON_ALIASES.items():
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, weapon_blob, re.IGNORECASE):
                weapon_name = CANONICAL_WEAPON_LABELS.get(slug, slug.title())
                break

        if not weapon_name:
            for em_m in CUSTOM_EMOJI_RE.finditer(weapon_blob):
                em_name = em_m.group(1).lower()
                for alias, slug in WEAPON_ALIASES.items():
                    if alias in em_name:
                        weapon_name = CANONICAL_WEAPON_LABELS.get(slug, slug.title())
                        break
                if weapon_name:
                    break

    # If neither animal nor weapon nor level was found, it could be an empty slot
    if not animal_name and not weapon_name and level == 1:
        return TeamSlot(slot_num=slot_num, is_empty=True, raw_text=cleaned)

    return TeamSlot(
        slot_num=slot_num,
        animal_name=animal_name,
        level=level,
        weapon_name=weapon_name,
        weapon_id=weapon_id,
        is_empty=False,
        raw_text=cleaned,
    )


def _parse_battle_pet_line(slot_num: int, line: str) -> TeamSlot | None:
    """Parse a single line from an owo b battle team embed (e.g. L. 10 :cow2: - <:epic:...><:epstaff:...><:ratt:...>)."""
    cleaned = line.strip()
    if not cleaned:
        return None

    lvl_match = re.search(r"L\.\s*(\d+)", cleaned)
    level = int(lvl_match.group(1)) if lvl_match else 1

    animal_name = None
    em_match = re.search(r":([A-Za-z0-9_]+):", cleaned)
    if em_match:
        animal_name = normalize_animal_name(em_match.group(1))
    if not animal_name:
        for cand in STANDARD_ANIMAL_NAMES:
            if re.search(r"\b" + re.escape(cand) + r"\b", cleaned, re.IGNORECASE):
                animal_name = normalize_animal_name(cand)
                break

    if not animal_name:
        return None

    weapon_name = None
    emojis = re.findall(r"<a?:([A-Za-z0-9_]+):\d+>", cleaned)
    for em in emojis:
        em_lower = em.lower()
        if em_lower in ANIMAL_RANK_PREFIXES or em_lower in ("epic", "rare", "common", "uncommon", "mythic", "legendary", "fabled", "special"):
            continue
        # Strip rank prefixes
        stripped = re.sub(r"^[cuerfmgblsphd]", "", em_lower)
        for cand in (stripped, em_lower):
            slug = WEAPON_ALIASES.get(cand)
            if slug:
                weapon_name = CANONICAL_WEAPON_LABELS.get(slug, slug.title())
                break
        if weapon_name:
            break

    if not weapon_name:
        for alias, slug in WEAPON_ALIASES.items():
            if re.search(r"\b" + re.escape(alias) + r"\b", cleaned, re.IGNORECASE):
                weapon_name = CANONICAL_WEAPON_LABELS.get(slug, slug.title())
                break

    return TeamSlot(
        slot_num=slot_num,
        animal_name=animal_name,
        level=level,
        weapon_name=weapon_name,
        raw_text=cleaned,
    )


# ==============================================================================
# 2. `owo weapon inv` Parser
# ==============================================================================

@dataclass
class WeaponInvRow:
    """Represents a parsed weapon entry from `owo weapon inv`."""
    weapon_id: str
    weapon_name: str
    quality_val: float
    wear: str = "worn"
    empowered: bool = False
    raw_line: str = ""

    def to_owned_weapon(self) -> Any:
        if OwnedWeapon is None:
            return None
        return OwnedWeapon(
            id=self.weapon_id.upper(),
            weapon_name=self.weapon_name,
            quality_val=self.quality_val,
            quality_is_exact=True,
            wear=self.wear.lower(),
            raw_line=self.raw_line,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "weapon_id": self.weapon_id,
            "weapon_name": self.weapon_name,
            "quality_val": self.quality_val,
            "wear": self.wear,
            "empowered": self.empowered,
            "raw_line": self.raw_line,
        }


@dataclass
class ParsedWeaponInv:
    """Represents a paginated inventory page from `owo weapon inv`."""
    current_page: int = 1
    total_pages: int = 1
    weapons: list[WeaponInvRow] = field(default_factory=list)
    user_id: str | int | None = None
    raw_message: str = ""
    has_next_page: bool = False

    def __post_init__(self):
        if not self.has_next_page and self.current_page < self.total_pages:
            self.has_next_page = True

    def to_owned_weapons(self) -> list[Any]:
        return [w.to_owned_weapon() for w in self.weapons if w.to_owned_weapon() is not None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "has_next_page": self.has_next_page,
            "weapons": [w.to_dict() for w in self.weapons],
            "user_id": self.user_id,
        }


def parse_owo_weapon_inv(message: Any) -> ParsedWeaponInv | None:
    """
    Parse paginated OwO weapon inventory listings or tables (`owo weapon inv`).
    Extracts weapon ID, quality percentage, wear, and weapon name.
    Supports table/codeblock format, delimited rows, and embed listings.
    """
    data = _extract_message_data(message)
    all_text = data["all_text"]

    if not all_text:
        return None

    # Check for inventory keywords or backtick weapon rows
    inv_indicators = ("weapon", "inventory", "weapons", "quality", "wear")
    if not any(k in all_text.lower() for k in inv_indicators) and not re.search(r"`\s*[A-Za-z0-9]+\s*`.*%", all_text):
        return None

    # Page number detection
    current_page = 1
    total_pages = 1
    page_match = re.search(r"(?:page|inventory)\s*([0-9]+)\s*(?:/|of)\s*([0-9]+)", all_text, re.IGNORECASE)
    if not page_match:
        page_match = re.search(r"\(([0-9]+)\s*/\s*([0-9]+)\)", all_text)
    if not page_match:
        page_match = re.search(r"^\s*([0-9]+)\s*/\s*([0-9]+)\s*$", all_text, re.MULTILINE)
    if not page_match:
        page_match = re.search(r"\b([0-9]+)\s*/\s*([0-9]+)\b", all_text)
    if page_match:
        current_page = int(page_match.group(1))
        total_pages = int(page_match.group(2))

    # Also inspect components directly for noop button (e.g. custom_id="noop", label="1/2")
    raw_components = getattr(message, "components", None) or (message.get("components") if isinstance(message, dict) else None)
    if raw_components:
        def _scan_noop(comps):
            for c in comps:
                cid = getattr(c, "custom_id", None) or (c.get("custom_id") if isinstance(c, dict) else None)
                lbl = getattr(c, "label", None) or (c.get("label") if isinstance(c, dict) else None)
                if cid == "noop" and lbl and "/" in lbl:
                    parts = lbl.split("/")
                    if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                        return int(parts[0].strip()), int(parts[1].strip())
                children = (
                    getattr(c, "children", None)
                    or getattr(c, "components", None)
                    or (c.get("components") if isinstance(c, dict) else None)
                )
                if children:
                    res = _scan_noop(children)
                    if res:
                        return res
            return None
        noop_res = _scan_noop(raw_components)
        if noop_res:
            current_page, total_pages = noop_res

    user_id = data["author_id"]
    u_match = re.search(r"<@!?(\d{15,22})>", all_text)
    if u_match:
        user_id = user_id or u_match.group(1)

    rows: list[WeaponInvRow] = []

    # Clean text line by line
    lines = [line.strip() for line in all_text.splitlines() if line.strip()]

    for line in lines:
        # Ignore table headers
        if re.search(r"^\s*`?ID`?\s+`?Quality`?", line, re.IGNORECASE) or re.search(r"^__\*\*.*weapons.*\*\*__", line, re.IGNORECASE):
            continue

        row = _parse_weapon_inv_line(line)
        if row is not None:
            rows.append(row)

    if not rows:
        return None

    return ParsedWeaponInv(
        current_page=current_page,
        total_pages=total_pages,
        weapons=rows,
        user_id=user_id,
        raw_message=all_text,
    )


def _parse_weapon_inv_line(line: str) -> WeaponInvRow | None:
    """Extract weapon ID, quality, wear, and name from a single inventory row."""
    # Must have a percentage for quality
    q_match = PERCENT_RE.search(line)
    if not q_match:
        return None

    quality_val = float(q_match.group(1))

    # Extract ID with priority:
    # 1. Backtick ID `664DFC` or `b102` (handling spaces inside like `105   `)
    w_id = None
    id_backtick = re.search(r"`\s*([A-Za-z0-9]+)\s*`", line)
    if id_backtick:
        w_id = id_backtick.group(1).upper()

    # 2. Bracket ID [664DFC] or [b102]
    if not w_id:
        id_bracket = re.search(r"\[\s*([A-Za-z0-9]+)\s*\]", line)
        if id_bracket:
            w_id = id_bracket.group(1).upper()

    # 3. Empowered 'b' prefix: b102
    if not w_id:
        id_emp = WEAPON_ID_EMPOWERED_RE.search(line)
        if id_emp:
            w_id = id_emp.group(1).upper()

    # 4. Strict 6-char hexadecimal (0-9, A-F) - excludes words like DECENT
    if not w_id:
        id_hex = WEAPON_ID_HEX_RE.search(line)
        if id_hex:
            w_id = id_hex.group(1).upper()

    # 5. Numeric ID token at start of row
    if not w_id:
        num_start = re.search(r"^(?:•|[-*])?\s*([0-9]{2,5})\b", line)
        if num_start:
            w_id = num_start.group(1)

    if not w_id:
        return None

    if w_id.upper() in {
        "COOKIE", "CUDDLE", "SHIP", "PRAY", "CURSE", "MARRY", "EMOJI",
        "PROFILE", "LEVEL", "WALLPAPER", "OWOIFY", "AVATAR", "HUG",
        "KISS", "LICK", "NOM", "PAT", "POKE", "SLAP", "STARE",
        "HIGHFIVE", "BITE", "GREET", "PUNCH", "HANDHOLDING", "TICKLE",
        "KILL", "HOLD", "PATS", "WAVE", "BOOP", "SNUGGLE", "BULLY",
        "RADA", "RADAR"
    }:
        return None

    empowered = w_id.lower().startswith("b")

    # Extract wear
    wear = "worn"
    wear_match = WEAR_RE.search(line)
    if wear_match:
        wear = wear_match.group(1).lower()

    # Extract weapon name
    weapon_name = "Great Sword"
    for alias, slug in WEAPON_ALIASES.items():
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, line, re.IGNORECASE):
            weapon_name = CANONICAL_WEAPON_LABELS.get(slug, slug.title())
            if empowered and not weapon_name.lower().startswith("empowered"):
                weapon_name = f"Empowered {weapon_name}"
            break
    else:
        # Fallback: clean line of ID, quality, wear, backticks, emojis
        rem = line
        rem = re.sub(re.escape(w_id), "", rem, flags=re.IGNORECASE)
        rem = re.sub(PERCENT_RE, "", rem)
        rem = re.sub(WEAR_RE, "", rem)
        rem = re.sub(CUSTOM_EMOJI_RE, "", rem)
        rem = re.sub(r"[`*•|\-:\[\]()]", " ", rem).strip()
        rem_tokens = [tok for tok in rem.split() if not tok.isdigit()]
        if rem_tokens:
            weapon_name = " ".join(rem_tokens).title()

    return WeaponInvRow(
        weapon_id=w_id,
        weapon_name=weapon_name,
        quality_val=quality_val,
        wear=wear,
        empowered=empowered,
        raw_line=line,
    )


# ==============================================================================
# 3. `owo weapon <id>` Parser (Inspection)
# ==============================================================================

@dataclass
class ParsedPassive:
    """Represents a passive ability found on a weapon."""
    name: str
    slug: str
    stat_val: float | None = None
    roll: int | None = None
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "slug": self.slug,
            "stat_val": self.stat_val,
            "roll": self.roll,
            "raw_text": self.raw_text,
        }


@dataclass
class ParsedWeaponInspect:
    """Represents individual weapon inspection output (`owo weapon <id>`)."""
    weapon_id: str
    weapon_name: str
    quality_val: float
    wear: str = "worn"
    wp_cost: int | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    rolls: list[int] = field(default_factory=list)
    passives: list[ParsedPassive] = field(default_factory=list)
    blueprint: str = ""
    description: str = ""
    shard_selling: int | None = None
    shard_buying: int | None = None
    empowered: bool = False
    owner: str | None = None
    raw_message: str = ""

    def to_owned_weapon(self) -> Any:
        if OwnedWeapon is None:
            return None
        passives_dict_list = [
            {"name": p.name, "slug": p.slug, "stat": p.stat_val, "roll": p.roll}
            for p in self.passives
        ]
        return OwnedWeapon(
            id=self.weapon_id.upper(),
            weapon_name=self.weapon_name,
            quality_val=self.quality_val,
            quality_is_exact=True,
            wear=self.wear.lower(),
            stats=dict(self.stats),
            passives=passives_dict_list,
            raw_line=self.raw_message,
            blueprint=self.blueprint,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "weapon_id": self.weapon_id,
            "weapon_name": self.weapon_name,
            "quality_val": self.quality_val,
            "wear": self.wear,
            "wp_cost": self.wp_cost,
            "stats": self.stats,
            "rolls": self.rolls,
            "passives": [p.to_dict() for p in self.passives],
            "blueprint": self.blueprint,
            "description": self.description,
            "shard_selling": self.shard_selling,
            "shard_buying": self.shard_buying,
            "empowered": self.empowered,
            "owner": self.owner,
        }


def parse_owo_weapon_inspect(message: Any) -> ParsedWeaponInspect | None:
    """
    Parse an individual weapon inspection response (`owo weapon <id>`).
    Extracts rolls, blueprints, passives, wear, quality, WP cost, and shard value.
    """
    data = _extract_message_data(message)
    all_text = data["all_text"]

    if not all_text:
        return None

    # Weapon inspection keywords
    has_inspect_keywords = any(
        kw in all_text.lower()
        for kw in ("quality:", "quality :", "wear:", "wear :", "wp cost", "shard value", "passives:", "blueprint")
    )
    # Must have inspection keywords AND must not be an inventory page
    if not has_inspect_keywords:
        return None
    if re.search(r"(?:page\s+[0-9]+|\([0-9]+/[0-9]+\))", all_text, re.IGNORECASE):
        return None

    # 1. Weapon ID
    w_id = None
    id_match = re.search(r"(?:\*\*ID:\*\*|ID:?)\s*`?([A-Za-z0-9]+)`?", all_text, re.IGNORECASE)
    if id_match:
        w_id = id_match.group(1).upper()
    else:
        # Check title like [664DFC] or `664DFC`
        bracket_id = re.search(r"\[([A-Za-z0-9]{3,8})\]|`([A-Za-z0-9]{3,8})`", all_text)
        if bracket_id:
            w_id = (bracket_id.group(1) or bracket_id.group(2)).upper()
        else:
            emp_id = WEAPON_ID_EMPOWERED_RE.search(all_text)
            if emp_id:
                w_id = emp_id.group(1).upper()
            else:
                hex_id = WEAPON_ID_HEX_RE.search(all_text)
                if hex_id:
                    w_id = hex_id.group(1).upper()

    if not w_id:
        return None

    if w_id.upper() in {
        "COOKIE", "CUDDLE", "SHIP", "PRAY", "CURSE", "MARRY", "EMOJI",
        "PROFILE", "LEVEL", "WALLPAPER", "OWOIFY", "AVATAR", "HUG",
        "KISS", "LICK", "NOM", "PAT", "POKE", "SLAP", "STARE",
        "HIGHFIVE", "BITE", "GREET", "PUNCH", "HANDHOLDING", "TICKLE",
        "KILL", "HOLD", "PATS", "WAVE", "BOOP", "SNUGGLE", "BULLY",
        "RADA", "RADAR"
    }:
        return None

    empowered = w_id.lower().startswith("b") or "empowered" in all_text.lower()

    # 2. Weapon Name
    weapon_name = "Great Sword"
    name_match = re.search(r"\*\*Name:\*\*\s*([^\n]+)", all_text, re.IGNORECASE)
    if name_match:
        raw_name = name_match.group(1).strip()
        _, weapon_name = normalize_weapon_name(raw_name)
    else:
        # Check header
        for alias, slug in WEAPON_ALIASES.items():
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, all_text, re.IGNORECASE):
                weapon_name = CANONICAL_WEAPON_LABELS.get(slug, slug.title())
                break

    # 3. Quality
    quality_val = 85.0
    q_match = re.search(r"(?:\*\*Quality:\*\*|Quality:?)\s*\*?\*?([0-9]+(?:\.[0-9]+)?)\s*%\*?\*?", all_text, re.IGNORECASE)
    if q_match:
        quality_val = float(q_match.group(1))
    else:
        gen_q = PERCENT_RE.search(all_text)
        if gen_q:
            quality_val = float(gen_q.group(1))

    # 4. Wear
    wear = "worn"
    wear_match = re.search(r"(?:\*\*Wear:\*\*|Wear:?)\s*\*?\*?([A-Za-z]+)\*?\*?", all_text, re.IGNORECASE)
    if wear_match:
        wear = wear_match.group(1).lower()
    else:
        gen_wear = WEAR_RE.search(all_text)
        if gen_wear:
            wear = gen_wear.group(1).lower()

    # 5. WP Cost
    wp_cost = None
    wp_match = re.search(r"\bWP\s*Cost\b\s*[:\*\s]*([0-9]+)", all_text, re.IGNORECASE)
    if wp_match:
        wp_cost = int(wp_match.group(1))

    # 6. Shard Values
    shard_selling = None
    shard_buying = None
    shard_match = re.search(r"([0-9,]+)\s*selling\s*/\s*([0-9,]+)\s*buying", all_text, re.IGNORECASE)
    if shard_match:
        shard_selling = int(shard_match.group(1).replace(",", ""))
        shard_buying = int(shard_match.group(2).replace(",", ""))

    # 7. Owner
    owner = None
    owner_match = re.search(r"\*\*Owner:\*\*\s*([^\n]+)", all_text, re.IGNORECASE)
    if owner_match:
        owner = owner_match.group(1).strip()

    # 8. Description
    description = ""
    desc_match = re.search(r"\*\*Description:\*\*\s*([^\n]+)", all_text, re.IGNORECASE)
    if desc_match:
        description = desc_match.group(1).strip()

    # 9. Passives
    passives: list[ParsedPassive] = []
    passives_sec = ""
    p_sec_match = re.search(r"\*\*Passives:\*\*(.*?)(?=\*\*[A-Z]|$)", all_text, re.DOTALL | re.IGNORECASE)
    if p_sec_match:
        passives_sec = p_sec_match.group(1)

    # Parse each passive row
    p_lines = passives_sec.splitlines() if passives_sec else all_text.splitlines()
    for pline in p_lines:
        pline = pline.strip()
        if not pline or not pline.startswith(("-", "•", "*")):
            continue

        # Look for passive name and percentage
        p_name = None
        p_slug = ""
        for alias, slug in PASSIVE_ALIASES.items():
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, pline, re.IGNORECASE):
                p_slug = slug
                p_name = PASSIVE_LABELS.get(slug, alias.title())
                break

        if p_name:
            pct_m = PERCENT_RE.search(pline)
            stat_val = float(pct_m.group(1)) if pct_m else None

            # Roll check
            roll_val = None
            roll_m = re.search(r"Roll:\s*([0-9]+)", pline, re.IGNORECASE)
            if roll_m:
                roll_val = int(roll_m.group(1))

            passives.append(
                ParsedPassive(
                    name=p_name,
                    slug=p_slug,
                    stat_val=stat_val,
                    roll=roll_val,
                    raw_text=pline,
                )
            )

    # 10. Rolls
    rolls: list[int] = []
    rolls_line_match = re.search(r"(?:^|\n)[ \t]*\**Rolls\**\s*[:\*\s]*([0-9,\s]+)", all_text, re.IGNORECASE)
    if rolls_line_match:
        roll_tokens = re.findall(r"\d+", rolls_line_match.group(1))
        rolls = [int(tok) for tok in roll_tokens]
    else:
        # Collect rolls from passives if present
        for p in passives:
            if p.roll is not None:
                rolls.append(p.roll)

    # 11. Blueprint
    bp_match = re.search(r"`([a-z]+ [0-9,]+ [a-z0-9, ]+)`", all_text, re.IGNORECASE)
    if bp_match:
        blueprint = bp_match.group(1).strip()
    else:
        # Synthesize blueprint string
        wp_slug = normalize_weapon_name(weapon_name)[0]
        stat_rolls_str = ",".join(str(r) for r in rolls[:2]) if rolls else "100"
        passive_str = " ".join(f"{p.slug} {int(p.stat_val or 100)}" for p in passives)
        blueprint = f"{wear} {wp_slug} {stat_rolls_str} {passive_str}".strip()

    stats: dict[str, Any] = {}
    if wp_cost is not None:
        stats["wp_cost"] = wp_cost
    # Scaling stats from description (e.g. 55% of your STR)
    scaling_m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*of\s*your\s*([A-Za-z]+)", description, re.IGNORECASE)
    if scaling_m:
        val = float(scaling_m.group(1))
        stat_type = scaling_m.group(2).lower()
        stats[stat_type] = val

    return ParsedWeaponInspect(
        weapon_id=w_id,
        weapon_name=weapon_name,
        quality_val=quality_val,
        wear=wear,
        wp_cost=wp_cost,
        stats=stats,
        rolls=rolls,
        passives=passives,
        blueprint=blueprint,
        description=description,
        shard_selling=shard_selling,
        shard_buying=shard_buying,
        empowered=empowered,
        owner=owner,
        raw_message=all_text,
    )


# ==============================================================================
# 4. `owo zoo` Parser
# ==============================================================================

@dataclass
class ZooEntry:
    """Represents an animal entry in a user's zoo inventory."""
    name: str
    count: int = 1
    rank: str | None = None
    emoji: str | None = None

    def to_owned_animal(self) -> Any:
        if OwnedAnimal is None:
            return None
        return OwnedAnimal(name=self.name, count=self.count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "rank": self.rank,
            "emoji": self.emoji,
        }


@dataclass
class ParsedZoo:
    """Represents parsed output of `owo zoo`."""
    user_name: str | None = None
    user_id: str | int | None = None
    zoo_points: int | None = None
    animals: list[ZooEntry] = field(default_factory=list)
    raw_message: str = ""

    def to_owned_animals(self) -> list[Any]:
        return [a.to_owned_animal() for a in self.animals if a.to_owned_animal() is not None]

    def get_count(self, animal_name: str) -> int:
        target = normalize_animal_name(animal_name)
        for a in self.animals:
            if a.name.lower() == target or normalize_animal_name(a.name) == target:
                return a.count
        return 0

    @property
    def total_animals(self) -> int:
        return sum(a.count for a in self.animals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_name": self.user_name,
            "user_id": self.user_id,
            "zoo_points": self.zoo_points,
            "total_animals": self.total_animals,
            "animals": [a.to_dict() for a in self.animals],
        }


def parse_owo_zoo(message: Any) -> ParsedZoo | None:
    """
    Parse an OwO `owo zoo` response.
    Extracts owned animals list/counts, zoo score/points, and user info.
    Supports emoji-count grids, list format, and embed layouts.
    """
    data = _extract_message_data(message)
    all_text = data["all_text"]

    if not all_text:
        return None

    # Check for zoo keywords
    is_zoo_msg = "'s zoo" in all_text.lower() or "zoo points" in all_text.lower() or "zoo display" in all_text.lower()
    if not is_zoo_msg:
        return None

    # Extract user info
    user_id = data["author_id"]
    u_match = re.search(r"<@!?(\d{15,22})>", all_text)
    if u_match:
        user_id = user_id or u_match.group(1)

    user_name = None
    name_match = re.search(r"\*\*([A-Za-z0-9_ -]+)'s\s+zoo", all_text, re.IGNORECASE)
    if name_match:
        user_name = name_match.group(1).strip()

    # Extract zoo points
    zoo_points = None
    pts_match = re.search(r"(?:zoo\s*points?|points?)[\.:\s_*]*([0-9,]+)", all_text, re.IGNORECASE)
    if pts_match:
        zoo_points = int(pts_match.group(1).replace(",", ""))

    counts_by_animal: dict[str, int] = {}
    rank_by_animal: dict[str, str] = {}
    emoji_by_animal: dict[str, str] = {}

    superscript_map = {
        '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
        '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'
    }

    def _parse_superscript_or_int(s: str | None) -> int:
        if not s:
            return 1
        digits = ''.join(superscript_map.get(c, c) for c in s if c in superscript_map or c.isdigit())
        return int(digits) if digits else 1

    tier_name_set = {
        "common", "uncommon", "rare", "epic", "mythic", "mythical",
        "legendary", "fabled", "gem", "bot", "distorted", "special",
        "hidden", "patreon"
    }

    # Pattern A1: Custom emoji with count or superscripts: `<a?:cbee:1001> 15`, `<a:gfox:123>⁰¹`
    custom_count_re = re.compile(r"<a?:([A-Za-z0-9_]+):(\d+)>\s*(?:x\s*)?([⁰¹²³⁴⁵⁶⁷⁸⁹0-9]+)?", re.IGNORECASE)
    for m in custom_count_re.finditer(all_text):
        raw_emoji = m.group(1)
        if raw_emoji.lower() in tier_name_set:
            continue
        cnt = _parse_superscript_or_int(m.group(3))
        animal = normalize_animal_name(raw_emoji)
        if animal and animal not in tier_name_set:
            # If count explicitly 0 (like ⁰⁰), user does not own it
            if cnt == 0 and m.group(3) is not None:
                continue
            counts_by_animal[animal] = counts_by_animal.get(animal, 0) + cnt
            emoji_by_animal[animal] = f"<:{raw_emoji}:{m.group(2)}>"
            for rk in ANIMAL_RANK_PREFIXES:
                if raw_emoji.startswith(rk):
                    rank_by_animal[animal] = rk
                    break

    # Pattern A2: Standard unicode/shortcode emojis with superscripts or numbers: `:bug:⁶⁹`, `:tiger2:⁰³`
    text_without_custom = custom_count_re.sub(" ", all_text)
    shortcode_count_re = re.compile(r":([A-Za-z0-9_]+):\s*(?:x\s*)?([⁰¹²³⁴⁵⁶⁷⁸⁹0-9]+)?", re.IGNORECASE)
    for m in shortcode_count_re.finditer(text_without_custom):
        raw_name = m.group(1)
        if raw_name.lower() in tier_name_set:
            continue
        cnt = _parse_superscript_or_int(m.group(2))
        animal = normalize_animal_name(raw_name)
        if animal and animal not in tier_name_set:
            if cnt == 0 and m.group(2) is not None:
                continue
            counts_by_animal[animal] = counts_by_animal.get(animal, 0) + cnt
            emoji_by_animal[animal] = f":{raw_name}:"

    # Pattern B: Plain text lines e.g. "Bee: 15, Bug: 8, Snail: 20" or "• Bee: 15"
    if not counts_by_animal:
        for candidate in STANDARD_ANIMAL_NAMES:
            pat = re.compile(r"\b" + re.escape(candidate) + r"\b\s*[:x\-]?\s*([0-9]+)\b", re.IGNORECASE)
            for m in pat.finditer(all_text):
                cnt = int(m.group(1))
                animal = normalize_animal_name(candidate)
                if cnt > 0:
                    counts_by_animal[animal] = counts_by_animal.get(animal, 0) + cnt

    # Pattern C: Plain animal emojis without count (e.g. brief display, count=1 each)
    if not counts_by_animal:
        emojis_only = CUSTOM_EMOJI_RE.findall(all_text)
        for raw_emoji, emoji_id in emojis_only:
            animal = normalize_animal_name(raw_emoji)
            if (animal in STANDARD_ANIMAL_NAMES or len(animal) >= 3) and animal not in tier_name_set:
                counts_by_animal[animal] = counts_by_animal.get(animal, 0) + 1
                emoji_by_animal[animal] = f"<:{raw_emoji}:{emoji_id}>"

    animals_list: list[ZooEntry] = []
    for anim, count in counts_by_animal.items():
        if anim.lower().strip() in tier_name_set or count <= 0:
            continue
        animals_list.append(
            ZooEntry(
                name=anim,
                count=count,
                rank=rank_by_animal.get(anim),
                emoji=emoji_by_animal.get(anim),
            )
        )

    return ParsedZoo(
        user_name=user_name,
        user_id=user_id,
        zoo_points=zoo_points,
        animals=animals_list,
        raw_message=all_text,
    )


# ==============================================================================
# Unified Dispatcher
# ==============================================================================

def parse_owo_message(message: Any, check_bot_id: bool = True) -> Any:
    """
    Automatic dispatcher to detect and parse any native OwO response.
    Returns ParsedTeam, ParsedWeaponInv, ParsedWeaponInspect, ParsedZoo, or None.
    """
    data = _extract_message_data(message)
    if check_bot_id and data["author_id"] is not None:
        if not is_owo_bot(data["author_id"]):
            return None

    all_text = data["all_text"].lower()

    # 1. Check Zoo
    if "'s zoo" in all_text or "zoo points" in all_text or "zoo display" in all_text:
        zoo_res = parse_owo_zoo(message)
        if zoo_res and zoo_res.animals:
            return zoo_res

    # 2. Check Team
    if "battle team" in all_text or "'s team" in all_text or "your team" in all_text or re.search(r"\[[1-3]\]", all_text):
        team_res = parse_owo_team(message)
        if team_res and not all(s.is_empty for s in team_res.slots):
            return team_res

    # 3. Check Weapon Inventory (paginated table or list)
    if ("weapons" in all_text or "inventory" in all_text) and ("page" in all_text or re.search(r"\b\d+/\d+\b", all_text)):
        inv_res = parse_owo_weapon_inv(message)
        if inv_res and inv_res.weapons:
            return inv_res

    # 4. Check Weapon Inspection
    if any(k in all_text for k in ("quality:", "quality :", "wp cost", "shard value", "passives:", "blueprint")):
        inspect_res = parse_owo_weapon_inspect(message)
        if inspect_res:
            return inspect_res

    # 5. Fallback check for inventory
    inv_res = parse_owo_weapon_inv(message)
    if inv_res and len(inv_res.weapons) >= 2:
        return inv_res

    return None


__all__ = [
    "OWO_BOT_ID",
    "TeamSlot",
    "ParsedTeam",
    "WeaponInvRow",
    "ParsedWeaponInv",
    "ParsedPassive",
    "ParsedWeaponInspect",
    "ZooEntry",
    "ParsedZoo",
    "is_owo_bot",
    "normalize_animal_name",
    "normalize_weapon_name",
    "parse_owo_team",
    "parse_owo_weapon_inv",
    "parse_owo_weapon_inspect",
    "parse_owo_zoo",
    "parse_owo_message",
]
