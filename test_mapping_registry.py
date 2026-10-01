"""
Mapping registry tests.

These tests check that automated source-to-row mappings are documented once
and match the country and currency in sources.json.
"""

import unittest

from validate_mapping_registry import RegistryError, load_registry, validate_registry


class MappingRegistryTests(unittest.TestCase):
    def test_registry_validates_against_sources(self):
        diagnostics = validate_registry(load_registry())
        self.assertGreaterEqual(diagnostics['mappings'], 13)
        self.assertIn('Mauritius', diagnostics['countries'])

    def test_duplicate_source_record_pair_rejected(self):
        rows = load_registry()
        with self.assertRaisesRegex(RegistryError, 'Duplicate'):
            validate_registry(rows + [dict(rows[0])])

    def test_missing_rule_pair_rejected(self):
        rows = load_registry()
        bad = [dict(r) for r in rows]
        bad[0]['record_id'] = 'missing-record'
        with self.assertRaisesRegex(RegistryError, 'not present'):
            validate_registry(bad)

    def test_country_currency_and_basis_validation(self):
        rows = load_registry()
        bad_country = [dict(r) for r in rows]
        bad_country[0]['country'] = 'Atlantis'
        with self.assertRaisesRegex(RegistryError, 'Country mismatch'):
            validate_registry(bad_country)
        bad_currency = [dict(r) for r in rows]
        bad_currency[0]['currency'] = 'Mauritian rupee'
        with self.assertRaisesRegex(RegistryError, 'Invalid currency'):
            validate_registry(bad_currency)
        bad_basis = [dict(r) for r in rows]
        bad_basis[0]['mapping_basis'] = 'guessed'
        with self.assertRaisesRegex(RegistryError, 'Unsupported mapping basis'):
            validate_registry(bad_basis)


if __name__ == '__main__':
    unittest.main()
