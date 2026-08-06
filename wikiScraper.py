import requests
import time
import re
import json

BASE_URL = "https://hypixel-skyblock.fandom.com/api.php"
HEADERS = {"User-Agent": "github.com/mmythen"}


def get_mobs():
    """Walk Category:Mobs and its subcategories, returning {pageid: title} for all mob pages."""
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:Mobs",
        "cmlimit": 500,
        "cmtype": "page|subcat",
        "format": "json"
    }
    data = requests.get(BASE_URL, params=params, headers=HEADERS).json()
    mobs = {}

    def search(members):
        for member in members:
            if member["title"] == "Category:Non-player characters" or member["pageid"] in mobs:
                continue
            if member["title"].startswith("Category:"):
                sub_params = {
                    "action": "query",
                    "list": "categorymembers",
                    "cmtitle": member["title"],
                    "cmlimit": 500,
                    "format": "json"
                }
                sub_data = requests.get(BASE_URL, params=sub_params, headers=HEADERS).json()
                time.sleep(0.3)
                search(sub_data["query"]["categorymembers"])
            elif member["ns"] == 0:
                mobs[member["pageid"]] = member["title"]

    search(data["query"]["categorymembers"])
    return mobs


def find_templates(wikitext, template_name):
    """Find all {{template_name ...}} blocks, handling nested braces."""
    blocks = []
    search_str = "{{" + template_name
    start = 0

    while True:
        idx = wikitext.find(search_str, start)
        if idx == -1:
            break
        depth, i = 0, idx
        while i < len(wikitext) - 1:
            if wikitext[i:i+2] == "{{":
                depth += 1
                i += 2
            elif wikitext[i:i+2] == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    break
            else:
                i += 1
        blocks.append(wikitext[idx+2:i-2])
        start = i

    return blocks


def clean_item_name(name):
    """Strip ref tags, handle enchant notation, and clean junk from an item name."""
    name = re.sub(r"<ref.*?(</ref>|/>)", "", name, flags=re.DOTALL)
    name = name.strip("[]")

    enchant_match = re.search(r"&([^&]+)&", name)
    if enchant_match:
        base = name.split("&")[0].strip()
        return f"{base} ({enchant_match.group(1).strip()})"

    name = name.split("!")[0]
    name = re.split(r"\[\[", name)[0]
    return name.split(";")[0].strip()


