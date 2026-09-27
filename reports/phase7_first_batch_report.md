# Phase 7 first safe rule conversions

## Live workbook authority

The live Google workbook was exported read-only from the shared Google Sheet and the country tabs were used to build the Record-ID identity manifest because the live workbook export did not yet contain a `Record_ID_Manifest` tab.

Manifest validation:

- Inspected rows: 3,411
- Exported rows: 3,411
- Unique Record IDs: 3,411
- Missing Record IDs: 0
- Duplicate Record IDs: 0

Country row counts:

- Mauritius: 246
- Seychelles: 149
- Ghana: 240
- Nigeria: 240
- Kenya: 266
- South Africa: 240
- Tanzania: 253
- Cote Divoire: 240
- Senegal: 241
- Egypt: 240
- Morocco: 240
- Botswana: 177
- Namibia: 156
- Uganda: 240
- Zambia: 243

Live-vs-local reconciliation:

- Live unique Record IDs: 3,411
- Local consolidated unique Record IDs: 3,411
- IDs only in live: 1
- IDs only in local: 1
- Country count differences: none

## Sources converted in this batch

Only four sources were converted because these had official pages, deterministic labels, and exact live Record IDs. No Record IDs were invented.

| Source ID | Country | Bank | Product automated | Live Record ID | Retrieval | Result |
|---|---|---|---|---|---|---|
| `src-826359a55d1fbe8b` | Mauritius | ABC Banking Corporation | ABC Savings, Individuals | `3df58c69d7ff81bc` | direct HTTP | ok |
| `src-011547757936daae` | Mauritius | BCP Bank(Mauritius) | Savings, Individuals | `828fd3846c2bd65d` | direct HTTP | ok |
| `src-6db4c18f67255270` | Mauritius | AfrAsia Bank | Savings, Individuals | `6608e6e916f9b6b9` | direct HTTP | ok |
| `src-981fab275d20596e` | Morocco | CFG Bank | Regulated passbook savings rate | `bf05d7499c04c4bf` | direct HTTP | ok |

The rules identify product labels and rate text on official pages. They do not store final interest-rate values in `sources.json`.

## Sources deliberately left in review

- `src-5882f5135bf84b65` — FNB Namibia Access Immediately. Crawl4AI renders the page, but the expected amount row is still missing or ambiguous.
- `src-97dac4e1b8d5eb32` — FNB Namibia Access After a Fixed Period. Crawl4AI renders the page, but the expected tenor row is still missing or ambiguous.
- `src-76e978c5da35b69b` — NMB Tanzania. Jina retrieves challenge/changed content, but the expected official publication wording is not deterministically available.
- BICICI, UBA Zambia, Stanbic IBTC Nigeria, CBAO Senegal, Bank One, and other candidates were not converted because their product-to-row mapping, rate meaning, duplicate rows, or conditional wording needs more review.

## Validation

Tests run:

- `py -3 -m unittest -v test_extractor.py test_results.py test_audit_bank_sources.py test_record_manifest.py`
- `node ..\Banking_Updater\test_updater.mjs`
- `py -3 run_extract.py --group bank`

Results:

- Python unit tests: 43 passed
- Apps Script local tests: passed
- Full mapped commercial-bank extraction: 16 sources, 13 ok, 3 review, 0 failed
- Total emitted records from ok bank sources: 68
- Newly automated rows: 4

## Final non-ok sources after full run

| Source ID | Bank | Country | Status | Retrieval | Reason |
|---|---|---|---|---|---|
| `src-5882f5135bf84b65` | FNB Namibia | Namibia | review | crawl4ai | Product row is missing or ambiguous: `N$0 - 4 999` |
| `src-97dac4e1b8d5eb32` | FNB Namibia | Namibia | review | crawl4ai | Product row is missing or ambiguous: `3 Months` |
| `src-76e978c5da35b69b` | NMB Bank | Tanzania | review | jina_reader | Publication wording changed or is ambiguous |

## Safety preserved

- No Apps Script write logic was changed.
- No NMB or FNB rule was weakened.
- No new retrieval engine was added.
- No hard-coded current rates were added.
- Official publisher URLs remain the evidence URLs.
- Existing Record-ID validation, midpoint handling, ambiguity detection, and review/failure safeguards remain intact.
