"""Catalog synchronization for OwO animals, weapons, and passives."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from owo_strategy.schemas.models import Animal, Passive, Weapon

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

ANIMALS_API_URL = "https://neonutil.com/api/animals"
FALLBACK_ANIMALS_PATH = Path("/tmp/owo_strategy_research/Basement/public/data/neonutilAnimalAPI.json")
WEAPONS_PATH = Path("/tmp/owo_strategy_research/Basement/src/data/weapons.json")
PASSIVES_PATH = Path("/tmp/owo_strategy_research/Basement/src/data/passives.json")

CATALOG_ANIMALS_FILE = DATA_DIR / "catalog_animals.json"
CATALOG_WEAPONS_FILE = DATA_DIR / "catalog_weapons.json"
CATALOG_PASSIVES_FILE = DATA_DIR / "catalog_passives.json"


def fetch_raw_animals(
    api_url: str = ANIMALS_API_URL,
    fallback_path: Path = FALLBACK_ANIMALS_PATH,
    timeout: float = 8.0,
    force_fallback: bool = False,
) -> dict[str, Any]:
    """Fetch animals data from live API with automatic fallback to local JSON file."""
    if not force_fallback:
        try:
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "OwOStrategyEngine/1.0 (+https://github.com/)"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    payload = json.loads(response.read().decode("utf-8"))
                    if isinstance(payload, dict) and "data" in payload:
                        logger.info("Successfully fetched animals from live API %s", api_url)
                        return payload
        except Exception as exc:
            logger.warning("Failed to fetch animals from %s (%s). Using fallback.", api_url, exc)

    if fallback_path.exists():
        logger.info("Loading animals from fallback file %s", fallback_path)
        with open(fallback_path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise FileNotFoundError(f"Could not fetch animals from {api_url} and fallback {fallback_path} does not exist.")


def normalize_animals(raw_payload: dict[str, Any]) -> list[Animal]:
    """Normalize raw NeonUtil animal API payload into Animal objects."""
    ranks = raw_payload.get("ranks", [])
    raw_data = raw_payload.get("data", [])

    animals: list[Animal] = []
    for entry in raw_data:
        # Expected row shape: [animated, name, id, aliases, stats, rank]
        animated = bool(entry[0]) if len(entry) > 0 else False
        name = str(entry[1]) if len(entry) > 1 else ""
        animal_id = str(entry[2]) if len(entry) > 2 else ""
        aliases = list(entry[3]) if len(entry) > 3 and isinstance(entry[3], list) else []
        stats_raw = list(entry[4]) if len(entry) > 4 and isinstance(entry[4], (list, tuple)) else [0, 0, 0, 0, 0, 0]
        rank_idx = entry[5] if len(entry) > 5 else 0

        rank_name = ranks[rank_idx] if isinstance(rank_idx, int) and 0 <= rank_idx < len(ranks) else str(rank_idx)

        dex_stats = {
            "hp": int(stats_raw[0]) if len(stats_raw) > 0 else 0,
            "str": int(stats_raw[1]) if len(stats_raw) > 1 else 0,
            "pr": int(stats_raw[2]) if len(stats_raw) > 2 else 0,
            "wp": int(stats_raw[3]) if len(stats_raw) > 3 else 0,
            "mag": int(stats_raw[4]) if len(stats_raw) > 4 else 0,
            "mr": int(stats_raw[5]) if len(stats_raw) > 5 else 0,
        }

        animals.append(
            Animal(
                id=animal_id,
                name=name,
                rank=rank_name,
                dex_stats=dex_stats,
                aliases=aliases,
                animated=animated,
            )
        )
    return animals


def load_raw_weapons(file_path: Path = WEAPONS_PATH) -> list[dict[str, Any]]:
    """Load raw weapons JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Weapons file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_weapons(raw_weapons: list[dict[str, Any]]) -> list[Weapon]:
    """Normalize raw weapons list into Weapon objects."""
    weapons: list[Weapon] = []
    for raw in raw_weapons:
        wp_config = raw.get("rawWPStatConfig")
        wp_cost_range = None
        if wp_config and isinstance(wp_config, dict):
            c_min = wp_config.get("min", 0)
            c_max = wp_config.get("max", 0)
            wp_cost_range = [min(c_min, c_max), max(c_min, c_max)]

        weapon = Weapon(
            id=raw.get("id"),
            name=str(raw.get("name", "")),
            wp_cost_range=wp_cost_range,
            stat_ranges=list(raw.get("rawStatConfigs", [])),
            passive_slots=int(raw.get("normalPassiveAmount", 1 if raw.get("objectType") == "weapon" else 0)),
            description=str(raw.get("description", "")),
            active_ability=raw.get("buffSlugs") or None,
            slug=str(raw.get("slug", "")),
            aliases=list(raw.get("aliases", [])),
            buff_slugs=list(raw.get("buffSlugs", [])),
        )
        weapons.append(weapon)
    return weapons


