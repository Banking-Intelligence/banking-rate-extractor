"""Audit commercial-bank sources before converting review entries to rules.

The audit is intentionally conservative. It can inspect official publications and rank
sources by apparent parser feasibility, but it does not create Record IDs and does not
modify sources.json. Existing spreadsheet Record IDs must come from the workbook or
from already-reviewed source rules.
"""
import argparse
import collections
import datetime as dt
import json
import re
from pathlib import Path

from extractor import CONFIG, ReviewRequired, fetch_publication, markdown_tables, tables, text_content
from import_record_manifest import allowed_countries, load_manifest, match_sources, validate_manifest_rows

REPORT_DIR = Path(__file__).with_name("reports")
REFERENCE_LINKED = re.compile(r"\b(?:prime|base\s+rate|repo|tbill|t-bill|treasury|benchmark|reference)\b\s*(?:[+\-]|plus|minus)", re.I)
PERSONALISED = re.compile(r"\b(?:negotiable|subject to|depending on|depends on|as per arrangement|upon request|available on request|contact branch|assessment|personalised|personalized)\b", re.I)
RATE_LIKE = re.compile(r"(?<!\d)(?:\d{1,2}(?:[.,]\d{1,3})?\s*%|\d{1,2}(?:[.,]\d{1,3})?\s*(?:-|to|à)\s*\d{1,2}(?:[.,]\d{1,3})?\s*%)", re.I)
PRODUCT_WORDS = re.compile(r"\b(?:deposit|savings?|loan|mortgage|fixed|term|call|notice|epargne|compte|taux|interest|rate)\b", re.I)
TENOR_WORDS = re.compile(r"\b(?:month|months|year|years|jours?|days?|tenor|term|maturity|mois|ans?)\b", re.I)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_kind(source):
    sid = source.get("id", "")
    if sid.startswith("src-"):
        return "product_publication"
    if sid.startswith("bank-"):
        return "directory_record"
    return "other"


def source_has_existing_record_ids(source):
    return [rule.get("record_id") for rule in source.get("rules", []) if rule.get("record_id")]


def classify_rate_meaning(text):
    snippets = [clean(s) for s in re.split(r"[\n\r]+|(?<=[.;])\\s+", text) if RATE_LIKE.search(s)]
    sample = " ".join(snippets[:20]) if snippets else text
    if REFERENCE_LINKED.search(sample):
        return "reference_linked"
    if snippets and all(PERSONALISED.search(s) for s in snippets):
        return "personalised_or_negotiated"
    if re.search(r"\d+(?:[.,]\d+)?\s*%?\s*(?:-|to|à)\s*\d+(?:[.,]\d+)?\s*%", sample, re.I):
        return "range"
    if RATE_LIKE.search(sample):
        return "single_numeric"
    if PERSONALISED.search(sample):
        return "personalised_or_negotiated"
    return "unavailable"


def inspect_content(raw):
    text = text_content(raw)
    html_tables = [] if raw.startswith(b"%PDF") else tables(raw)
    md_tables = [] if raw.startswith(b"%PDF") else markdown_tables(raw)
    all_tables = html_tables + md_tables
    table_summaries = []
    for table in all_tables[:12]:
        if not table:
            continue
        header = table[0]
        rows = table[1:6]
        joined = " ".join(" | ".join(row) for row in table[:8])
        if RATE_LIKE.search(joined) or PRODUCT_WORDS.search(joined):
            table_summaries.append({"header": header, "sample_rows": rows})
    product_lines = []
    rate_lines = []
    for line in re.split(r"[\n\r]+|(?<=[.;])\s+", text):
        line = clean(line)
        if len(line) < 8:
            continue
        if RATE_LIKE.search(line):
            rate_lines.append(line[:300])
        if PRODUCT_WORDS.search(line) and (RATE_LIKE.search(line) or TENOR_WORDS.search(line)):
            product_lines.append(line[:300])
        if len(product_lines) >= 12 and len(rate_lines) >= 12:
            break
    return {
        "contains_numeric_interest_rates": bool(RATE_LIKE.search(text)),
        "tables_structurally_identifiable": bool(table_summaries),
        "product_or_tenor_labels_explicit": bool(TENOR_WORDS.search(text) or table_summaries),
        "rate_meaning": classify_rate_meaning("\n".join(rate_lines) or text),
        "table_summaries": table_summaries[:5],
        "product_lines": product_lines[:10],
        "rate_lines": rate_lines[:10],
    }


