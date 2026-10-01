"""Run configured public-source extractions and publish versioned JSON results."""
import argparse
import datetime as dt
import json
from pathlib import Path

from extractor import CONFIG, ReviewRequired, extract

SCHEMA_VERSION = 1
RESULTS_DIR = Path(__file__).with_name("results")


def result_path(source_id, results_dir=RESULTS_DIR):
    if not source_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in source_id):
        raise ValueError("Unsafe source identifier")
    return results_dir / f"{source_id}.json"


def source_is_publishable(source, group):
    if source.get("group") != group or not source.get("enabled", True):
        return False
    if group == "bank":
        return source.get("adapter") != "review"
    return True


def build_result(source, extract_fn=extract, now=None):
    """Wrap extractor output in the stable JSON contract Apps Script expects."""
    checked_at = (now or dt.datetime.now(dt.timezone.utc)).isoformat()
    base = {
        "schema_version": SCHEMA_VERSION,
        "source_id": source["id"],
        "checked_at": checked_at,
        "status": "failed",
        "records": [],
        "fingerprint": "",
        "source_url": source["url"],
        "message": "",
    }
    passthrough = ("status", "records", "fingerprint", "source_url", "message", "retrieval_method", "stage", "render_status")
    try:
        extracted = extract_fn(source)
        base.update({k: extracted[k] for k in passthrough if k in extracted})
    except ReviewRequired as exc:
        base.update(status="review", message=str(exc)[:500])
        base.update(getattr(exc, "metadata", {}))
    except Exception as exc:
        base.update(status="failed", message=str(exc)[:500])
    return base


def run(group, results_dir=RESULTS_DIR):
    """Process all publishable sources in a group and save their result files."""
    sources = json.loads(CONFIG.read_text(encoding="utf-8"))
    selected = [s for s in sources if source_is_publishable(s, group)]
    results_dir.mkdir(parents=True, exist_ok=True)
    counts = {"ok": 0, "review": 0, "failed": 0}
    for source in selected:
        result = build_result(source)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        path = result_path(source["id"], results_dir)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
    return len(selected), counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", required=True, choices=("central", "bank"))
    args = parser.parse_args()
    total, counts = run(args.group)
    print(json.dumps({"group": args.group, "sources": total, "results": counts}, sort_keys=True))
