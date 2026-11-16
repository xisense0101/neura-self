"""Pure Python parser for NeonUtil weapon inventory views, blueprints, and inspection outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from owo_strategy.schemas.models import OwnedAnimal, OwnedWeapon

# Core regex patterns adapted from owo-boss-helper-discord-bot/cogs/neon_weapons.py
WEAPON_ID_RE = re.compile(r"\b([A-Z0-9]{6})\b", re.IGNORECASE)
CUSTOM_EMOJI_RE = re.compile(r"<a?:([A-Za-z0-9_]+):(\d{15,22})>")
NEON_HEADER_RE = re.compile(
    r"(?:^|\n)\s*#+\s*⚔️\s*<@!?(\d{15,22})>'s\s+([\d,]+)\s+(saved\s+)?weapons\b",
    re.IGNORECASE,
)
FILTER_LINE_RE = re.compile(r"^\s*\*\*Filters:\*\*\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
WEAPON_ROW_RE = re.compile(r"^\s*`([A-Z0-9]{6})`\s+(.+)$", re.IGNORECASE | re.MULTILINE)
QUALITY_RE = re.compile(r"\*\*\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*\*\*")
BACKTICK_NUMBER_RE = re.compile(r"`\s*([0-9]+(?:\.[0-9]+)?)\s*%?\s*`")
BLUEPRINT_RE = re.compile(r"`([^`]*[A-Za-z][^`]*)`")
MAX_QUALITY_HEADER_RE = re.compile(r"Max\s+qualities\s+for\s+\d+", re.IGNORECASE)

STATUS_EMOJIS = {
    "max_possible": "1064755333484007535",
    "exact": "1064746427147890758",
    "saved": "1064746427147890758",
}

NEON_CONTEXT_PREFIXES = (
    "common",
    "uncommon",
    "rare",
    "epic",
    "mythic",
    "mythical",
    "legendary",
    "fabled",
    "hidden",
    "distorted",
    "patreon",
    "gem",
    "bot",
    "pristine",
    "fine",
    "decent",
    "worn",
    "unknown",
    "empowered",
    "pr",
    "c",
    "u",
    "r",
    "e",
    "m",
    "l",
    "f",
    "d",
    "p",
    "g",
    "b",
    "h",
)

WEAPON_ALIASES: dict[str, str] = {
    "sword": "sword",
    "gsword": "sword",
    "greatsword": "sword",
    "great_sword": "sword",
    "ugreatsword": "sword",
    "rgreatsword": "sword",
    "egreatsword": "sword",
    "mgreatsword": "sword",
    "great": "sword",
    "hstaff": "hstaff",
    "healstaff": "hstaff",
    "healingstaff": "hstaff",
    "bow": "bow",
    "rune": "rune",
    "shield": "shield",
    "aegis": "shield",
    "orb": "orb",
    "vstaff": "vstaff",
    "vampstaff": "vstaff",
    "dagger": "dagger",
    "pdagger": "dagger",
    "pdag": "dagger",
    "pd": "dagger",
    "wand": "wand",
    "awand": "wand",
    "fstaff": "fstaff",
    "estaff": "estaff",
    "sstaff": "sstaff",
    "ascept": "ascept",
    "arcane": "ascept",
    "scepter": "ascept",
    "rstaff": "rstaff",
    "axe": "axe",
    "gaxe": "axe",
    "vban": "vban",
    "banner": "vban",
    "sythe": "sythe",
    "csyth": "sythe",
    "csy": "sythe",
    "scythe": "sythe",
    "crune": "crune",
    "cel": "crune",
    "pstaff": "pstaff",
    "lsyth": "lsyth",
    "lsy": "lsyth",
    "lscythe": "lsyth",
    "ffish": "ffish",
    "lrune": "lrune",
    "cstaff": "cstaff",
    "stithe": "stithe",
    "soul": "stithe",
    "tithe": "stithe",
    "bhstaff": "bhstaff",
    "aedge": "aedge",
    "edge": "aedge",
    "woundb": "woundb",
    "crossbow": "woundb",
    "wbow": "woundb",
    "wcbow": "woundb",
    "xbow": "woundb",
    "bgaz": "bgaz",
    "gaze": "bgaz",
    "bgaze": "bgaz",
    "cclaw": "cclaw",
    "claw": "cclaw",
}

PASSIVE_ALIASES: dict[str, str] = {
    "att": "str",
    "str": "str",
    "strength": "str",
    "mag": "mag",
    "magic": "mag",
    "hp": "hp",
    "wp": "wp",
    "pr": "pr",
    "mr": "mr",
    "lifesteal": "ls",
    "ls": "ls",
    "thorns": "th",
    "th": "th",
    "mtap": "mtap",
    "manatap": "mtap",
    "mana_tap": "mtap",
    "absolve": "absv",
    "absv": "absv",
    "safeguard": "sg",
    "sg": "sg",
    "critical": "crit",
    "crit": "crit",
    "discharge": "dc",
    "dc": "dc",
    "kkaze": "kk",
    "kamikaze": "kk",
    "kk": "kk",
    "hgen": "hgen",
    "regen": "hgen",
    "regeneration": "hgen",
    "wgen": "wgen",
    "energ": "wgen",
    "energize": "wgen",
    "sprout": "sprout",
    "sprt": "sprout",
    "enrage": "enrage",
    "enra": "enrage",
    "sac": "sac",
    "sacrifice": "sac",
    "snail": "snail",
    "knowledge": "kno",
    "kno": "kno",
    "n": "kno",
    "gslay": "gslay",
    "slay": "gslay",
    "slayer": "gslay",
    "adapt": "adapt",
    "adaptation": "adapt",
    "resonance": "res",
    "res": "res",
    "reso": "res",
    "swarm": "swarm",
    "hive": "swarm",
    "lhive": "swarm",
    "lwolf": "lwolf",
    "wolf": "lwolf",
    "dstrike": "ds",
    "strike": "ds",
    "ds": "ds",
    "frarm": "fr",
    "armor": "fr",
    "fr": "fr",
}

WEAPON_LABELS = {
    "sword": "Great Sword",
    "hstaff": "Healing Staff",
    "bow": "Bow",
    "rune": "Rune",
    "shield": "Defender's Aegis",
    "orb": "Orb",
    "vstaff": "Vampiric Staff",
    "dagger": "Poison Dagger",
    "wand": "Wand",
    "fstaff": "Flame Staff",
    "estaff": "Energy Staff",
    "sstaff": "Spirit Staff",
    "ascept": "Arcane Scepter",
    "rstaff": "Resurrection Staff",
    "axe": "Glacial Axe",
    "vban": "Vanguard's Banner",
    "sythe": "Culling Scythe",
    "crune": "Rune of Celebration",
    "pstaff": "Staff of Purity",
    "lsyth": "Leeching Scythe",
    "ffish": "Foul Fish",
    "lrune": "Rune of Luck",
    "cstaff": "Staff of Corruption",
    "stithe": "Soul Tithe",
    "bhstaff": "Briar-Heart Staff",
    "aedge": "Arbiter's Edge",
    "woundb": "Wounding Crossbow",
    "bgaz": "Bleeding Gaze",
    "cclaw": "Conduit Claw",
}

PASSIVE_LABELS = {
    "str": "Strength",
    "mag": "Magic",
    "hp": "Health Point",
    "wp": "Weapon Point",
    "pr": "Physical Resistance",
    "mr": "Magic Resistance",
    "ls": "Lifesteal",
    "th": "Thorns",
    "mtap": "Mana Tap",
    "absv": "Absolve",
    "sg": "Safeguard",
    "crit": "Critical",
    "dc": "Discharge",
    "kk": "Kamikaze",
    "hgen": "Regeneration",
    "wgen": "Energize",
    "sprout": "Sprout",
    "enrage": "Enrage",
    "sac": "Sacrifice",
    "snail": "Snail",
    "kno": "Knowledge",
    "gslay": "Giant Slayer",
    "adapt": "Adaptation",
    "res": "Resonance",
    "swarm": "Living Hive",
    "lwolf": "Lone Wolf",
    "ds": "Double Strike",
    "fr": "Frost Armor",
}

WEAR_NAMES = ("worn", "decent", "fine", "pristine")


@dataclass(frozen=True)
class ParsedWeaponRow:
    """Represents a parsed weapon line from Neon inventory view."""

    weapon_id: str
    raw_line: str
    current_quality: float | None
    max_quality: float | None
    max_possible: bool
    exact: bool
    saved: bool
    weapon_type: str
    passive_types: tuple[str, ...]
    emoji_ids: tuple[str, ...]
    empowered_unresolved: bool

    @property
    def weapon_name(self) -> str:
        return WEAPON_LABELS.get(self.weapon_type, self.weapon_type or "Unknown Weapon")

    def to_owned_weapon(self) -> OwnedWeapon:
        passives_list = [
            {"slug": p, "name": PASSIVE_LABELS.get(p, p)} for p in self.passive_types
        ]
        stats = {}
        if self.current_quality is not None:
            stats["current_quality"] = self.current_quality
        if self.max_quality is not None:
            stats["max_quality"] = self.max_quality

        return OwnedWeapon(
            id=self.weapon_id,
            weapon_name=self.weapon_name,
            quality_val=self.current_quality if self.current_quality is not None else self.max_quality,
            quality_is_exact=self.exact or self.saved,
            wear="worn",
            stats=stats,
            passives=passives_list,
            raw_line=self.raw_line,
        )


@dataclass(frozen=True)
class ParsedNeonPage:
    """Represents a parsed multi-line Neon weapon inventory page."""

    owner_user_id: int
    total_weapons: int
    saved_inventory: bool
    weapon_type: str
    passive_types: tuple[str, ...]
    rows: tuple[ParsedWeaponRow, ...]


def normalize_alias(value: str) -> str:
    """Strip all non-alphanumeric characters and lowercase."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def normalize_weapon(value: str) -> str:
    """Normalize weapon name or alias to canonical slug."""
    return WEAPON_ALIASES.get(normalize_alias(value), "")