def load_raw_passives(file_path: Path = PASSIVES_PATH) -> list[dict[str, Any]]:
    """Load raw passives JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Passives file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_passives(raw_passives: list[dict[str, Any]]) -> list[Passive]:
    """Normalize raw passives list into Passive objects."""
    passives: list[Passive] = []
    for raw in raw_passives:
        passive = Passive(
            name=str(raw.get("name", "")),
            stat_boosts=list(raw.get("rawStatConfigs", [])),
            description=str(raw.get("description", "")),
            effect_type=str(raw.get("objectType", "passive")),
            slug=str(raw.get("slug", "")),
            aliases=list(raw.get("aliases", [])),
            buff_slugs=list(raw.get("buffSlugs", [])),
        )
        passives.append(passive)
    return passives


def sync_animals(
    output_path: Path = CATALOG_ANIMALS_FILE,
    force_fallback: bool = False,
) -> list[Animal]:
    """Sync animals catalog and persist to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_payload = fetch_raw_animals(force_fallback=force_fallback)
    animals = normalize_animals(raw_payload)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([a.to_dict() for a in animals], f, indent=2)
    logger.info("Saved %d normalized animals to %s", len(animals), output_path)
    return animals


def sync_weapons(
    output_path: Path = CATALOG_WEAPONS_FILE,
    source_path: Path = WEAPONS_PATH,
) -> list[Weapon]:
    """Sync weapons catalog and persist to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_weapons = load_raw_weapons(source_path)
    weapons = normalize_weapons(raw_weapons)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([w.to_dict() for w in weapons], f, indent=2)
    logger.info("Saved %d normalized weapons to %s", len(weapons), output_path)
    return weapons


def sync_passives(
    output_path: Path = CATALOG_PASSIVES_FILE,
    source_path: Path = PASSIVES_PATH,
) -> list[Passive]:
    """Sync passives catalog and persist to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_passives = load_raw_passives(source_path)
    passives = normalize_passives(raw_passives)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in passives], f, indent=2)
    logger.info("Saved %d normalized passives to %s", len(passives), output_path)
    return passives


def sync_all(force_fallback: bool = False) -> dict[str, int]:
    """Synchronize all catalogs (animals, weapons, passives) into data/."""
    animals = sync_animals(force_fallback=force_fallback)
    weapons = sync_weapons()
    passives = sync_passives()
    return {
        "animals": len(animals),
        "weapons": len(weapons),
        "passives": len(passives),
    }


def load_catalog_animals(path: Path = CATALOG_ANIMALS_FILE) -> list[Animal]:
    """Load normalized animals from persisted JSON catalog."""
    if not path.exists():
        return sync_animals(output_path=path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Animal.from_dict(item) for item in data]


def load_catalog_weapons(path: Path = CATALOG_WEAPONS_FILE) -> list[Weapon]:
    """Load normalized weapons from persisted JSON catalog."""
    if not path.exists():
        return sync_weapons(output_path=path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Weapon.from_dict(item) for item in data]


def load_catalog_passives(path: Path = CATALOG_PASSIVES_FILE) -> list[Passive]:
    """Load normalized passives from persisted JSON catalog."""
    if not path.exists():
        return sync_passives(output_path=path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Passive.from_dict(item) for item in data]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    counts = sync_all()
    print("Catalog sync complete:", counts)
