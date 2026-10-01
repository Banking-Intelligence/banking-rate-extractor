"""Validate Record-ID manifests exported from the Banking Intelligence workbook.

This tool never creates Record IDs. It only validates an export from the workbook and
uses it to diagnose which existing rows a source might be allowed to update later.
"""
import argparse
import collections
import csv
import json
import re
import unicodedata
from pathlib import Path

from extractor import CONFIG

SCHEMA_VERSION = 1
REQUIRED_COLUMNS = ["Record ID", "Country", "Sheet", "Bank Name", "Type", "Product / Tenor", "Currency"]
OPTIONAL_COLUMNS = ["Website Link", "Data Source Link", "Manual Override"]
SANITIZED_COLUMNS = ["Record ID", "Country", "Sheet", "Bank Name", "Type", "Product / Tenor", "Currency"]
SENSITIVE_COLUMNS = re.compile(r"token|secret|credential|password|staff|email|script property|spreadsheet id", re.I)
DEFAULT_OUTPUT = Path(__file__).with_name("reports") / "record_manifest_match_report.json"


class ManifestError(ValueError):
    pass


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value):
    text = unicodedata.normalize("NFKD", clean(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = re.sub(r"\b(limited|ltd|plc|bank|banque|corporation|corp|group|groupe|sa|llc|the)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_currency(value):
    return clean(value).upper()


def allowed_countries(sources=None):
    data = sources if sources is not None else json.loads(CONFIG.read_text(encoding="utf-8"))
    return {s.get("target") for s in data if s.get("group") == "bank" and s.get("target")} | {s.get("country") for s in data if s.get("group") == "bank" and s.get("country")}


def load_manifest(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        if payload.get("schema_version") not in (None, SCHEMA_VERSION):
            raise ManifestError("Unsupported manifest schema_version")
        records = payload.get("records")
        if not isinstance(records, list):
            raise ManifestError("JSON manifest must contain a records array")
        return records
    if isinstance(payload, list):
        return payload
    raise ManifestError("Manifest must be a CSV, a JSON records array, or a JSON object with records")


def validate_manifest_rows(rows, countries=None, allow_sensitive=False):
    """Validate exported workbook row identities before using them for matching."""
    if not rows:
        raise ManifestError("Manifest is empty")
    columns = set().union(*(row.keys() for row in rows))
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise ManifestError("Missing required columns: " + ", ".join(missing))
    if not allow_sensitive:
        sensitive = sorted(c for c in columns if SENSITIVE_COLUMNS.search(c))
        if sensitive:
            raise ManifestError("Manifest contains sensitive-looking columns: " + ", ".join(sensitive))
    countries = set(countries or [])
    seen = {}
    missing_ids = []
    cleaned = []
    duplicate_logical = collections.defaultdict(list)
    for idx, row in enumerate(rows, start=2):
        record_id = clean(row.get("Record ID"))
        if not record_id:
            missing_ids.append(idx)
            continue
        if record_id in seen:
            raise ManifestError(f"Duplicate Record ID {record_id!r} at rows {seen[record_id]} and {idx}")
        seen[record_id] = idx
        country = clean(row.get("Country"))
        sheet = clean(row.get("Sheet")) or country
        if countries and (country not in countries or sheet not in countries):
            raise ManifestError(f"Invalid country/sheet for Record ID {record_id!r}: {country!r}/{sheet!r}")
        currency = normalize_currency(row.get("Currency"))
        if not re.fullmatch(r"[A-Z]{3}|N/A|", currency):
            raise ManifestError(f"Invalid currency for Record ID {record_id!r}: {currency!r}")
        entry = {col: clean(row.get(col)) for col in REQUIRED_COLUMNS + OPTIONAL_COLUMNS if col in row or col in OPTIONAL_COLUMNS}
        entry["Record ID"] = record_id
        entry["Country"] = country
        entry["Sheet"] = sheet
        entry["Currency"] = currency or "N/A"
        cleaned.append(entry)
        logical = (normalize_text(country), normalize_text(row.get("Bank Name")), normalize_text(row.get("Type")), normalize_text(row.get("Product / Tenor")), entry["Currency"])
        duplicate_logical[logical].append(record_id)
    if missing_ids:
        raise ManifestError("Rows with missing Record ID: " + ", ".join(map(str, missing_ids[:20])))
    diagnostics = {
        "rows": len(cleaned),
        "unique_record_ids": len(seen),
        "counts_by_country": dict(collections.Counter(r["Country"] for r in cleaned)),
        "counts_by_bank": dict(collections.Counter(r["Bank Name"] for r in cleaned)),
        "duplicate_logical_products": [ids for ids in duplicate_logical.values() if len(ids) > 1],
    }
    return {"schema_version": SCHEMA_VERSION, "records": cleaned, "diagnostics": diagnostics}


def sanitized_manifest(validated):
    """Keep only safe identity fields for repo-side matching."""
    return {"schema_version": SCHEMA_VERSION, "records": [{k: r.get(k, "") for k in SANITIZED_COLUMNS} for r in validated["records"]]}


def bank_tokens(value):
    return set(normalize_text(value).split())


def bank_match_score(source_name, workbook_name):
    a, b = bank_tokens(source_name), bank_tokens(workbook_name)
    if not a or not b:
        return 0.0
    if a == b or normalize_text(source_name) == normalize_text(workbook_name):
        return 1.0
    overlap = len(a & b) / max(len(a), len(b))
    return overlap


def row_matches_expected_fields(row, source):
    expected_currency = normalize_currency(source.get("match_currency", ""))
    if expected_currency and expected_currency != "N/A" and row.get("Currency") != expected_currency:
        return False
    expected_type = normalize_text(source.get("match_type", ""))
    if expected_type and expected_type not in normalize_text(row.get("Type", "")):
        return False
    expected_product = normalize_text(source.get("match_product", "") or source.get("match_tenor", ""))
    if expected_product and expected_product not in normalize_text(row.get("Product / Tenor", "")):
        return False
    return True


def classify_source_match(source, records):
    country_records = [r for r in records if r["Country"] == source.get("target") or r["Country"] == source.get("country")]
    country_records = [r for r in country_records if row_matches_expected_fields(r, source)]
    scored = [(bank_match_score(source.get("name", ""), r.get("Bank Name", "")), r) for r in country_records]
    strong = [r for score, r in scored if score >= 0.8]
    weak = [r for score, r in scored if 0.45 <= score < 0.8]
    if not strong and not weak:
        return "none", []
    bank_groups = collections.defaultdict(list)
    for r in strong:
        bank_groups[normalize_text(r["Bank Name"])].append(r)
    if len(bank_groups) == 1:
        rows = next(iter(bank_groups.values()))
        currencies = {r["Currency"] for r in rows if r["Currency"] and r["Currency"] != "N/A"}
        products = {normalize_text(r["Type"] + " " + r["Product / Tenor"]) for r in rows}
        if len(rows) == 1 or (currencies and products):
            return "exact", rows
        return "candidate", rows
    if strong:
        return "ambiguous", strong
    return ("candidate" if len({normalize_text(r["Bank Name"]) for r in weak}) == 1 else "ambiguous"), weak


def match_sources(validated, sources=None):
    """Classify each review publication as exact, candidate, ambiguous, or none."""
    sources = sources if sources is not None else json.loads(CONFIG.read_text(encoding="utf-8"))
    records = validated["records"]
    rows = []
    for source in sources:
        if source.get("group") != "bank" or source.get("enabled") is False:
            continue
        if source.get("adapter") != "review" or not source.get("id", "").startswith("src-"):
            continue
        status, matches = classify_source_match(source, records)
        rows.append({
            "source_id": source["id"],
            "country": source.get("country"),
            "bank_name": source.get("name"),
            "url": source.get("url"),
            "match_status": status,
            "record_ids": [r["Record ID"] for r in matches],
            "matched_rows": [{k: r.get(k, "") for k in SANITIZED_COLUMNS} for r in matches[:50]],
        })
    return rows


def write_reports(validated, matches, output=DEFAULT_OUTPUT):
    output = Path(output)
    output.parent.mkdir(exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "manifest_diagnostics": validated["diagnostics"],
        "match_counts": dict(collections.Counter(m["match_status"] for m in matches)),
        "matches": matches,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description="Validate a workbook Record-ID manifest and match review sources to existing rows.")
    parser.add_argument("manifest", help="CSV or JSON export from Record_ID_Manifest")
    parser.add_argument("--write-sanitized", help="Optional path for identity-only sanitized manifest JSON")
    parser.add_argument("--write-report", default=str(DEFAULT_OUTPUT), help="Path for source matching diagnostics")
    parser.add_argument("--allow-sensitive-columns", action="store_true", help="Permit sensitive-looking columns for local validation only")
    args = parser.parse_args()
    sources = json.loads(CONFIG.read_text(encoding="utf-8"))
    validated = validate_manifest_rows(load_manifest(args.manifest), countries=allowed_countries(sources), allow_sensitive=args.allow_sensitive_columns)
    if args.write_sanitized:
        Path(args.write_sanitized).write_text(json.dumps(sanitized_manifest(validated), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    matches = match_sources(validated, sources)
    report = write_reports(validated, matches, args.write_report)
    print(json.dumps({
        "rows": validated["diagnostics"]["rows"],
        "unique_record_ids": validated["diagnostics"]["unique_record_ids"],
        "match_counts": dict(collections.Counter(m["match_status"] for m in matches)),
        "report": str(report),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
