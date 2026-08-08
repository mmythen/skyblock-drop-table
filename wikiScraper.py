import requests
import time
import re
import json
import html


BASE_URL = "https://hypixel-skyblock.fandom.com/api.php"
HEADERS = {"User-Agent": "github.com/mmythen"}

SLAYER_BOSS_IDS = {
    89097,  # Inferno Demonlord
    80243,  # Voidgloom Seraph
    6339,   # Revenant Horror
    6393,   # Tarantula Broodfather
    6397,   # Sven Packmaster
}

RARITY_MAP = {
    "common": "c",
    "uncommon": "u",
    "rare": "r",
    "epic": "e",
    "legendary": "l",
    "rng": "rng",
    "rngesus": "rng",
}


def get_mobs():
    """Return {pageid: title} for all mob pages in Category:Mobs."""
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:Mobs",
        "cmlimit": 500,
        "cmtype": "page|subcat",
        "format": "json",
    }

    data = requests.get(
        BASE_URL, params=params, headers=HEADERS
    ).json()

    mobs = {}

    def search(members):
        for member in members:
            title = member["title"]
            pageid = member["pageid"]

            if (
                title == "Category:Non-player characters"
                or pageid in mobs
            ):
                continue

            if title.startswith("Category:"):
                sub_params = {
                    "action": "query",
                    "list": "categorymembers",
                    "cmtitle": title,
                    "cmlimit": 500,
                    "cmtype": "page|subcat",
                    "format": "json",
                }

                sub_data = requests.get(
                    BASE_URL,
                    params=sub_params,
                    headers=HEADERS,
                ).json()

                time.sleep(0.3)
                search(sub_data["query"]["categorymembers"])

            elif member["ns"] == 0:
                mobs[pageid] = title

    search(data["query"]["categorymembers"])
    return mobs


def find_templates(text, template_name):
    """
    Find complete {{template_name ...}} blocks.

    Unlike the old version, this understands nested templates and
    therefore won't stop at a }} belonging to an inner template.
    """
    blocks = []
    needle = "{{" + template_name
    start = 0

    while True:
        begin = text.find(needle, start)
        if begin == -1:
            break

        depth = 0
        i = begin

        while i < len(text) - 1:
            pair = text[i:i + 2]

            if pair == "{{":
                depth += 1
                i += 2
                continue

            if pair == "}}":
                depth -= 1
                i += 2

                if depth == 0:
                    blocks.append(text[begin + 2:i - 2])
                    start = i
                    break

                continue

            i += 1
        else:
            # Incomplete template. Ignore it rather than producing
            # corrupted data.
            break

    return blocks


def split_template_fields(block):
    """
    Split a template into parameters without splitting on | characters
    inside nested templates or wikilinks.
    """
    fields = []
    current = []

    template_depth = 0
    link_depth = 0

    i = 0

    while i < len(block):
        pair = block[i:i + 2]

        if pair == "{{":
            template_depth += 1
            current.append(pair)
            i += 2
            continue

        if pair == "}}" and template_depth:
            template_depth -= 1
            current.append(pair)
            i += 2
            continue

        if pair == "[[":
            link_depth += 1
            current.append(pair)
            i += 2
            continue

        if pair == "]]" and link_depth:
            link_depth -= 1
            current.append(pair)
            i += 2
            continue

        if (
            block[i] == "|"
            and template_depth == 0
            and link_depth == 0
        ):
            fields.append("".join(current))
            current = []
        else:
            current.append(block[i])

        i += 1

    fields.append("".join(current))
    return fields


