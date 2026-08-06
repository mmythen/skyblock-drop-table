import json
import html

RARITY_MAP = {
    "Common": "c",
    "common": "c",
    "Uncommon": "u",
    "uncommon": "u",
    "Rare": "r",
    "rare": "r",
    "Epic": "e",
    "epic": "e",
    "Legendary": "l",
    "legendary": "l",
    "Rng": "rng",
    "RNGesus": "rng",
}


def clean(obj):
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [clean(x) for x in obj]

    if isinstance(obj, str):
        # Decode HTML entities
        obj = html.unescape(obj)

        # Remove HTML line breaks
        obj = obj.replace("<br>", " ")

        # Normalize rarity names
        if obj in RARITY_MAP:
            obj = RARITY_MAP[obj]

        return obj

    return obj


with open("loot_table.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Clean all strings in the JSON
data = clean(data)

# Keep only entries that have at least one non-empty drop table
filtered = [
    entry for entry in data
    if entry["drops"] and any(
        table.get("drops") if isinstance(table, dict) and "drops" in table else True
        for table in entry["drops"]
    )
]

with open("loot_table.json", "w", encoding="utf-8") as f:
    json.dump(filtered, f, indent=4, ensure_ascii=False)

print(f"Kept {len(filtered)} of {len(data)} entries")