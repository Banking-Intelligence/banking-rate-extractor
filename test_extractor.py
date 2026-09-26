import unittest, math, ssl, urllib.error
from unittest import mock
from extractor import rate,ReviewRequired,allowed,parse_sarb,retrieve,parse_rules,row_label_matches
class ExtractionTests(unittest.TestCase):
 def test_midpoint(self):
  r=rate('2%–3%');self.assertAlmostEqual(r['rate'],.025);self.assertEqual(r['method'],'Calculated midpoint')
 def test_french_decimal(self):self.assertAlmostEqual(rate('1,75% - 2,00%')['rate'],.01875)
 def test_replacement_dash_range(self):self.assertAlmostEqual(rate('1.75% � 2.75%')['rate'],.0225)
 def test_zero_is_not_missing(self):self.assertEqual(rate('0%')['rate'],0)
 def test_qualifiers_not_guessed(self):
  for v in ['Up to 3%','From 2%','Prime + 2%','Negotiable','N/A','3% - 2%','2% monthly','2.5% / 3.5%']:
   with self.subTest(v=v),self.assertRaises(ReviewRequired):rate(v)
 def test_publisher_allowlist(self):
  s={'allowed_hosts':['bank.example']}
  self.assertTrue(allowed('https://bank.example/rates.pdf',s))
  for u in ['http://bank.example/','https://evil.example/','https://bank.example.evil.test/','https://u:p@bank.example/','https://bank.example:8080/']:
   self.assertFalse(allowed(u,s))

 def test_direct_retrieval_success(self):
  with mock.patch('extractor.retrieve_http', return_value={'body':b'<html>ok</html>','url':'https://bank.example/rates','retrieval_method':'direct_http'}), mock.patch('extractor.retrieve_jina_reader') as fallback:
   out=retrieve('https://bank.example/rates',{'allowed_hosts':['bank.example']})
   self.assertEqual(out['retrieval_method'],'direct_http');self.assertEqual(out['url'],'https://bank.example/rates');fallback.assert_not_called()
 def test_fallback_after_ssl_failure(self):
  with mock.patch('extractor.retrieve_http', side_effect=urllib.error.URLError(ssl.SSLError('certificate verify failed'))), mock.patch('extractor.retrieve_jina_reader', return_value={'body':b'| Product | Rate |\n| --- | --- |\n| A | 2% |','url':'https://bank.example/rates','retrieval_method':'jina_reader'}):
   out=retrieve('https://bank.example/rates',{'allowed_hosts':['bank.example']})
   self.assertEqual(out['retrieval_method'],'jina_reader');self.assertEqual(out['url'],'https://bank.example/rates')
 def test_both_retrieval_methods_fail_for_review(self):
  with mock.patch('extractor.retrieve_http', side_effect=urllib.error.URLError(ssl.SSLError('certificate verify failed'))), mock.patch('extractor.retrieve_jina_reader', side_effect=TimeoutError('timeout')):
   with self.assertRaises(ReviewRequired):retrieve('https://bank.example/rates',{'allowed_hosts':['bank.example']})
 def test_fallback_does_not_authorize_proxy_domain(self):
  s={'allowed_hosts':['bank.example']}
  self.assertFalse(allowed('https://r.jina.ai/https://bank.example/rates',s))
 def test_escaped_space_row_labels_match(self):
  self.assertTrue(row_label_matches('Save\\ As\\ You\\ Earn\\(SAYE\\)','Save As You Earn (SAYE)'))
  self.assertTrue(row_label_matches('3\\ Months','3 Months'))
 def test_markdown_table_rules_preserve_record_ids(self):
  src={'id':'src-3557d0482cf2a1ce','target':'Botswana','url':'https://www.bsb.bw/rates-and-pricing/','scope':'Bank-published product rates','rules':[{'kind':'table','table_header':['Type of Deposit','Nominal Interest Rates (%)Lowest-Highest','Actual Interest Rates (%)Lowest-Highest','Minimum Opening Balance'],'row_label':'Sesigo','label_column':0,'column':1,'record_id':'4cd389f2af3c9cf0'}]}
  raw=b'| Type of Deposit | Nominal Interest Rates (%) Lowest-Highest | Actual Interest Rates (%) Lowest-Highest | Minimum Opening Balance |\n| --- | --- | --- | --- |\n| Sesigo | 2% - 3% | 2% - 3% | P100 |'
  records=parse_rules(src,raw)
  self.assertEqual(records[0]['id'],'4cd389f2af3c9cf0');self.assertAlmostEqual(records[0]['rate'],.025)
 def test_markdown_rules_do_not_verify_ambiguous_rates(self):
  src={'id':'src-test','target':'Botswana','url':'https://www.bsb.bw/rates-and-pricing/','rules':[{'kind':'table','table_header':['Product','Rate'],'row_label':'Sesigo','label_column':0,'column':1,'record_id':'r1'}]}
  raw=b'| Product | Rate |\n| --- | --- |\n| Sesigo | Up to 3% |'
  with self.assertRaises(ReviewRequired):parse_rules(src,raw)
 def test_units(self):
  import json
  s={'id':'cb-test','target':'Test','url':'https://bank.example/'}
  base={'Name':'SARB Policy Rate','SectionName':'Money Market Rates','TimeseriesCode':'A','Date':'2026-09-10','Value':7}
  gold=dict(base,Name='US Dollar',SectionId='CMRLGP',SectionName='London gold price',Value=4405.7,TimeseriesCode='B')
  out=parse_sarb(s,json.dumps([base,gold]).encode());self.assertEqual(out[0]['value'],.07);self.assertEqual(out[1]['value'],4405.7);self.assertEqual(out[1]['unit'],'USD per fine ounce')
if __name__=='__main__':unittest.main()