def tier_for(source, content=None, retrieval_status="not_checked"):
    if source_kind(source) != "product_publication":
        return "Directory", "Directory/homepage record; not a product-rate publication placeholder"
    if source.get("adapter") == "rules":
        return "Mapped", "Already configured with deterministic rules"
    if retrieval_status != "ok" or not content:
        return "Tier C", "Publication was not retrieved successfully during audit"
    if content["rate_meaning"] in ("reference_linked", "personalised_or_negotiated", "unavailable"):
        return "Tier C", "Rate wording is not a simple numeric published value or range"
    if not content["contains_numeric_interest_rates"]:
        return "Tier C", "No numeric interest rates detected"
    if content["tables_structurally_identifiable"] and content["product_or_tenor_labels_explicit"]:
        return "Tier A", "Official publication has identifiable table structure and explicit labels"
    if content["contains_numeric_interest_rates"] and content["product_or_tenor_labels_explicit"]:
        return "Tier B", "Numeric rates and labels are visible, but parser may need regex or normalization"
    return "Tier C", "Numeric content is not structurally tied to clear product labels"


def audit_source(source, fetch_review_publications=True):
    """Inspect one bank source and decide how safe it looks for automation."""
    item = {
        "source_id": source.get("id"),
        "country": source.get("country"),
        "bank_name": source.get("name"),
        "official_url": source.get("url"),
        "current_adapter": source.get("adapter"),
        "source_kind": source_kind(source),
        "existing_record_ids": source_has_existing_record_ids(source),
        "retrieval_status": "not_checked",
        "http_status": "not_recorded",
        "retrieval_method": "not_checked",
        "contains_numeric_interest_rates": False,
        "tables_structurally_identifiable": False,
        "product_or_tenor_labels_explicit": False,
        "rate_meaning": "unknown",
        "current_spreadsheet_record_ids_exist": False,
        "automation_appears_deterministic": False,
        "tier": "Unclassified",
        "reason": "",
        "visible_product_rows": [],
        "table_headers": [],
        "expected_record_count": 0,
    }
    should_fetch = fetch_review_publications and item["source_kind"] == "product_publication"
    if should_fetch:
        try:
            current, raw, final_url, meta = fetch_publication(source)
            content = inspect_content(raw)
            item.update(content)
            item["retrieval_status"] = "ok"
            item["http_status"] = "ok"
            item["retrieval_method"] = meta.get("retrieval_method", "direct_http")
            item["official_url"] = final_url
            item["visible_product_rows"] = content["product_lines"]
            item["table_headers"] = [t.get("header") for t in content["table_summaries"]]
        except ReviewRequired as exc:
            item["retrieval_status"] = "review"
            item["reason"] = str(exc)[:300]
            meta = getattr(exc, "metadata", {}) or {}
            item["retrieval_method"] = meta.get("retrieval_method", "not_available")
            item["http_status"] = meta.get("render_status", "not_recorded")
        except Exception as exc:
            item["retrieval_status"] = "failed"
            item["reason"] = str(exc)[:300]
    tier, reason = tier_for(source, item if item["retrieval_status"] == "ok" else None, item["retrieval_status"])
    item["tier"] = tier
    if not item["reason"]:
        item["reason"] = reason
    item["current_spreadsheet_record_ids_exist"] = bool(item["existing_record_ids"])
    item["expected_record_count"] = len(item["existing_record_ids"])
    item["automation_appears_deterministic"] = item["tier"] in ("Tier A", "Tier B") and bool(item["existing_record_ids"])
    return item


def rank_candidates(items, limit=10):
    """Prefer the clearest source candidates while spreading coverage by country."""
    tier_score = {"Tier A": 0, "Tier B": 1}
    candidates = [i for i in items if i["tier"] in tier_score and i["source_kind"] == "product_publication"]
    candidates.sort(key=lambda i: (tier_score[i["tier"]], i["country"] or "", i["bank_name"] or ""))
    selected = []
    country_counts = collections.Counter()
    for item in candidates:
        if len(selected) >= limit:
            break
        if country_counts[item["country"]] >= 2 and len({c for c in country_counts if country_counts[c]}) < min(limit, len(set(i["country"] for i in candidates))):
            continue
        selected.append(item)
        country_counts[item["country"]] += 1
    for item in candidates:
        if len(selected) >= limit:
            break
        if item not in selected:
            selected.append(item)
    return selected