def normalize_passive(value: str) -> str:
    """Normalize passive name or alias to canonical slug."""
    return PASSIVE_ALIASES.get(normalize_alias(value), "")


def split_hyphen_spaces(s: str) -> list[str]:
    """Split string on spaces/hyphens without splitting hyphenated numbers."""
    normalized = re.sub(r"-+", "-", s)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r",+", ",", normalized)
    normalized = re.sub(r"\.{2,}", ".", normalized).strip()
    parts = re.split(r"(?<!\d)[ -]|[ -](?!\d)", normalized)
    return [p for p in parts if p]


def alias_candidates_from_emoji_name(name: str) -> tuple[str, ...]:
    """Return canonicalization candidates for a Neon emoji name (stripping prefixes)."""
    normalized = normalize_alias(name)
    if not normalized:
        return ()
    candidates: list[str] = [normalized]
    for prefix in NEON_CONTEXT_PREFIXES:
        if normalized.startswith(prefix) and len(normalized) > len(prefix) + 1:
            stripped = normalized[len(prefix) :]
            if stripped and stripped not in candidates:
                candidates.append(stripped)

    suffix_aliases = sorted(
        {
            alias
            for alias in (*WEAPON_ALIASES.keys(), *PASSIVE_ALIASES.keys())
            if len(alias) >= 3
        },
        key=len,
        reverse=True,
    )
    for alias in suffix_aliases:
        if normalized.endswith(alias) and alias not in candidates:
            candidates.append(alias)
    return tuple(candidates)


