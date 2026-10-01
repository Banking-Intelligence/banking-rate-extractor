# Phase 9 Coverage Expansion Report

## Current branch and baseline

- Branch: `codex/phase9-coverage-expansion`
- Phase 8 merge baseline: `6826361 Merge pull request #3 from yusuf302/codex/phase8-second-mapping-batch`
- Current enabled commercial-bank rule sources: 22
- Current enabled commercial-bank review sources: 210
- Production approach remains unchanged: GitHub Actions extracts results; Apps Script writes validated results to the workbook.

## Stabilization before new mappings

The dirty working tree was first validated before adding Phase 9 mappings. The existing Phase 7 and Phase 8 mappings remained valid.

Validation run:

- Python extractor and manifest tests: 56 tests passed.
- Apps Script local updater tests: passed.
- Mapping registry validator: passed with 24 source/Record-ID mappings.
- Full bank extraction: completed with 0 failed sources.

## Live identity authority

`reports/live_record_manifest_sanitized.json` was regenerated from the live workbook export available locally. It contains only sanitized identity fields used for safe matching.

Manifest validation summary:

- Exported rows: 3,411
- Unique Record IDs: 3,411
- Duplicate Record IDs: 0
- Missing Record IDs: 0

## Phase 9 audit and candidate decision

The audit was rerun against the live manifest. Two candidates were accepted because the official source, product meaning, currency, and existing live Record IDs were exact.

Accepted:

1. `src-a866ecbbd99927df` — Mauritus Commercial Bank (MCB), Mauritius
   - Official source: `https://mcb.mu/rates-fees`
   - Retrieval method: direct official HTTP
   - Added records: 6
   - Mapping basis: official savings-rate text and official MUR term-deposit tables.

2. `src-580ac56e8bbdabec` — United Bank of Africa (UBA) Zambia, Zambia
   - Official source: `https://www.ubazambia.com/personal-banking/accounts/uba-savings-account/`
   - Retrieval method: direct official HTTP
   - Added records: 5
   - Mapping basis: official product sections for Kiddies, Teens, NextGen, Freedom, and Bumper accounts.

Rejected or left unchanged:

- United Bank Egypt: source primarily showed financing/LTV percentages, not a clear product interest rate suitable for spreadsheet rate rows.
- Stanbic IBTC Nigeria: source had reference-linked, monthly, or personalized/negotiated wording that is not safe for deterministic automation.
- FNB Namibia Access Immediately: left in review; product row remains missing or ambiguous.
- FNB Namibia Access After a Fixed Period: left in review; tenor row remains missing or ambiguous.
- NMB Tanzania: left in review; publication wording remains ambiguous under current deterministic rules.

## Files changed for Phase 9

- `sources.json`
  - Converted MCB and UBA Zambia from `review` to `rules`.
  - Added deterministic parsing rules tied only to official source text/tables and live Record IDs.

- `mapped_record_registry.json`
  - Added audit/control entries for the 11 new source/Record-ID mappings.

- `test_extractor.py`
  - Added Phase 9 parser regression tests for MCB and UBA Zambia.
  - Added safe-failure tests for missing, malformed, duplicate, or unrelated rows.
  - Kept the no-hard-coded-rate rule check for the new Phase 9 sources.

- `reports/live_record_manifest_sanitized.json`
  - Sanitized live Record-ID identity manifest used for matching.

- `reports/phase9_coverage_expansion_report.md`
  - This report.

## New automated rows

MCB Mauritius:

- `cbed3baca38afbf3`
- `d4736feb26068a47`
- `a9fc59997c16ed6a`
- `a9fc59997c16ed6a-bbec7dd4`
- `a9fc59997c16ed6a-4aff2e78`
- `a9fc59997c16ed6a-68c9cb98`

UBA Zambia:

- `7ea55f7bd0dc0e60`
- `7ea55f7bd0dc0e60-1ad277ee`
- `7ea55f7bd0dc0e60-eabe7eb9`
- `7ea55f7bd0dc0e60-b22151da`
- `e9c8f9311512100a`

## Final extraction result

Full bank extraction result after Phase 9 changes:

- Scheduled mapped sources: 22
- OK: 19
- Review: 3
- Failed: 0
- Emitted records: 88

Remaining non-OK mapped sources:

- `src-5882f5135bf84b65` — FNB Namibia — review — product row is missing or ambiguous: `N$0 - 4 999`
- `src-97dac4e1b8d5eb32` — FNB Namibia — review — product row is missing or ambiguous: `3 Months`
- `src-76e978c5da35b69b` — NMB Bank Tanzania — review — publication wording changed or is ambiguous

## Country-level coverage after Phase 9

- Botswana: 1 source, 6 emitted records
- Côte d’Ivoire: 1 source, 1 emitted record
- Ghana: 1 source, 1 emitted record
- Kenya: 1 source, 30 emitted records
- Mauritius: 7 sources, 17 emitted records
- Morocco: 1 source, 1 emitted record
- Namibia: 2 sources, 0 emitted records because both remain in review
- Senegal: 1 source, 1 emitted record
- Seychelles: 1 source, 7 emitted records
- South Africa: 1 source, 3 emitted records
- Tanzania: 3 sources, 14 emitted records
- Uganda: 1 source, 2 emitted records
- Zambia: 1 source, 5 emitted records

## Safety notes

- No new retrieval engine was added.
- No Apps Script write logic was changed.
- No workbook rows or Record IDs were invented.
- No rates were hard-coded into `sources.json` or Python.
- FNB Namibia and NMB Tanzania were deliberately left in review where deterministic evidence was still not strong enough.
