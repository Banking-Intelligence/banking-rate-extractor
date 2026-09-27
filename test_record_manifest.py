import tempfile
import unittest
from pathlib import Path

from import_record_manifest import (
    ManifestError,
    classify_source_match,
    load_manifest,
    match_sources,
    sanitized_manifest,
    validate_manifest_rows,
)

COUNTRIES = {'Tanzania', 'Zambia', 'Mauritius'}


def row(**overrides):
    base = {
        'Record ID': 'rid-1',
        'Country': 'Tanzania',
        'Sheet': 'Tanzania',
        'Bank Name': 'NMB Bank',
        'Type': 'Deposit',
        'Product / Tenor': '3 Months',
        'Currency': 'TZS',
        'Website Link': 'https://nmb.example',
        'Data Source Link': 'https://nmb.example/rates',
        'Manual Override': 'No',
    }
    base.update(overrides)
    return base


class RecordManifestTests(unittest.TestCase):
    def test_valid_manifest_and_sanitized_output(self):
        valid = validate_manifest_rows([row()], countries=COUNTRIES)
        self.assertEqual(valid['diagnostics']['unique_record_ids'], 1)
        sanitized = sanitized_manifest(valid)
        self.assertEqual(set(sanitized['records'][0]), {'Record ID','Country','Sheet','Bank Name','Type','Product / Tenor','Currency'})
        self.assertNotIn('Website Link', sanitized['records'][0])

    def test_duplicate_and_missing_record_ids_are_rejected(self):
        with self.assertRaisesRegex(ManifestError, 'Duplicate Record ID'):
            validate_manifest_rows([row(), row(Product__Tenor='ignored')], countries=COUNTRIES)
        with self.assertRaisesRegex(ManifestError, 'missing Record ID'):
            validate_manifest_rows([row(**{'Record ID': ''})], countries=COUNTRIES)

    def test_required_columns_country_and_currency_validation(self):
        bad = row(); del bad['Currency']
        with self.assertRaisesRegex(ManifestError, 'Missing required columns'):
            validate_manifest_rows([bad], countries=COUNTRIES)
        with self.assertRaisesRegex(ManifestError, 'Invalid country'):
            validate_manifest_rows([row(Country='Atlantis')], countries=COUNTRIES)
        with self.assertRaisesRegex(ManifestError, 'Invalid currency'):
            validate_manifest_rows([row(Currency='Tanzanian shilling')], countries=COUNTRIES)

    def test_sensitive_columns_rejected_by_default(self):
        with self.assertRaisesRegex(ManifestError, 'sensitive-looking'):
            validate_manifest_rows([dict(row(), **{'Access Token': 'secret'})], countries=COUNTRIES)

    def test_csv_json_loading(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / 'manifest.csv'
            csv_path.write_text('Record ID,Country,Sheet,Bank Name,Type,Product / Tenor,Currency\nrid,Tanzania,Tanzania,NMB Bank,Deposit,3 Months,TZS\n', encoding='utf-8')
            self.assertEqual(load_manifest(csv_path)[0]['Record ID'], 'rid')
            json_path = Path(d) / 'manifest.json'
            json_path.write_text('{"schema_version":1,"records":[{"Record ID":"rid","Country":"Tanzania","Sheet":"Tanzania","Bank Name":"NMB Bank","Type":"Deposit","Product / Tenor":"3 Months","Currency":"TZS"}]}', encoding='utf-8')
            self.assertEqual(load_manifest(json_path)[0]['Bank Name'], 'NMB Bank')

    def test_exact_candidate_ambiguous_and_none_matching(self):
        records = [row(), row(**{'Record ID':'rid-2','Product / Tenor':'6 Months'}), row(**{'Record ID':'rid-3','Bank Name':'Other Bank'})]
        status, matches = classify_source_match({'country':'Tanzania','target':'Tanzania','name':'NMB Bank'}, records)
        self.assertEqual(status, 'exact')
        self.assertEqual({m['Record ID'] for m in matches}, {'rid-1','rid-2'})
        status, matches = classify_source_match({'country':'Tanzania','target':'Tanzania','name':'Unknown Bank'}, records)
        self.assertEqual(status, 'none')
        ambiguous_records = [row(**{'Record ID':'rid-4','Bank Name':'ABC Bank'}), row(**{'Record ID':'rid-5','Bank Name':'ABC Savings Bank'})]
        status, matches = classify_source_match({'country':'Tanzania','target':'Tanzania','name':'ABC Bank'}, ambiguous_records)
        self.assertIn(status, {'exact', 'ambiguous'})

    def test_source_matching_reports_review_publications_only(self):
        valid = validate_manifest_rows([row()], countries=COUNTRIES)
        sources = [
            {'id':'src-nmb','group':'bank','enabled':True,'adapter':'review','country':'Tanzania','target':'Tanzania','name':'NMB Bank','url':'https://nmb.example'},
            {'id':'bank-nmb','group':'bank','enabled':True,'adapter':'review','country':'Tanzania','target':'Tanzania','name':'NMB Bank','url':'https://nmb.example'},
            {'id':'src-mapped','group':'bank','enabled':True,'adapter':'rules','country':'Tanzania','target':'Tanzania','name':'NMB Bank','url':'https://nmb.example'},
        ]
        matches = match_sources(valid, sources)
        self.assertEqual([m['source_id'] for m in matches], ['src-nmb'])
        self.assertEqual(matches[0]['match_status'], 'exact')

    def test_currency_and_product_mismatch_do_not_create_false_row_identity(self):
        valid = validate_manifest_rows([row(Currency='USD', **{'Product / Tenor':'Savings'})], countries=COUNTRIES)
        source = {'id':'src-nmb','group':'bank','enabled':True,'adapter':'review','country':'Tanzania','target':'Tanzania','name':'NMB Bank','url':'https://nmb.example','match_currency':'TZS'}
        self.assertEqual(match_sources(valid, [source])[0]['match_status'], 'none')
        source = {**source, 'match_currency':'USD', 'match_product':'3 Months'}
        self.assertEqual(match_sources(valid, [source])[0]['match_status'], 'none')
        source = {**source, 'match_product':'Savings'}
        self.assertEqual(match_sources(valid, [source])[0]['match_status'], 'exact')


if __name__ == '__main__':
    unittest.main()

