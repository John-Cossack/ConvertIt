"""Shared conversion registry used by the UI, CLI, and generated Explorer tables."""
import json
from pathlib import Path
import sys

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
REGISTRY = json.loads((ROOT / "routes.json").read_text(encoding="utf-8"))
OUTPUTS = {row["id"]: row for row in REGISTRY["outputs"]}
INPUTS = {ext: row for row in REGISTRY["inputs"] for ext in row["extensions"]}
ALIASES = {"jpeg":"jpg", "jpe":"jpg", "jfif":"jpg", "tif":"tiff"}


def extension(target):
    return OUTPUTS[target]["extension"]


def input_extension(path):
    name = Path(path).name.lower()
    return next((ext for ext in sorted(INPUTS, key=len, reverse=True) if name.endswith('.'+ext)), '')


def available(source_format, kind="image"):
    rule = next((row for row in REGISTRY["inputs"] if row["format"] == source_format and row["kind"] == kind), None)
    if not rule:
        return []
    return [row for row in REGISTRY["outputs"]
            if (row["id"] in rule["allow"] if "allow" in rule else row["kind"] == rule["kind"])
            and row["id"] not in rule.get("exclude", [])]


def selection_groups(files):
    common = set(OUTPUTS)
    for path in files:
        rule = INPUTS.get(input_extension(path))
        if not rule:
            return []
        common &= {row["id"] for row in available(rule["format"], rule["kind"])}
    return [(group["label"], [row for row in REGISTRY["outputs"] if row["group"] == group["id"] and row["id"] in common])
            for group in REGISTRY["groups"] if any(row["group"] == group["id"] and row["id"] in common for row in REGISTRY["outputs"])]