def classify_neon_emoji_names(names: tuple[str, ...] | list[str]) -> tuple[str, tuple[str, ...]]:
    """Infer weapon type and passive types from custom emoji names."""
    weapon_type = ""
    passive_types: list[str] = []
    for name in names:
        candidates = alias_candidates_from_emoji_name(name)
        if not weapon_type:
            for candidate in candidates:
                weapon = normalize_weapon(candidate)
                if weapon:
                    weapon_type = weapon
                    break
        for candidate in candidates:
            passive = normalize_passive(candidate)
            if passive and passive not in passive_types:
                passive_types.append(passive)
                break
    return weapon_type, tuple(passive_types)


def parse_filters(text: str) -> tuple[str, tuple[str, ...]]:
    """Extract filter constraints from page header if present."""
    match = FILTER_LINE_RE.search(text or "")
    if match is None:
        return "", ()
    filter_text = match.group(1)
    weapon_type = ""
    passives: list[str] = []
    for name, _emoji_id in CUSTOM_EMOJI_RE.findall(filter_text):
        weapon = normalize_weapon(name)
        passive = normalize_passive(name)
        if weapon and not weapon_type:
            weapon_type = weapon
        elif passive and passive not in passives:
            passives.append(passive)
    return weapon_type, tuple(passives)


def emoji_names_before_quality(body: str) -> tuple[str, ...]:
    """Return custom emoji names that appear before the visible quality percent."""
    quality_match = QUALITY_RE.search(body or "")
    prefix = body[: quality_match.start()] if quality_match else body
    return tuple(name for name, _emoji_id in CUSTOM_EMOJI_RE.findall(prefix))


def has_exact_or_saved_marker(text: str) -> bool:
    """Check if the row text contains an exact or saved marker."""
    lowered = (text or "").casefold()
    return (
        "<:saved:" in lowered
        or "<:exact:" in lowered
        or ":saved:" in lowered
        or ":exact:" in lowered
        or "✅" in text
        or "✔" in text
        or "✓" in text
    )


def has_max_possible_marker(text: str) -> bool:
    """Check if the row text contains an estimated/max_possible marker."""
    lowered = (text or "").casefold()
    return (
        "<:max_possible:" in lowered
        or ":max_possible:" in lowered
        or STATUS_EMOJIS["max_possible"] in text
    )


