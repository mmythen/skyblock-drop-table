import json

with open("loot_table.json", "r") as f:
    data = json.load(f)

# keep only entries that have at least one non-empty drop table
filtered = [
    entry for entry in data
    if entry["drops"] and any(
        table.get("drops") if isinstance(table, dict) and "drops" in table else True
        for table in entry["drops"]
    )
]

with open("loot_table.json", "w") as f:
    json.dump(filtered, f, indent=4)

print(f"Kept {len(filtered)} of {len(data)} entries")