def clean_text(value):
    """Convert wiki/HTML formatting into plain text."""
    if value is None:
        return None

    # References
    value = re.sub(
        r"<ref\b[^>]*>.*?</ref\s*>",
        "",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    value = re.sub(
        r"<ref\b[^>]*/>",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # HTML tags. Keep their contents.
    value = re.sub(r"<[^>]+>", "", value)

    # Wikilinks:
    # [[Page|Display]] -> Display
    # [[Page#Section]] -> Section
    def clean_link(match):
        link = match.group(1)

        if "|" in link:
            return link.split("|")[-1]

        if "#" in link:
            return link.split("#")[-1]

        return link

    value = re.sub(r"\[\[([^\]]+)\]\]", clean_link, value)

    # Common simple templates.
    value = re.sub(
        r"\{\{\s*(?:InfoNeeded|ConfirmationNeeded|bc)\s*\}\}",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # {{g|value}} -> value
    value = re.sub(
        r"\{\{\s*g\s*\|\s*([^{}]*)\}\}",
        r"\1",
        value,
        flags=re.IGNORECASE,
    )

    # {{Overline|value}} -> value
    value = re.sub(
        r"\{\{\s*Overline\s*\|\s*([^{}]*)\}\}",
        r"\1",
        value,
        flags=re.IGNORECASE,
    )

    # Remove unresolved Odds templates rather than leaving wiki markup.
    value = re.sub(
        r"\{\{\s*Odds\b[^{}]*\}\}",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # Formatting used by the wiki for rarity/item colours:
    # $R$ Item -> Item
    # $e$ Item -> Item
    value = re.sub(r"\$[A-Za-z]+\$\s*", "", value)

    # HTML entities
    value = html.unescape(value)

    # Normalize whitespace
    value = re.sub(r"\s+", " ", value).strip()

    return value or None


def clean_item_name(name):
    """Clean an item name while preserving useful text."""
    name = clean_text(name)

    if not name:
        return None

    # Enchant notation:
    # Enchanted Book &Magnet VI& -> Enchanted Book (Magnet VI)
    enchant = re.search(r"&([^&]+)&", name)

    if enchant:
        base = name[:enchant.start()].strip()
        enchantment = enchant.group(1).strip()
        return f"{base} ({enchantment})"

    # Remove wiki separators that sometimes occur after the useful value.
    name = name.split("!", 1)[0]
    name = name.split(";", 1)[0]

    return name.strip("[] ").strip() or None


def clean_rarity(value):
    value = clean_text(value)

    if not value:
        return None

    return RARITY_MAP.get(value.lower(), value)


def make_drop(item, count, rarity, chance):
    return {
        "item": clean_item_name(item),
        "count": clean_text(count),
        "rarity": clean_rarity(rarity),
        "chance": clean_text(chance),
    }


def make_table(coins=None, exp=None, loot_share=False, drops=None):
    return {
        "coins": clean_text(coins),
        "exp": clean_text(exp),
        "loot_share": loot_share,
        "drops": drops or [],
    }


def make_mob(name, drops):
    return {
        "name": name,
        "drops": drops,
    }


def drop_table(wikitext, name):
    """
    Parse normal {{Mob Drops Table}} templates.

    Returns a list containing one normal-format mob entry.
    """
    tables = []

    for block in find_templates(wikitext, "Mob Drops Table"):
        fields = {}

        for field in split_template_fields(block):
            if "=" not in field:
                continue

            key, value = field.split("=", 1)
            fields[key.strip()] = value.strip()

        drops = []

        for key in fields:
            match = re.fullmatch(r"drop(\d*)", key)
            if not match:
                continue

            suffix = match.group(1)

            item = fields.get(f"drop{suffix}")
            if not item:
                continue

            item = clean_item_name(item)
            if not item:
                continue

            drops.append(
                make_drop(
                    item,
                    fields.get(f"count{suffix}"),
                    fields.get(f"rarity{suffix}"),
                    fields.get(f"chance{suffix}"),
                )
            )

        table = make_table(
            coins=fields.get("coins") or fields.get("c"),
            exp=fields.get("exp"),
            loot_share=(
                clean_text(fields.get("loot_share")) or ""
            ).lower() == "true",
            drops=drops,
        )

        # Don't keep completely empty tables.
        if drops:
            tables.append(table)

    return [make_mob(name, tables)] if tables else []


def slayer_drop_tables(wikitext, name):
    """
    Parse a Slayer boss's tiered drop table.

    Each tier becomes a separate normal-format mob entry:
        Boss I
        Boss II
        Boss III
        ...
    """
    section_match = re.search(
        r"==\s*Drops\s*==(.*?)(?=\n==[^=]|\Z)",
        wikitext,
        re.DOTALL | re.IGNORECASE,
    )

    if not section_match:
        return []

    section = section_match.group(1)

    table_match = re.search(
        r"\{\|.*?\n\|\}",
        section,
        re.DOTALL,
    )

    if not table_match:
        return []

    table_text = table_match.group(0)

    # Determine how many tiers are represented by the header.
    header_end = table_text.find("\n|-\n|{{Slot")

    if header_end == -1:
        header_text = table_text
    else:
        header_text = table_text[:header_end]

    tier_count = len(
        re.findall(r"\{\{\s*SlayerTier\s*\|", header_text)
    ) // 2

    if not tier_count:
        tier_count = 5

    tier_labels = ["I", "II", "III", "IV", "V"][:tier_count]

    # Parse table rows while respecting colspan.
    rows = []
    current_row = []

    for line in table_text.splitlines():
        line = line.strip()

        if line.startswith("|-"):
            if current_row:
                rows.append(current_row)
                current_row = []
            continue

        if (
            not line.startswith("|")
            or line.startswith("|}")
            or line.startswith("|+")
        ):
            continue

        cell = line[1:].strip()
        colspan = 1

        match = re.match(
            r'colspan="(\d+)"\s*\|(.*)',
            cell,
        )

        if match:
            colspan = int(match.group(1))
            cell = match.group(2).strip()

        elif "style=" in cell and "|" in cell:
            cell = cell.split("|", 1)[1].strip()

        current_row.append((cell, colspan))

    if current_row:
        rows.append(current_row)

    results = [
        {
            "name": f"{name} {tier}",
            "drops": [],
        }
        for tier in tier_labels
    ]

    expected_len = 3 + tier_count + 1 + tier_count

    for row in rows:
        flat = []

        for value, span in row:
            flat.extend([value] * span)

        if len(flat) < expected_len:
            continue

        # The second column contains the actual drop item.
        item_match = re.search(
            r"\{\{\s*ID\s*\|\s*([^}|!&]+)",
            flat[1],
        )

        if not item_match:
            continue

        item = clean_item_name(item_match.group(1))

        if not item:
            continue

        # Existing Slayer table layout:
        # icon, item, level, amounts..., odds separator, chances...
        amounts = flat[3:3 + tier_count]
        chances_start = 4 + tier_count
        chances = flat[
            chances_start:chances_start + tier_count
        ]

        for i, tier in enumerate(tier_labels):
            amount = (
                clean_text(amounts[i])
                if i < len(amounts)
                else None
            )

            chance = (
                clean_text(chances[i])
                if i < len(chances)
                else None
            )

            # Ignore empty / wiki-only values.
            if not amount and not chance:
                continue

            results[i]["drops"].append(
                make_table(
                    drops=[
                        make_drop(
                            item,
                            amount,
                            None,
                            chance,
                        )
                    ]
                )
            )

    # A Slayer tier should have one normal drop table containing
    # all of its drops, not one table per item.
    for result in results:
        tables = result["drops"]

        if not tables:
            continue

        combined_drops = []

        for table in tables:
            combined_drops.extend(table["drops"])

        result["drops"] = [
            make_table(drops=combined_drops)
        ]

    return [
        result
        for result in results
        if result["drops"] and result["drops"][0]["drops"]
    ]


def main():
    mobs = get_mobs()

    # Always start from an empty dataset.
    # This prevents duplicate entries when the scraper is run again.
    file_data = []

    for index, (pageid, name) in enumerate(mobs.items(), 1):
        params = {
            "action": "parse",
            "pageid": pageid,
            "prop": "wikitext",
            "format": "json",
        }

        data = requests.get(
            BASE_URL,
            params=params,
            headers=HEADERS,
        ).json()

        time.sleep(0.1)

        wikitext = data["parse"]["wikitext"]["*"]

        if pageid in SLAYER_BOSS_IDS:
            entries = slayer_drop_tables(wikitext, name)
        else:
            entries = drop_table(wikitext, name)

        file_data.extend(entries)

        print(
            f"[{index}/{len(mobs)}] {name}: "
            f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"
        )

    # Final safety check against duplicate names.
    unique = {}
    for entry in file_data:
        unique[entry["name"]] = entry

    file_data = list(unique.values())

    with open("loot_table.json", "w", encoding="utf-8") as f:
        json.dump(
            file_data,
            f,
            indent=4,
            ensure_ascii=False,
        )

    print()
    print(f"Found {len(mobs)} mob pages.")
    print(f"Wrote {len(file_data)} entries to loot_table.json")
    print("Done.")


if __name__ == "__main__":
    main()