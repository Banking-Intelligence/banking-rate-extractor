# Commercial-bank coverage audit — 5 October 2026

## Findings

Inspected all 15 country tables in a fresh live workbook export and retrieved all 232 enabled bank sources using the existing retrieval chain. The source audit retrieved 214 publications/pages; 14 failed retrieval and 4 required review. Retrieval is not proof of a usable interest rate. Homepage/news percentages, foreign-parent bank rates, fees and promotional terms cannot automatically satisfy product mappings.

The extractor previously scheduled only 22 mapped sources; 210 review entries were not extracted into bank result files. The GitHub schedule is Monday weekly, not daily. A daily Apps Script run validates existing JSON; it does not itself create missing product mappings.

### Live workbook before this change

| Country | Rows | Banks | Numeric-rate rows | Rate availability | Exact-source links |
|---|---:|---:|---:|---:|---:|
| Mauritius | 246 | 15 | 17 | 6.9% | 20 |
| Seychelles | 149 | 9 | 7 | 4.7% | 23 |
| Ghana | 240 | 15 | 1 | 0.4% | 2 |
| Nigeria | 240 | 15 | 0 | 0.0% | 4 |
| Kenya | 266 | 15 | 30 | 11.3% | 30 |
| South Africa | 240 | 15 | 3 | 1.2% | 3 |
| Tanzania | 253 | 15 | 24 | 9.5% | 24 |
| Cote Divoire | 240 | 15 | 1 | 0.4% | 1 |
| Senegal | 241 | 15 | 3 | 1.2% | 3 |
| Egypt | 240 | 15 | 0 | 0.0% | 1 |
| Morocco | 240 | 15 | 1 | 0.4% | 1 |
| Botswana | 177 | 11 | 6 | 3.4% | 6 |
| Namibia | 156 | 9 | 16 | 10.3% | 32 |
| Uganda | 240 | 15 | 2 | 0.8% | 2 |
| Zambia | 243 | 15 | 5 | 2.1% | 22 |

Total Record IDs: 3411; duplicate IDs: 0; spreadsheet formula errors found: 0. Counts describe all physical rows, including hidden detail and placeholders, not all verified terms.

## Verified additions

- Access Bank Nigeria (`bank-eea41274b759`): annual ordinary retail savings, live ID `d2e5a105f2ed2b1f`. All named ordinary savings columns must agree; HIDA's unrelated tiers are excluded. A future difference sends the source to review.
- ATLANTICO Namibia (`bank-749c4d4e2cf9`): ordinary 3/6/12-month NAD fixed deposits. IDs `fd2989a146aa1b09`, `521ba3f051c5165b`, `ce8bb6e1e7805111`. Promotional new-client offer is excluded, not blended into a range.
- Banque Misr Egypt (`bank-5cfa550f9cc9`): 12-month USD deposit, live ID `84fb22a27adbbaee`, matching existing USD 500 minimum and the official USD 500–25,000 tier. The PDF is parsed in visual layout order: unique product page, exact tier boundaries, exact currency/tenor header, unique USD row and YEAR column. Evidence retains the tier. Other EGP/USD tiers and payment variants remain unmapped.

No rates are stored in config or Python. Five existing rows gain mappings, across three countries; no rows or IDs are created. Registry entries use the fresh live export. Official URLs remain evidence URLs, including when Jina retrieves content.

## Deliberately unresolved

- FNB Namibia Access Immediately and Access After a Fixed Period: current rendered content does not uniquely match existing configured product rows.
- NMB Tanzania: current publication content does not match the reviewed rate wording. Previous success is not assumed to mean present success.
- Standard Chartered Ghana: official rates board found, but generic fixed-deposit rows lack a unique balance-tier identity.
- Other Banque Misr savings/EGP deposits: multiple balance/payment variants; cannot choose a rate merely to improve coverage.
- BOA Senegal, Stanbic Nigeria pricing guide, United Bank Egypt mortgage and Absa Ghana loan: require further exact product/tenor/amount interpretation before conversion.
- Parent-bank pages for overseas branches: reject rates for a different country/currency.
- Visible explanatory amount/loan cells and legacy numeric published-low/high fields exist in some rows. Their presence is not verification. This change does not overwrite those fields with guessed terms.

## Validation

79 Python tests pass, including synthetic fixtures for wrong currency/product/tenor, duplicates, missing/malformed/qualified rates, retail disagreement, PDF tier boundaries, and discovery provenance. Existing Apps Script local tests pass. Mapping registry validation passes (registry is partial historical coverage: existing entries plus new mappings; not a complete runtime authority).

Raw downloaded evidence and workbook export are kept outside the Git repository. `reports/commercial_full_source_audit.json` is a read-only public-source diagnostic snapshot taken before conversions; its tier/rate hints require manual interpretation and never generate rates.

### Updater repair

The live updater requested GitHub files even for `adapter: review` bank directory sources. Those files intentionally do not exist. A narrow `readSource_` guard now returns review without network calls or writes. Mapped sources still use all existing GitHub validation. No schedules or credentials are changed.

### Existing mapping repair

MauBank's HTML table becomes plain text in Jina. The old rule also pinned a changing rate inside its expected header. The new rule matches the exact Household Savings label, annual unit, and adjoining Savings Base Rate label in both representations, capturing the rate dynamically. Duplicate, qualified and wrong-product text stays review. Live direct HTML and Jina both passed.