def parse_weapon_row(
    line: str,
    *,
    saved_inventory: bool = False,
    default_weapon_type: str = "",
    default_passives: tuple[str, ...] = (),
) -> ParsedWeaponRow | None:
    """Parse a single line from NeonUtil weapon inventory into a ParsedWeaponRow."""
    match = WEAPON_ROW_RE.match(line)
    if match is None:
        return None
    weapon_id = match.group(1).upper()
    body = match.group(2)

    quality_match = QUALITY_RE.search(body)
    current_quality = float(quality_match.group(1)) if quality_match else None

    max_numbers = BACKTICK_NUMBER_RE.findall(body)
    max_quality = float(max_numbers[-1]) if max_numbers else None

    emoji_names = emoji_names_before_quality(body)
    row_weapon_type, row_passive_types = classify_neon_emoji_names(emoji_names)

    if not row_weapon_type and default_weapon_type:
        row_weapon_type = default_weapon_type

    combined_passives = list(row_passive_types)
    for p in default_passives:
        if p not in combined_passives:
            combined_passives.append(p)

    emojis = tuple(emoji_id for _name, emoji_id in CUSTOM_EMOJI_RE.findall(body))
    max_possible = has_max_possible_marker(body)
    exact = has_exact_or_saved_marker(body)
    saved = saved_inventory or exact

    return ParsedWeaponRow(
        weapon_id=weapon_id,
        raw_line=line.strip(),
        current_quality=current_quality,
        max_quality=max_quality,
        max_possible=max_possible,
        exact=exact,
        saved=saved,
        weapon_type=row_weapon_type,
        passive_types=tuple(combined_passives),
        emoji_ids=emojis,
        empowered_unresolved=len(emojis) >= 3 and not (saved or exact or max_possible),
    )


def parse_neon_weapon_page(text: str) -> ParsedNeonPage | None:
    """Parse a full NeonUtil weapon inventory page including header, filters, and rows."""
    header = NEON_HEADER_RE.search(text or "")
    if header is None:
        return None
    owner_user_id = int(header.group(1))
    total_weapons = int(header.group(2).replace(",", ""))
    saved_inventory = bool(header.group(3))
    weapon_type, passive_types = parse_filters(text)

    rows: list[ParsedWeaponRow] = []
    for line in (text or "").splitlines():
        row = parse_weapon_row(
            line,
            saved_inventory=saved_inventory,
            default_weapon_type=weapon_type,
            default_passives=passive_types,
        )
        if row is not None:
            rows.append(row)

    if not rows:
        return None

    return ParsedNeonPage(
        owner_user_id=owner_user_id,
        total_weapons=total_weapons,
        saved_inventory=saved_inventory,
        weapon_type=weapon_type,
        passive_types=passive_types,
        rows=tuple(rows),
    )


def parse_neon_inventory(text: str) -> list[OwnedWeapon]:
    """Extract all weapons from a NeonUtil `/weapon inv view` text into OwnedWeapon objects."""
    page = parse_neon_weapon_page(text)
    if page is not None:
        return [row.to_owned_weapon() for row in page.rows]

    # Fallback to row-by-row parsing if page header is missing
    weapons: list[OwnedWeapon] = []
    for line in (text or "").splitlines():
        row = parse_weapon_row(line)
        if row is not None:
            weapons.append(row.to_owned_weapon())
    return weapons


def parse_blueprint(text: str) -> str | None:
    """Extract a candidate blueprint string from text (e.g. `sword 31,7 mtap 77`)."""
    candidates = [c.strip() for c in BLUEPRINT_RE.findall(text or "")]
    for candidate in reversed(candidates):
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_'-]*", candidate)
        if not tokens:
            continue
        if any(normalize_weapon(token) for token in tokens):
            return candidate

    # Check unquoted single line text
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if len(lines) == 1:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_'-]*", lines[0])
        if any(normalize_weapon(token) for token in tokens) and len(tokens) <= 8:
            return lines[0]
    return None


def classify_blueprint(blueprint: str) -> tuple[str, tuple[str, ...]]:
    """Infer weapon type and passive types from a blueprint string."""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_'-]*", blueprint or "")
    weapon_type = ""
    passive_types: list[str] = []
    for token in tokens:
        if not weapon_type:
            weapon = normalize_weapon(token)
            if weapon:
                weapon_type = weapon
                continue
        passive = normalize_passive(token)
        if passive and passive not in passive_types:
            passive_types.append(passive)
    return weapon_type, tuple(passive_types)


def _is_weapon_id_token(token: str) -> bool:
    """Check if token is a 6-character weapon ID rather than an alias or wear name."""
    if not re.fullmatch(r"[A-Z0-9]{6}", token, re.IGNORECASE):
        return False
    lowered = token.casefold()
    if lowered in WEAPON_ALIASES or lowered in PASSIVE_ALIASES or lowered in WEAR_NAMES:
        return False
    return True