def clean_value(value):
    """Strip HTML spans, refs, and unresolved templates from a field value."""
    value = re.sub(r"<ref.*?(</ref>|/>)", "", value, flags=re.DOTALL)
    value = re.sub(r"<span[^>]*>(.*?)</span>", r"\1", value)  # drop tags
    value = re.sub(r"\{\{InfoNeeded\}\}", "", value)
    value = re.sub(r"\{\{bc\}\}", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\{\{Overline.*", "", value)
    value = re.sub(r"\{\{Odds.*", "", value)
    value = value.strip()
    return value or None


def drop_table(wikitext):
    """Parse all {{Mob Drops Table}} blocks into a list of drop tables."""
    tables = []

    for block in find_templates(wikitext, "Mob Drops Table"):
        fields = {}
        for line in block.split("|"):
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            fields[key.strip()] = clean_value(value)

        drops = []
        for key in fields:
            if not re.fullmatch(r"drop\d*", key):
                continue
            suffix = key[len("drop"):]
            item = clean_item_name(fields.get(f"drop{suffix}") or "")
            if not item:
                continue
            drops.append({
                "item": item,
                "count": fields.get(f"count{suffix}"),
                "rarity": fields.get(f"rarity{suffix}"),
                "chance": fields.get(f"chance{suffix}")
            })

        tables.append({
            "coins": fields.get("coins") or fields.get("c"),
            "exp": fields.get("exp"),
            "loot_share": fields.get("loot_share") == "true",
            "drops": drops
        })

    return tables


def slayer_drop_table(wikitext):
    """Parse the raw ==Drops== wikitable used by tiered slayer bosses."""
    wikitext = re.sub(r"<!--.*?-->", "", wikitext, flags=re.DOTALL)  # strip stale commented-out data

    section_match = re.search(r"==\s*Drops\s*==(.*?)(?=\n==[^=]|\Z)", wikitext, re.DOTALL)
    if not section_match:
        return []

    table_match = re.search(r"\{\|.*?\n\|\}", section_match.group(1), re.DOTALL)
    if not table_match:
        return []

    table_text = table_match.group(0)

    # tier count varies by boss
    header_end = table_text.find("|-\n|{{Slot")
    header_text = table_text[:header_end] if header_end != -1 else table_text
    num_tiers = len(re.findall(r"\{\{SlayerTier\|", header_text)) // 2 or 5
    tier_labels = ["I", "II", "III", "IV", "V"][:num_tiers]

    rows, current_row = [], []
    for line in table_text.split("\n"):
        line = line.strip()
        if line.startswith("|-"):
            if current_row:
                rows.append(current_row)
                current_row = []
            continue
        if not line.startswith("|") or line.startswith("|}") or line.startswith("|+"):
            continue

        cell = line[1:].strip()
        colspan = 1
        m = re.match(r'colspan="(\d+)"\s*\|(.*)', cell)
        if m:
            colspan, cell = int(m.group(1)), m.group(2).strip()
        elif "style=" in cell and "|" in cell:
            cell = cell.split("|", 1)[1].strip()

        current_row.append((cell, colspan))
    if current_row:
        rows.append(current_row)

    def clean_chance(val):
        if not val:
            return None
        val = re.sub(r"\{\{ConfirmationNeeded\}\}", "", val)
        m = re.search(r"\{\{g\|([^}]+)\}\}", val)
        val = m.group(1) if m else val
        val = val.strip()
        return val if val and "{{bc}}" not in val.lower() else None

    def clean_amount(val):
        if not val or "{{bc}}" in val.lower():
            return None
        return val.strip()

    def clean_slayer_item_name(name):
        name = re.sub(r"<ref.*?(</ref>|/>)", "", name, flags=re.DOTALL)
        return re.split(r"[!&]", name)[0].strip()

    drops = []
    expected_len = 3 + num_tiers + 1 + num_tiers  # icon+drop+lvl, amounts, odds, chances

    for row in rows:
        flat = []
        for value, span in row:
            flat.extend([value] * span)
        if len(flat) < expected_len:
            continue

        item_match = re.search(r"\{\{ID\|([^}|!&]+)", flat[1])
        if not item_match:
            continue
        item = clean_slayer_item_name(item_match.group(1))
        if not item:
            continue

        amounts = flat[3:3 + num_tiers]
        chances = flat[4 + num_tiers: 4 + num_tiers * 2]

        per_tier = [
            {
                "tier": tier,
                "amount": clean_amount(amounts[i]) if i < len(amounts) else None,
                "chance": clean_chance(chances[i]) if i < len(chances) else None
            }
            for i, tier in enumerate(tier_labels)
        ]
        drops.append({"item": item, "tiers": per_tier})

    return drops


SLAYER_BOSS_IDS = {89097, 80243, 6339, 6393, 6397}  # Inferno Demonlord, Voidgloom Seraph, Revenant Horror, Tarantula Broodfather, Sven Packmaster

mobs = get_mobs()

with open("loot_table.json", "r") as f:
    file_data = json.load(f)

for pageid, name in mobs.items():
    params = {"action": "parse", "pageid": pageid, "prop": "wikitext", "format": "json"}
    data = requests.get(BASE_URL, params=params, headers=HEADERS).json()
    time.sleep(0.1)
    wikitext = data["parse"]["wikitext"]["*"]

    parser = slayer_drop_table if pageid in SLAYER_BOSS_IDS else drop_table
    file_data.append({"name": name, "drops": parser(wikitext)})

with open("loot_table.json", "w") as f:
    json.dump(file_data, f, indent=4)

print("Done writing loot_table.json")