# Banking rate extractor

This private repository retrieves configured public bank and central-bank publications. GitHub Actions writes versioned JSON files under `results/`; the Banking Intelligence Apps Script imports those files into Google Sheets through stable Record IDs.

The workflows run central-bank extraction daily at 04:30 and commercial-bank extraction Monday at 05:30, Africa/Dar_es_Salaam. Both can also be run manually from the Actions page.

Failures, ambiguous publications and changed page structures produce review results. They never replace established spreadsheet values.