def parse_weapon_blueprint(text: str) -> OwnedWeapon:
    """Parse detailed `owo weapon <id>` inspection output or pure blueprint string into OwnedWeapon."""
    source = (text or "").strip()
    cleaned = re.sub(r"\*{1,2}", "", source)

    # 1. Attempt detailed inspection format parsing
    is_detailed_inspection = any(
        re.search(pattern, cleaned, re.IGNORECASE)
        for pattern in (r"\bID:\s*", r"\bQuality:\s*", r"\bWP Cost:\s*", r"\bShard Value:\s*")
    )

    if is_detailed_inspection:
        # Extract weapon ID
        id_match = re.search(r"\bID:\s*`?([A-Z0-9]{6})`?", cleaned, re.IGNORECASE)
        if not id_match:
            id_match = WEAPON_ID_RE.search(cleaned)
        weapon_id = id_match.group(1).upper() if id_match else "UNKNOWN"

        # Extract name
        name_match = re.search(r"\bName:\s*([^\n\r]+)", cleaned, re.IGNORECASE)
        raw_name = name_match.group(1).strip() if name_match else ""

        # Extract wear
        wear_match = re.search(r"\bWear:\s*([a-zA-Z]+)", cleaned, re.IGNORECASE)
        wear = wear_match.group(1).strip().lower() if wear_match else ""
        if wear not in WEAR_NAMES:
            # Check title line for wear
            first_line = cleaned.splitlines()[0] if cleaned.splitlines() else ""
            for w in WEAR_NAMES:
                if re.search(rf"\b{w}\b", first_line, re.IGNORECASE):
                    wear = w
                    break
            if not wear:
                wear = "worn"

        # Extract quality percentage
        qual_match = re.search(r"\bQuality:\s*([0-9]+(?:\.[0-9]+)?)\s*%", cleaned, re.IGNORECASE)
        quality_val = float(qual_match.group(1)) if qual_match else None

        # Extract WP cost
        wp_match = re.search(r"\bWP Cost:\s*([0-9]+)", cleaned, re.IGNORECASE)
        stats: dict[str, Any] = {}
        if wp_match:
            stats["wp_cost"] = int(wp_match.group(1))

        # Check description for base stat percentages (e.g. Deals 55% of your STR)
        for stat_name in ("str", "mag", "hp", "wp", "pr", "mr"):
            stat_match = re.search(rf"([0-9]+(?:\.[0-9]+)?)\s*%\s*of\s*your\s*:{stat_name}:?\s*{stat_name}", cleaned, re.IGNORECASE)
            if not stat_match:
                stat_match = re.search(rf"([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:of\s*your\s*)?{stat_name}", cleaned, re.IGNORECASE)
            if stat_match:
                stats[stat_name] = float(stat_match.group(1))

        # Extract passives
        passives_list: list[dict[str, Any]] = []
        passives_section = re.search(r"\bPassives?:\s*(.*)", cleaned, re.IGNORECASE | re.DOTALL)
        if passives_section:
            for p_line in passives_section.group(1).splitlines():
                p_line = p_line.strip().lstrip("-*• ")
                if not p_line or ":" in p_line and any(k in p_line for k in ("Owner", "ID", "Shard")):
                    continue
                # Match "Mana Tap: 77%" or "Mana Tap (77%)"
                p_match = re.search(r"([A-Za-z\s'-]+)(?:[:(]\s*([0-9]+(?:\.[0-9]+)?)\s*%?\s*\)?)?", p_line)
                if p_match:
                    p_name = p_match.group(1).strip()
                    p_slug = normalize_passive(p_name)
                    if p_slug:
                        val = float(p_match.group(2)) if p_match.group(2) else None
                        passives_list.append({
                            "name": PASSIVE_LABELS.get(p_slug, p_name),
                            "slug": p_slug,
                            "stat": val,
                        })

        # Canonicalize weapon name
        if not raw_name:
            # Check title
            first_line = cleaned.splitlines()[0] if cleaned.splitlines() else ""
            for alias, canon in WEAPON_ALIASES.items():
                if re.search(rf"\b{alias}\b", first_line, re.IGNORECASE):
                    raw_name = WEAPON_LABELS.get(canon, canon)
                    break
        canonical_name = raw_name or "Unknown Weapon"

        # Embedded blueprint if any
        bp_candidate = parse_blueprint(source) or ""

        return OwnedWeapon(
            id=weapon_id,
            weapon_name=canonical_name,
            quality_val=quality_val,
            quality_is_exact=True,
            wear=wear,
            stats=stats,
            passives=passives_list,
            raw_line=source,
            blueprint=bp_candidate,
        )

    # 2. Pure blueprint string parsing (e.g. `pristine sword 31,7 mtap 77` or `sword-31,7-mtap-77`)
    candidate = parse_blueprint(source) or source.strip("` ")
    tokens = split_hyphen_spaces(candidate)

    weapon_id = ""
    for tok in tokens:
        if _is_weapon_id_token(tok) and not weapon_id:
            weapon_id = tok.upper()

    tokens = [t for t in tokens if t.upper() != weapon_id]

    wear = "worn"
    if tokens and tokens[0].lower() in WEAR_NAMES:
        wear = tokens[0].lower()
        tokens = tokens[1:]

    weapon_type = ""
    weapon_stats: list[float] = []
    passives_list = []
    all_stat_percentages: list[float] = []

    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        w = normalize_weapon(tok)
        p = normalize_passive(tok)
        if w and not weapon_type:
            weapon_type = w
            idx += 1
            if idx < len(tokens) and re.match(r"^[\d.,]+$", tokens[idx]):
                weapon_stats = [float(x) for x in tokens[idx].split(",") if x]
                all_stat_percentages.extend(weapon_stats)
                idx += 1
            continue
        if p:
            p_slug = p
            idx += 1
            p_stats: list[float] = []
            if idx < len(tokens) and re.match(r"^[\d.,]+$", tokens[idx]):
                p_stats = [float(x) for x in tokens[idx].split(",") if x]
                all_stat_percentages.extend(p_stats)
                idx += 1
            passives_list.append({
                "slug": p_slug,
                "name": PASSIVE_LABELS.get(p_slug, p_slug),
                "stats": p_stats,
            })
            continue
        idx += 1

    # Quality is calculated from stat percentages if present
    calculated_quality = (
        round(sum(all_stat_percentages) / len(all_stat_percentages), 1)
        if all_stat_percentages
        else None
    )

    weapon_name = WEAPON_LABELS.get(weapon_type, weapon_type or "Unknown Weapon")

    return OwnedWeapon(
        id=weapon_id or "UNKNOWN",
        weapon_name=weapon_name,
        quality_val=calculated_quality,
        quality_is_exact=True,
        wear=wear,
        stats={"base_stats": weapon_stats} if weapon_stats else {},
        passives=passives_list,
        raw_line=source,
        blueprint=candidate,
    )


