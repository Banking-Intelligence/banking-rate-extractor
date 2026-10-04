# Phase 10 Commercial-Bank Mapping Start

Checked on 2026-10-04.

## What was checked

This pass started with the two examples supplied for the next commercial-bank mapping work:

- National Bank of Egypt / NBE product page
- GTBank Ghana savings and investment accounts page

The audit was also rerun against the live Record-ID manifest to see whether any remaining review source could safely become a deterministic rule.

## Findings

- NBE currently rejects direct extractor retrieval. Jina Reader retrieves the general NBE site shell, but not the routed product-rate table from the supplied product URL. This is not safe to map yet.
- GTBank Ghana account pages are retrievable, but they describe products using wording such as prevailing or competitive interest. They do not publish exact numeric savings or fixed-deposit rates in the page HTML checked here.
- GTBank Ghana's official tariff PDF was checked as a possible source, but it is mainly a fees/tariff document rather than a clear product-rate publication for the workbook rows.
- United Bank of Egypt's mortgage page was previously ranked too highly by the audit because it contains percentages such as financing up to 80% of property value. That is not an interest rate.
- Stanbic IBTC Nigeria remains visible to the audit because it contains numeric rates, but the exact published products do not safely match the generic live workbook rows.

## Change made

The audit tool is now stricter. It no longer treats non-rate percentages such as financing up to 80% of property value as safe interest-rate evidence, and it treats MPR-linked savings wording as reference-linked rather than a clean fixed rate.

## Mapping decision

No new commercial-bank source was converted in this pass. That is intentional. The evidence found was not exact enough to update live workbook rows safely.

## Next best mapping work

The next productive step is to target banks with official pages or PDFs that show clear numeric rows like:

- product name;
- tenor;
- currency;
- exact rate or exact range;
- official source URL.

For Egypt and Ghana specifically, the next investigation should look for downloadable official rate sheets, tariff/rate PDFs, or hidden official data endpoints rather than general product pages.
