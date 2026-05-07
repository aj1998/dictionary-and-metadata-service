import json

with open("parser_configs/_manual_configs/shastra.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for obj in data:
    if "format" in obj and "पृष्ठ" in obj["format"]:
        obj["type"] = "teeka"

with open("parser_configs/_manual_configs/shastra_updated.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)