STANDARD_ANIMAL_NAMES = frozenset({
    "bee", "bug", "snail", "beetle", "clam", "crab", "squid", "caterpillar",
    "spider", "ant", "flea", "worm", "sloth", "chicken", "duck", "bat", "mouse",
    "pig", "hedgehog", "skunk", "badger", "sheep", "alpaca", "rabbit", "otter",
    "wolf", "fox", "cow", "horse", "dove", "deer", "panda", "monkey", "seal",
    "llama", "zebra", "goat", "boar", "dog", "cat", "bear", "lion", "tiger",
    "elephant", "rhino", "hippo", "dino", "alligator", "snake", "eagle",
    "owl", "flamingo", "crow", "frog", "cheetah", "kangaroo", "gorilla", "giraffe",
    "giraffbot", "whale", "shark", "dolphin", "peacock", "lobster", "bison", "swan"
})

ANIMAL_RANK_PREFIXES = ("g", "c", "u", "r", "e", "m", "l", "f", "d", "p", "b", "h")


def normalize_animal_name(name_or_emoji: str) -> str:
    """Normalize animal token or Discord emoji alias into a canonical animal name."""
    cleaned = (name_or_emoji or "").strip().lower()
    cleaned = re.sub(r"^[<:a]+|[:>]+$", "", cleaned).strip()
    if not cleaned:
        return ""
    if cleaned in STANDARD_ANIMAL_NAMES:
        return cleaned
    for animal in sorted(STANDARD_ANIMAL_NAMES, key=len, reverse=True):
        if cleaned.endswith(animal):
            prefix = cleaned[:-len(animal)]
            if not prefix or prefix in ANIMAL_RANK_PREFIXES:
                return animal
    # Fallback to alphanumeric token
    tokens = re.findall(r"[a-z0-9_]+", cleaned)
    return tokens[0] if tokens else cleaned


