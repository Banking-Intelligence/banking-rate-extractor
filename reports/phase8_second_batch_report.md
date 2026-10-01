# Phase 8 second safe commercial-bank rule batch

## Baseline and audit

Live-derived Record-ID manifest remained the authority: 3,411 rows, 3,411 unique Record IDs, 0 missing IDs, 0 duplicate IDs.

Refreshed commercial-bank audit with `reports/live_record_manifest_sanitized.json` found:

- Mapped sources before Phase 8: 16
- Review sources before Phase 8: 216
- Tier A remaining review candidates: 3
- Tier B remaining review candidates: 5
- Product-publication exact bank matches from manifest audit: 10

Shortlist considered:

| Source ID | Country | Bank | Tier | Decision | Reason |
|---|---|---|---|---|---|
| `src-03f5f03cf8322000` | Cote Divoire | BICICI | Tier B | Selected | Official page has one special savings rate tied to XOF retail savings row. |
| `src-85fc6b655cb3e5ad` | Senegal | CBAO Groupe Attijariwafa Bank | Tier B | Selected | Official PDF states simple savings interest clearly. |
| `src-cd0ea2cb49049d0a` | Mauritius | SBM Bank (Mauritius) | Tier A | Selected | Official table has savings and 12-month MUR term deposit rows matching live rows. |
| `src-e0c3794479e44377` | Mauritius | Bank One | Tier A | Selected | Official tariff table has exact savings tiers/products already represented in live rows. |
| `src-a866ecbbd99927df` | Mauritius | Mauritus Commercial Bank(MCB) | Tier A | Rejected | Several 12-month rows and table structure need more identity review before new rules. |
| `src-5c12cce71ec726b1` | Egypt | The United Bank of Egypt | Tier B | Rejected | Detected values are loan-to-value percentages, not deterministic rates for workbook rows. |
| `src-6fda9bec19d1a868` | Nigeria | Stanbic IBTC Bank | Tier B | Rejected | Uses MPR/reference-linked savings language and monthly loan rates. |
| `src-580ac56e8bbdabec` | Zambia | United Bank of Africa(UBA) Zambia | Tier B | Rejected | Multiple similar savings products and duplicate retail rows make row identity ambiguous. |

## New mappings added

| Source ID | Country | Bank | Record IDs added | Emitted records |
|---|---|---|---|---:|
| `src-03f5f03cf8322000` | Cote Divoire | BICICI | `77c79ab8942a9190` | 1 |
| `src-85fc6b655cb3e5ad` | Senegal | CBAO Groupe Attijariwafa Bank | `ca8ccb1104402be2` | 1 |
| `src-cd0ea2cb49049d0a` | Mauritius | SBM Bank (Mauritius) | `c97791493abc9fdd`, `1d4a911081bbbca9` | 2 |
| `src-e0c3794479e44377` | Mauritius | Bank One | `50b2f0241b37b51c`, `50b2f0241b37b51c-e82cfddd`, `50b2f0241b37b51c-d84bf1c2`, `0ba341b1bc65072e`, `0ba341b1bc65072e-dad7c69c` | 5 |

New countries represented in automated rules: Cote Divoire and Senegal.

## Mapping registry

Created `mapped_record_registry.json` with 13 non-sensitive mappings:

- 4 Phase 7 mappings
- 9 Phase 8 record mappings

Registry validation passed. The registry is an audit/control artifact only; runtime extraction still uses `sources.json`.

## Validation

Tests and checks run:

- `py -3 -m unittest -v test_extractor.py test_results.py test_audit_bank_sources.py test_record_manifest.py test_mapping_registry.py` — 52 passed
- `node ..\Banking_Updater\test_updater.mjs` — passed
- `py -3 validate_mapping_registry.py` — passed
- Independent live extraction for all four new sources — all `ok`
- Full bank extraction — completed with 20 mapped sources, 15 ok, 5 review, 0 failed
- Follow-up recheck for existing BSB and DTB sources — both returned `ok`; refreshed their result JSON files

Final verified result-file state after rechecking transient existing-source reviews:

- Mapped sources: 20
- OK: 17
- Review: 3
- Failed: 0
- Emitted records: 77
- Previous mapped count: 16
- Previous emitted records: 68
- New automated rows: 9

Automated ok sources by country:

- Mauritius: 6
- Tanzania: 2
- Kenya: 1
- Cote Divoire: 1
- Uganda: 1
- Botswana: 1
- Senegal: 1
- South Africa: 1
- Morocco: 1
- Ghana: 1
- Seychelles: 1

Remaining review sources are deliberately unchanged:

- `src-5882f5135bf84b65` — FNB Namibia Access Immediately
- `src-97dac4e1b8d5eb32` — FNB Namibia Access After a Fixed Period
- `src-76e978c5da35b69b` — NMB Tanzania

## Safety notes

- No Apps Script write logic changed.
- No new retrieval engine added.
- No FNB Namibia or NMB Tanzania mapping changed.
- No Record IDs invented.
- No current rate values were stored as data in `sources.json`.
- Source URLs remain official bank URLs/PDFs.
