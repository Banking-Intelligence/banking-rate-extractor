"""
Bank-source audit tests.

These tests keep the audit tool conservative so homepage/directory records are
not mistaken for safe product-rate automation candidates.
"""

import unittest

from audit_bank_sources import audit_source, classify_rate_meaning, rank_candidates, source_kind, tier_for


class BankSourceAuditTests(unittest.TestCase):
    def test_source_kind_distinguishes_product_publications_from_directory_records(self):
        self.assertEqual(source_kind({'id': 'src-example'}), 'product_publication')
        self.assertEqual(source_kind({'id': 'bank-example'}), 'directory_record')

    def test_rate_meaning_uses_rate_bearing_snippets_not_generic_contact_text(self):
        text = 'Contact us for support. Savings account pays 3.5% per annum.'
        self.assertEqual(classify_rate_meaning(text), 'single_numeric')
        self.assertEqual(classify_rate_meaning('Term deposit 3.0% - 4.0% p.a.'), 'range')
        self.assertEqual(classify_rate_meaning('Loan Prime + 2%'), 'reference_linked')
        self.assertEqual(classify_rate_meaning('Term deposit available upon request'), 'personalised_or_negotiated')

    def test_tier_a_requires_numeric_rates_and_clear_structure(self):
        source = {'id': 'src-example', 'adapter': 'review'}
        content = {
            'rate_meaning': 'single_numeric',
            'contains_numeric_interest_rates': True,
            'tables_structurally_identifiable': True,
            'product_or_tenor_labels_explicit': True,
        }
        tier, reason = tier_for(source, content, 'ok')
        self.assertEqual(tier, 'Tier A')
        self.assertIn('identifiable table', reason)

    def test_directory_records_are_not_conversion_candidates(self):
        item = audit_source({'id': 'bank-example', 'group': 'bank', 'enabled': True, 'adapter': 'review', 'allowed_hosts': ['bank.example'], 'url': 'https://bank.example/', 'country': 'X', 'name': 'Bank'}, fetch_review_publications=False)
        self.assertEqual(item['tier'], 'Directory')
        self.assertFalse(item['automation_appears_deterministic'])

    def test_rank_candidates_prefers_tier_a_and_country_spread(self):
        items = [
            {'source_id': 'a1', 'source_kind': 'product_publication', 'tier': 'Tier A', 'country': 'A', 'bank_name': 'One'},
            {'source_id': 'a2', 'source_kind': 'product_publication', 'tier': 'Tier A', 'country': 'A', 'bank_name': 'Two'},
            {'source_id': 'b1', 'source_kind': 'product_publication', 'tier': 'Tier B', 'country': 'B', 'bank_name': 'Three'},
            {'source_id': 'c1', 'source_kind': 'product_publication', 'tier': 'Tier C', 'country': 'C', 'bank_name': 'Four'},
            {'source_id': 'd1', 'source_kind': 'directory_record', 'tier': 'Tier A', 'country': 'D', 'bank_name': 'Five'},
        ]
        ranked = rank_candidates(items, limit=3)
        self.assertEqual([i['source_id'] for i in ranked], ['a1', 'a2', 'b1'])


if __name__ == '__main__':
    unittest.main()
