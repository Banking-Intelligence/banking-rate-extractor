"""Validate the audit registry that explains source-to-Record-ID permissions."""
import argparse
import collections
import json
from pathlib import Path

from extractor import CONFIG

SCHEMA_VERSION = 1
REGISTRY = Path(__file__).with_name("mapped_record_registry.json")
REQUIRED = ["source_id", "record_id", "country", "bank_name", "type", "product_tenor", "currency", "mapping_basis"]


class RegistryError(ValueError):
    pass


def load_registry(path=REGISTRY):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise RegistryError("Unsupported registry schema_version")
    mappings = payload.get("mappings")
    if not isinstance(mappings, list):
        raise RegistryError("Registry must contain a mappings array")
    return mappings


def source_rule_pairs(sources=None):
    sources = sources if sources is not None else json.loads(CONFIG.read_text(encoding="utf-8"))
    pairs = {}
    for source in sources:
        if source.get("group") != "bank" or source.get("adapter") != "rules":
            continue
        for rule in source.get("rules", []):
            record_id = rule.get("record_id")
            if record_id:
                pairs[(source["id"], record_id)] = source
    return pairs


def validate_registry(mappings, sources=None):
    pairs = source_rule_pairs(sources)
    seen = set()
    diagnostics = {"mappings": 0, "countries": {}, "sources": {}}
    for index, mapping in enumerate(mappings, start=1):
        missing = [key for key in REQUIRED if not str(mapping.get(key, "")).strip()]
        if missing:
            raise RegistryError(f"Mapping {index} is missing required fields: {', '.join(missing)}")
        pair = (mapping["source_id"], mapping["record_id"])
        if pair in seen:
            raise RegistryError(f"Duplicate source/Record-ID pair: {pair[0]} / {pair[1]}")
        seen.add(pair)
        source = pairs.get(pair)
        if not source:
            raise RegistryError(f"Registry pair is not present in rules sources: {pair[0]} / {pair[1]}")
        if mapping["country"] not in {source.get("country"), source.get("target")}:
            raise RegistryError(f"Country mismatch for {pair[0]} / {pair[1]}")
        if mapping["mapping_basis"] != "live_workbook_exact_match":
            raise RegistryError(f"Unsupported mapping basis for {pair[0]} / {pair[1]}")
        currency = str(mapping.get("currency", "")).upper()
        if currency and currency != "N/A" and not currency.isalpha():
            raise RegistryError(f"Invalid currency for {pair[0]} / {pair[1]}")
        diagnostics["mappings"] += 1
        diagnostics["countries"][mapping["country"]] = diagnostics["countries"].get(mapping["country"], 0) + 1
        diagnostics["sources"][mapping["source_id"]] = diagnostics["sources"].get(mapping["source_id"], 0) + 1
    return diagnostics


def main():
    parser = argparse.ArgumentParser(description="Validate mapped_record_registry.json against sources.json.")
    parser.add_argument("registry", nargs="?", default=str(REGISTRY))
    args = parser.parse_args()
    diagnostics = validate_registry(load_registry(args.registry))
    print(json.dumps(diagnostics, sort_keys=True))


if __name__ == "__main__":
    main()