def apply_manifest_matches(items, validated_manifest, sources):
    if not validated_manifest:
        return {}
    matches = {m["source_id"]: m for m in match_sources(validated_manifest, sources)}
    for item in items:
        match = matches.get(item["source_id"])
        if match:
            item["manifest_match_status"] = match["match_status"]
            item["manifest_record_ids"] = match["record_ids"]
            item["manifest_matched_rows"] = match["matched_rows"]
    return matches


def write_reports(items, selected, manifest_matches=None):
    REPORT_DIR.mkdir(exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    counts = collections.Counter(i["tier"] for i in items)
    adapters = collections.Counter(i["current_adapter"] for i in items)
    payload = {"checked_at": timestamp, "counts_by_tier": dict(counts), "counts_by_adapter": dict(adapters), "match_counts": dict(collections.Counter((manifest_matches or {}).get(i["source_id"], {}).get("match_status", "not_checked") for i in items if i["source_kind"] == "product_publication" and i["current_adapter"] == "review")), "selected_candidates": selected, "sources": items}
    (REPORT_DIR / "phase5_bank_source_audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Phase 5 Commercial-Bank Source Audit",
        "",
        f"Checked at: {timestamp}",
        "",
        "## Summary",
        "",
        f"- Enabled bank-group sources audited: {len(items)}",
        f"- Adapter counts: {dict(adapters)}",
        f"- Tier counts: {dict(counts)}",
        "- FNB Namibia Access Immediately and Access After a Fixed Period remain review by policy.",
        "- Candidate conversion is blocked unless existing workbook Record IDs are available for the exact product rows.",
        "",
        "## Top candidate publications",
        "",
    ]
    if not selected:
        lines.append("No Tier A/Tier B product publications with existing Record IDs were available for conversion in this repository snapshot.")
    else:
        lines.append("| Tier | Country | Bank | Source ID | Retrieval | Rate meaning | Existing IDs | Manifest match | Manifest Record IDs | Deterministic reason |")
        lines.append("|---|---|---|---|---|---|---:|---|---:|---|")
        for item in selected:
            lines.append("| {tier} | {country} | {bank_name} | `{source_id}` | {retrieval_method} | {rate_meaning} | {ids} | {match} | {manifest_ids} | {reason} |".format(
                ids=len(item["existing_record_ids"]), match=item.get("manifest_match_status", "not_checked"),
                manifest_ids=len(item.get("manifest_record_ids", [])), **{k: str(v).replace('|', '/') for k, v in item.items()}
            ))
    lines.extend(["", "## Product-rate review publications", "", "| Tier | Country | Bank | Source ID | Retrieval | Record IDs available | Reason |", "|---|---|---|---|---|---:|---|"])
    for item in [i for i in items if i["source_kind"] == "product_publication" and i["current_adapter"] == "review"]:
        lines.append("| {tier} | {country} | {bank_name} | `{source_id}` | {retrieval_status}/{retrieval_method} | {ids} | {reason} |".format(
            ids=len(item["existing_record_ids"]), **{k: str(v).replace('|', '/') for k, v in item.items()}
        ))
    (REPORT_DIR / "phase5_candidate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Audit commercial-bank source feasibility without changing mappings.")
    parser.add_argument("--no-fetch", action="store_true", help="Skip live retrieval and only classify source metadata.")
    parser.add_argument("--limit", type=int, default=10, help="Number of candidate rows to highlight.")
    parser.add_argument("--manifest", help="Optional CSV/JSON export from Record_ID_Manifest for source-to-row matching.")
    args = parser.parse_args()
    sources = json.loads(CONFIG.read_text(encoding="utf-8"))
    bank_sources = [s for s in sources if s.get("group") == "bank" and s.get("enabled", True)]
    items = [audit_source(s, fetch_review_publications=not args.no_fetch) for s in bank_sources]
    validated_manifest = None
    manifest_matches = None
    if args.manifest:
        validated_manifest = validate_manifest_rows(load_manifest(args.manifest), countries=allowed_countries(sources))
        manifest_matches = apply_manifest_matches(items, validated_manifest, sources)
    selected = rank_candidates(items, args.limit)
    write_reports(items, selected, manifest_matches)
    print(json.dumps({
        "audited": len(items),
        "tier_counts": dict(collections.Counter(i["tier"] for i in items)),
        "adapter_counts": dict(collections.Counter(i["current_adapter"] for i in items)),
        "selected": [i["source_id"] for i in selected],
        "report": str(REPORT_DIR / "phase5_candidate_report.md"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()