def parse_team_message(text: str) -> dict[str, Any] | None:
    """
    Parse an OwO team message into active animals and equipped weapons.
    Expects section markers [1], [2], [3] and associated pet/weapon rows.
    Returns dict with 'animals', 'weapons', and 'slots' or None if not a team message.
    """
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    # Clean emoji syntax: <:deagle:12345> -> :deagle:
    cleaned = re.sub(r"<a?:([A-Za-z0-9_]+):\d+>", r":\1:", cleaned)

    sec_re = re.compile(r"(?m)^[ \t]*\[([1-3])\](?:[ \t]+([^\n]*?))?[ \t]*$")
    matches = list(sec_re.finditer(cleaned))
    if len(matches) < 2:  # OwO team messages typically have 3 slots
        return None

    animals: list[OwnedAnimal] = []
    weapons: list[OwnedWeapon] = []
    slots: list[dict[str, Any]] = []

    for i, m in enumerate(matches):
        pos = int(m.group(1))
        line_header = (m.group(2) or "").strip()
        next_pos = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
        section = cleaned[m.end():next_pos]
        combined = f"{line_header}\n{section}"

        # Extract animal name
        animal_name = None
        emoji_match = re.search(r":([A-Za-z0-9_]+):", combined)
        if emoji_match:
            cand = normalize_animal_name(emoji_match.group(1))
            if cand not in ("hp", "wp", "str", "mag", "level", "lvl", "weapon", "slot"):
                animal_name = cand

        if not animal_name:
            for cand in STANDARD_ANIMAL_NAMES:
                if re.search(r"\b" + re.escape(cand) + r"\b", combined, re.IGNORECASE):
                    animal_name = cand
                    break

        if not animal_name:
            tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9_]+", line_header)]
            valid_tokens = [t for t in tokens if t not in ("hp", "wp", "str", "mag", "level", "lvl", "weapon", "slot")]
            if valid_tokens:
                animal_name = normalize_animal_name(valid_tokens[0])

        if not animal_name:
            continue

        # Extract level
        lvl_match = re.search(r"(?:Lvl|Level|lvl)\s*(\d+)", combined, re.IGNORECASE)
        level = int(lvl_match.group(1)) if lvl_match else 50

        # Extract weapon ID
        w_id_match = re.search(r"\b([A-Z0-9]{6})\b", section, re.IGNORECASE)
        if not w_id_match:
            w_id_match = re.search(r"ID:\s*([A-Za-z0-9]+)", section, re.IGNORECASE)
        weapon_id = w_id_match.group(1).upper() if w_id_match else f"W{pos}"

        # Extract quality
        q_match = re.search(r"(\d+(?:\.\d+)?)\s*%", section)
        quality_val = float(q_match.group(1)) if q_match else 85.0

        # Extract weapon name
        weapon_name = "Defender's Aegis" if pos == 1 else "Great Sword"
        for alias, slug in WEAPON_ALIASES.items():
            if re.search(r"\b" + re.escape(alias) + r"\b", section, re.IGNORECASE):
                weapon_name = WEAPON_LABELS.get(slug, slug.title())
                break

        animal_obj = OwnedAnimal(name=animal_name, level=level, equipped_weapon_id=weapon_id)
        weapon_obj = OwnedWeapon(
            id=weapon_id,
            weapon_name=weapon_name,
            quality_val=quality_val,
            quality_is_exact=True,
            raw_line=section.strip(),
        )

        animals.append(animal_obj)
        weapons.append(weapon_obj)
        slots.append({
            "position": pos,
            "animal": animal_name,
            "level": level,
            "weapon_id": weapon_id,
            "weapon_name": weapon_name,
            "quality": quality_val,
        })

    return {
        "animals": animals,
        "weapons": weapons,
        "slots": slots,
    }


