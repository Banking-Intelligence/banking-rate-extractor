# Phase 5 Commercial-Bank Source Audit

Checked at: 2026-09-26T21:49:21.474905+00:00

## Summary

- Enabled bank-group sources audited: 232
- Adapter counts: {'rules': 16, 'review': 216}
- Tier counts: {'Mapped': 16, 'Tier A': 3, 'Tier B': 5, 'Tier C': 2, 'Directory': 206}
- FNB Namibia Access Immediately and Access After a Fixed Period remain review by policy.
- Candidate conversion is blocked unless existing workbook Record IDs are available for the exact product rows.

## Top candidate publications

| Tier | Country | Bank | Source ID | Retrieval | Rate meaning | Existing IDs | Manifest match | Manifest Record IDs | Deterministic reason |
|---|---|---|---|---|---|---:|---|---:|---|
| Tier A | Mauritius | Bank One | `src-e0c3794479e44377` | direct_http | single_numeric | 0 | exact | 19 | Official publication has identifiable table structure and explicit labels |
| Tier A | Mauritius | Mauritus Commercial Bank(MCB) | `src-a866ecbbd99927df` | direct_http | single_numeric | 0 | exact | 19 | Official publication has identifiable table structure and explicit labels |
| Tier B | Cote Divoire | BICICI | `src-03f5f03cf8322000` | direct_http | single_numeric | 0 | exact | 16 | Numeric rates and labels are visible, but parser may need regex or normalization |
| Tier B | Egypt | The United Bank of Egypt | `src-5c12cce71ec726b1` | direct_http | single_numeric | 0 | exact | 16 | Numeric rates and labels are visible, but parser may need regex or normalization |
| Tier B | Nigeria | Stanbic IBTC Bank | `src-6fda9bec19d1a868` | direct_http | single_numeric | 0 | exact | 16 | Numeric rates and labels are visible, but parser may need regex or normalization |
| Tier B | Senegal | CBAO Groupe Attijariwafa Bank | `src-85fc6b655cb3e5ad` | direct_http | single_numeric | 0 | exact | 16 | Numeric rates and labels are visible, but parser may need regex or normalization |
| Tier B | Zambia | United Bank of Africa(UBA) Zambia | `src-580ac56e8bbdabec` | direct_http | single_numeric | 0 | exact | 19 | Numeric rates and labels are visible, but parser may need regex or normalization |
| Tier A | Mauritius | SBM Bank (Mauritius) | `src-cd0ea2cb49049d0a` | direct_http | single_numeric | 0 | exact | 16 | Official publication has identifiable table structure and explicit labels |

## Product-rate review publications

| Tier | Country | Bank | Source ID | Retrieval | Record IDs available | Reason |
|---|---|---|---|---|---:|---|
| Tier A | Mauritius | Mauritus Commercial Bank(MCB) | `src-a866ecbbd99927df` | ok/direct_http | 0 | Official publication has identifiable table structure and explicit labels |
| Tier A | Mauritius | Bank One | `src-e0c3794479e44377` | ok/direct_http | 0 | Official publication has identifiable table structure and explicit labels |
| Tier A | Mauritius | SBM Bank (Mauritius) | `src-cd0ea2cb49049d0a` | ok/direct_http | 0 | Official publication has identifiable table structure and explicit labels |
| Tier B | Cote Divoire | BICICI | `src-03f5f03cf8322000` | ok/direct_http | 0 | Numeric rates and labels are visible, but parser may need regex or normalization |
| Tier C | Senegal | Bank of Africa(BOA) Senegal | `src-5a9648f44b55ed1a` | ok/direct_http | 0 | Numeric content is not structurally tied to clear product labels |
| Tier B | Senegal | CBAO Groupe Attijariwafa Bank | `src-85fc6b655cb3e5ad` | ok/direct_http | 0 | Numeric rates and labels are visible, but parser may need regex or normalization |
| Tier B | Zambia | United Bank of Africa(UBA) Zambia | `src-580ac56e8bbdabec` | ok/direct_http | 0 | Numeric rates and labels are visible, but parser may need regex or normalization |
| Tier B | Nigeria | Stanbic IBTC Bank | `src-6fda9bec19d1a868` | ok/direct_http | 0 | Numeric rates and labels are visible, but parser may need regex or normalization |
| Tier C | Ghana | Absa Bank Ghana | `src-0fdb9ddeadd5292b` | ok/direct_http | 0 | Rate wording is not a simple numeric published value or range |
| Tier B | Egypt | The United Bank of Egypt | `src-5c12cce71ec726b1` | ok/direct_http | 0 | Numeric rates and labels are visible, but parser may need regex or normalization |
