"""Read all enabled bank sources, including homepages, without creating rates.

The ordinary extractor runs reviewed mappings only. This audit also checks the
unmapped directory pages and discovers approved product/rate publication links.
Those links are candidates for human mapping, never permission to write rows.
"""
import argparse
import collections
import concurrent.futures
import datetime as dt
import hashlib
import json
import re
import urllib.parse
from pathlib import Path

from lxml import html
from audit_bank_sources import inspect_content, source_kind
from extractor import CONFIG, ReviewRequired, allowed, fetch_publication

PUBLICATION_WORDS = re.compile(r"interest|rate|tariff|pricing|deposit|savings|epargne|taux|conditions", re.I)


def publication_links(raw, official_url, source):
    """Find relevant links while enforcing the existing official-host checks."""
    if raw.startswith(b"%PDF"):
        return []
    doc = html.fromstring(raw)
    found = {}
    for anchor in doc.xpath('//a[@href]'):
        url = urllib.parse.urljoin(official_url, anchor.get('href'))
        label = re.sub(r'\s+', ' ', anchor.text_content()).strip()
        if allowed(url, source) and PUBLICATION_WORDS.search(label + ' ' + url):
            url = urllib.parse.urldefrag(url)[0]
            found.setdefault(url, {'url': url, 'label': label[:150]})
    return list(found.values())[:25]


def inspect_source(source, cache_dir=None):
    """Fetch a source for diagnosis; no extraction rule or result file is changed."""
    result = {'source_id': source['id'], 'country': source['country'],
              'bank_name': source['name'], 'adapter': source['adapter'],
              'source_kind': source_kind(source), 'source_url': source['url'],
              'mapped_record_ids': [r['record_id'] for r in source.get('rules', []) if 'record_id' in r],
              'publication_links': [], 'status': 'review'}
    try:
        _, raw, url, meta = fetch_publication(source)
        result.update(source_url=url, retrieval_method=meta.get('retrieval_method'),
                      fingerprint=hashlib.sha256(raw).hexdigest(), status='retrieved')
        result.update(inspect_content(raw))
        result['publication_links'] = publication_links(raw, url, source)
        if cache_dir:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            (Path(cache_dir) / (source['id'] + '.bin')).write_bytes(raw)
    except ReviewRequired as exc:
        result.update(message=str(exc), **exc.metadata)
    except Exception as exc:
        result.update(status='retrieval_failed', message=str(exc)[:500])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cache-dir', help='Optional local evidence cache, outside Git history')
    parser.add_argument('--workers', type=int, default=6)
    args = parser.parse_args()
    sources = [s for s in json.loads(CONFIG.read_text(encoding='utf-8'))
               if s.get('group') == 'bank' and s.get('enabled', True)]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(inspect_source, s, args.cache_dir): s for s in sources}
        for job in concurrent.futures.as_completed(pending):
            item = job.result()
            results.append(item)
            print(f"{len(results)}/{len(sources)} {item['country']} {item['bank_name']}: {item['status']}", flush=True)
    payload = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
               'source_count': len(results),
               'status_counts': dict(collections.Counter(r['status'] for r in results)),
               'sources': sorted(results, key=lambda r: (r['country'], r['bank_name'], r['source_id']))}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload['status_counts']), flush=True)


if __name__ == '__main__':
    main()