def parse_weapon_inventory_message(text: str) -> list[OwnedWeapon]:
    """
    Parse an OwO or NeonUtil weapon inventory message into a list of OwnedWeapon instances.
    Handles NeonUtil /weapon inv views, embed weapon listings, and standard OwO formats.
    """
    # 1. Try NeonUtil inventory parser
    neon_weapons = parse_neon_inventory(text)
    if neon_weapons:
        return neon_weapons

    # 2. Line-by-line fallback for OwO native weapon inventory
    weapons: list[OwnedWeapon] = []
    lines = (text or "").splitlines()
    row_pattern = re.compile(
        r"(?:`|\[)?\s*([A-Z0-9]{3,8})\s*(?:`|\])?\s*[-|:]?\s*([A-Za-z0-9' ]+?)\s*(?:[-|:(]|\*\*|\s+)\s*(\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    )

    for line in lines:
        match = row_pattern.search(line)
        if match:
            w_id = match.group(1).upper()
            w_raw_name = match.group(2).strip()
            q_val = float(match.group(3))

            # Normalize weapon name
            w_slug = normalize_weapon(w_raw_name)
            w_name = WEAPON_LABELS.get(w_slug, w_raw_name)

            weapons.append(
                OwnedWeapon(
                    id=w_id,
                    weapon_name=w_name,
                    quality_val=q_val,
                    quality_is_exact=True,
                    raw_line=line.strip(),
                )
            )

    return weapons


def parse_neon_calculation_message(message_or_text: Any) -> list[OwnedWeapon]:
    """
    Parse NeonUtil max quality calculation embeds and text responses.
    Triggered by reacting with <a:calculate:1263895039172677692> or 🧮.
    Extracts weapon ID, exact quality percentage, passives, wear, locked status,
    and safe dismantle / shard markers.
    """
    chunks: list[str] = []
    if isinstance(message_or_text, str):
        chunks.append(message_or_text)
    elif isinstance(message_or_text, dict):
        if message_or_text.get("content"):
            chunks.append(str(message_or_text["content"]))
        if message_or_text.get("title"):
            chunks.append(str(message_or_text["title"]))
        if message_or_text.get("description"):
            chunks.append(str(message_or_text["description"]))
        auth = message_or_text.get("author")
        if isinstance(auth, dict) and auth.get("name"):
            chunks.append(str(auth["name"]))
        for f in message_or_text.get("fields", []):
            if isinstance(f, dict):
                chunks.append(f"{f.get('name', '')} {f.get('value', '')}")
        for emb in message_or_text.get("embeds", []):
            if isinstance(emb, dict):
                if emb.get("title"):
                    chunks.append(str(emb["title"]))
                if emb.get("description"):
                    chunks.append(str(emb["description"]))
                auth = emb.get("author")
                if isinstance(auth, dict) and auth.get("name"):
                    chunks.append(str(auth["name"]))
                for f in emb.get("fields", []):
                    if isinstance(f, dict):
                        chunks.append(f"{f.get('name', '')} {f.get('value', '')}")
    else:
        # Object-like (discord.Message)
        if getattr(message_or_text, "content", None):
            chunks.append(str(message_or_text.content))
        for emb in getattr(message_or_text, "embeds", []):
            if getattr(emb, "title", None):
                chunks.append(str(emb.title))
            if getattr(emb, "description", None):
                chunks.append(str(emb.description))
            if getattr(emb, "author", None) and getattr(emb.author, "name", None):
                chunks.append(str(emb.author.name))
            for f in getattr(emb, "fields", []):
                chunks.append(f"{getattr(f, 'name', '')} {getattr(f, 'value', '')}")

    full_text = "\n".join(chunks)
    if not full_text:
        return []

    # Guard: Must be a Neon calculation message (header or signature emojis)
    if not (
        MAX_QUALITY_HEADER_RE.search(full_text)
        or "max_possible" in full_text
        or "0_min_quality" in full_text
        or "Max qualities" in full_text
    ):
        return []

    weapons: list[OwnedWeapon] = []
    for line in full_text.splitlines():
        id_match = re.search(r"`([A-Z0-9]{6})`", line, re.IGNORECASE)
        if not id_match:
            continue
        w_id = id_match.group(1).upper()

        q_match = re.search(r"`([0-9]+(?:\.[0-9]+)?)\s*%`", line)
        if not q_match:
            q_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", line)
        quality = float(q_match.group(1)) if q_match else None

        locked = "🔐" in line
        dismantle = "💀" in line or "☠️" in line or "0_min_quality" in line
        shard = "ws" in line or "0_min_quality" in line or dismantle

        # Wear detection
        wear = "worn"
        if "pristine" in line.lower():
            wear = "pristine"
        elif "fine" in line.lower():
            wear = "fine"
        elif "decent" in line.lower():
            wear = "decent"

        # Emojis for weapon and passive classification
        emojis = [name for name, _ in CUSTOM_EMOJI_RE.findall(line)]
        w_type, p_types = classify_neon_emoji_names(emojis)
        w_name = WEAPON_LABELS.get(w_type, w_type.title() if w_type else "Unknown Weapon")

        # Check for max possible quality marker or explicit max value
        max_possible = None
        if "max_possible" in line:
            max_possible = quality  # upper bound roll flag

        weapons.append(
            OwnedWeapon(
                id=w_id,
                weapon_name=w_name,
                quality_val=quality,
                quality_is_exact=True,
                wear=wear,
                passives=list(p_types),
                raw_line=line.strip(),
                is_locked=locked,
                max_possible_quality=max_possible,
                is_dismantle_candidate=dismantle,
                is_shard_candidate=shard,
            )
        )

    return weapons


__all__ = [
    "WEAPON_ID_RE",
    "CUSTOM_EMOJI_RE",
    "NEON_HEADER_RE",
    "FILTER_LINE_RE",
    "WEAPON_ROW_RE",
    "QUALITY_RE",
    "BACKTICK_NUMBER_RE",
    "BLUEPRINT_RE",
    "MAX_QUALITY_HEADER_RE",
    "STATUS_EMOJIS",
    "WEAPON_ALIASES",
    "PASSIVE_ALIASES",
    "WEAPON_LABELS",
    "PASSIVE_LABELS",
    "WEAR_NAMES",
    "STANDARD_ANIMAL_NAMES",
    "ANIMAL_RANK_PREFIXES",
    "ParsedWeaponRow",
    "ParsedNeonPage",
    "normalize_alias",
    "normalize_weapon",
    "normalize_passive",
    "normalize_animal_name",
    "split_hyphen_spaces",
    "alias_candidates_from_emoji_name",
    "classify_neon_emoji_names",
    "parse_weapon_row",
    "parse_neon_weapon_page",
    "parse_neon_inventory",
    "parse_blueprint",
    "classify_blueprint",
    "parse_weapon_blueprint",
    "parse_team_message",
    "parse_weapon_inventory_message",
    "parse_neon_calculation_message",
]
