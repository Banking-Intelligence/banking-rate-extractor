"""
Extractor safety tests.

These tests protect the rules that matter most: official-source provenance,
range midpoints, ambiguity rejection, retrieval fallbacks, and exact Record-ID
mapping for automated bank sources.
"""

import unittest, math, ssl, urllib.error
from unittest import mock
from extractor import rate,ReviewRequired,allowed,parse_sarb,retrieve,parse_rules,parse_central_rules,parse_bceao_country,parse_zambia_api,row_label_matches,extract
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
 def test_nmb_jina_challenge_stays_review(self):
  src={'id':'src-76e978c5da35b69b','target':'Tanzania','url':'https://www.nmbbank.co.tz/investor-relations-nmb/financial-and-regulatory-reports/disclosure?download=469:2026-minimum-disclosure-of-interest-rates-fees-and-charges','rules':[{'kind':'regex','pattern':'\\b3\\s+Months\\s+(?P<rate>\\d+(?:\\.\\d+)?%)','record_id':'9dd848740cd021b7'}]}
  raw=b'Title: Just a moment...\n\nWarning: Target URL returned error 403: Forbidden\n\nMarkdown Content:\nEnable JavaScript and cookies to continue'
  with self.assertRaises(ReviewRequired):parse_rules(src,raw)
 def test_fnb_unrelated_static_table_stays_review(self):
  src={'id':'src-5882f5135bf84b65','target':'Namibia','url':'https://www.fnbnamibia.com.na/rates-pricing/accessImmediately.html','rules':[{'kind':'table','table_header':['Amount','Nominal','Effective'],'row_label':'N\\$0\\ \\-\\ 4\\ 999','label_column':0,'column':1,'record_id':'e615d6cec91d603b'}]}
  raw=b'<table><tr><th>Sales and Services</th><th>Tellers</th></tr><tr><td>Monday and Friday</td><td>8:30 - 16:00</td></tr></table>'
  with self.assertRaises(ReviewRequired):parse_rules(src,raw)

 def test_crawl4ai_fallback_only_for_configured_sources(self):
  src={'id':'src-test','target':'Namibia','url':'https://www.fnbnamibia.com.na/rates-pricing/accessImmediately.html','allowed_hosts':['www.fnbnamibia.com.na'],'adapter':'rules','rules':[{'kind':'table','table_header':['Amount','Nominal','Effective'],'row_label':'N\\$0\\ \\-\\ 4\\ 999','label_column':0,'column':1,'record_id':'r1'}]}
  raw=b'<table><tr><th>Sales and Services</th><th>Tellers</th></tr></table>'
  with mock.patch('extractor.fetch_publication', return_value=(src,raw,src['url'],{'retrieval_method':'direct_http'})), mock.patch('extractor.retrieve_crawl4ai') as crawl:
   with self.assertRaises(ReviewRequired):extract(src)
   crawl.assert_not_called()
 def test_crawl4ai_fallback_parses_valid_rendered_table(self):
  src={'id':'src-5882f5135bf84b65','target':'Namibia','url':'https://www.fnbnamibia.com.na/rates-pricing/accessImmediately.html','allowed_hosts':['www.fnbnamibia.com.na'],'adapter':'rules','retrieval_fallback':'crawl4ai','rules':[{'kind':'table','table_header':['Amount','Nominal','Effective'],'row_label':'N\\$0\\ \\-\\ 4\\ 999','label_column':0,'column':1,'record_id':'e615d6cec91d603b'}]}
  raw=b'<table><tr><th>Sales and Services</th><th>Tellers</th></tr></table>'
  rendered=b'<table><tr><th>Amount</th><th>Nominal</th><th>Effective</th></tr><tr><td>N$0 - 4 999</td><td>2.31%</td><td>2.33%</td></tr></table>'
  with mock.patch('extractor.fetch_publication', return_value=(src,raw,src['url'],{'retrieval_method':'direct_http'})), mock.patch('extractor.retrieve_crawl4ai', return_value={'body':rendered,'url':src['url'],'retrieval_method':'crawl4ai','render_status':200}):
   result=extract(src)
   self.assertEqual(result['status'],'ok');self.assertEqual(result['retrieval_method'],'crawl4ai');self.assertEqual(result['source_url'],src['url']);self.assertEqual(result['records'][0]['id'],'e615d6cec91d603b')
 def test_crawl4ai_failure_does_not_create_ok(self):
  src={'id':'src-5882f5135bf84b65','target':'Namibia','url':'https://www.fnbnamibia.com.na/rates-pricing/accessImmediately.html','allowed_hosts':['www.fnbnamibia.com.na'],'adapter':'rules','retrieval_fallback':'crawl4ai','rules':[{'kind':'table','table_header':['Amount','Nominal','Effective'],'row_label':'N\\$0\\ \\-\\ 4\\ 999','label_column':0,'column':1,'record_id':'e615d6cec91d603b'}]}
  raw=b'<table><tr><th>Sales and Services</th><th>Tellers</th></tr></table>'
  with mock.patch('extractor.fetch_publication', return_value=(src,raw,src['url'],{'retrieval_method':'direct_http'})), mock.patch('extractor.retrieve_crawl4ai', side_effect=ReviewRequired('renderer failed')):
   with self.assertRaises(ReviewRequired):extract(src)
 def test_direct_success_does_not_invoke_crawl4ai(self):
  src={'id':'src-5882f5135bf84b65','target':'Namibia','url':'https://www.fnbnamibia.com.na/rates-pricing/accessImmediately.html','allowed_hosts':['www.fnbnamibia.com.na'],'adapter':'rules','retrieval_fallback':'crawl4ai','rules':[{'kind':'table','table_header':['Amount','Nominal','Effective'],'row_label':'N\\$0\\ \\-\\ 4\\ 999','label_column':0,'column':1,'record_id':'e615d6cec91d603b'}]}
  raw=b'<table><tr><th>Amount</th><th>Nominal</th><th>Effective</th></tr><tr><td>N$0 - 4 999</td><td>2.31%</td><td>2.33%</td></tr></table>'
  with mock.patch('extractor.fetch_publication', return_value=(src,raw,src['url'],{'retrieval_method':'direct_http'})), mock.patch('extractor.retrieve_crawl4ai') as crawl:
   result=extract(src)
   self.assertEqual(result['status'],'ok');self.assertEqual(result['retrieval_method'],'direct_http');crawl.assert_not_called()

 def test_mauritius_savings_rules_use_exact_live_record_ids(self):
  cases=[
   ({'id':'src-826359a55d1fbe8b','target':'Mauritius','url':'https://abcbanking.mu/fees-and-charges/','rules':[{'kind':'table','table_header':['','Individuals','Corporate','Others'],'row_label':'ABC\\ Savings','label_column':0,'column':1,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?\s*payable\s+half\s+yearly','record_id':'3df58c69d7ff81bc'}]}, b'<table><tr><th></th><th>Individuals</th><th>Corporate</th><th>Others</th></tr><tr><td>ABC Savings</td><td>3.15% p.a payable half yearly</td><td>N/A</td><td>N/A</td></tr></table>', '3df58c69d7ff81bc'),
   ({'id':'src-011547757936daae','target':'Mauritius','url':'https://www.bcpbank.mu/content/bank-mauritius-template-fees-charges-and-commissions','rules':[{'kind':'table','table_header':['','Individuals','Corporates','Self-employed / SMEs'],'row_label':'Savings','label_column':0,'column':1,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)','record_id':'828fd3846c2bd65d'}]}, b'<table><tr><th></th><th>Individuals</th><th>Corporates</th><th>Self-employed / SMEs</th></tr><tr><td>Savings</td><td>3.25%</td><td>n/a</td><td>3.25%</td></tr></table>', '828fd3846c2bd65d'),
   ({'id':'src-6db4c18f67255270','target':'Mauritius','url':'https://www.afrasiabank.com/en/about/rates','rules':[{'kind':'table','table_header':['A) Interest Rates','Individuals','Corporates','Others'],'row_label':'Savings','label_column':0,'column':1,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?','record_id':'6608e6e916f9b6b9'}]}, b'<table><tr><th>A) Interest Rates</th><th>Individuals</th><th>Corporates</th><th>Others</th></tr><tr><td>Savings</td><td>3.65% p.a</td><td>n/a</td><td>n/a</td></tr></table>', '6608e6e916f9b6b9')]
  for src,raw,record_id in cases:
   with self.subTest(src=src['id']):
    records=parse_rules(src,raw)
    self.assertEqual(records[0]['id'],record_id);self.assertEqual(records[0]['source_url'],src['url'])
 def test_mauritius_savings_rules_reject_wrong_product_and_duplicates(self):
  src={'id':'src-011547757936daae','target':'Mauritius','url':'https://www.bcpbank.mu/content/bank-mauritius-template-fees-charges-and-commissions','rules':[{'kind':'table','table_header':['','Individuals','Corporates','Self-employed / SMEs'],'row_label':'Savings','label_column':0,'column':1,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)','record_id':'828fd3846c2bd65d'}]}
  wrong=b'<table><tr><th></th><th>Individuals</th><th>Corporates</th><th>Self-employed / SMEs</th></tr><tr><td>Term (MUR)</td><td>3.70% - 5.05%</td><td>Upon request</td><td>Upon request</td></tr></table>'
  duplicate=b'<table><tr><th></th><th>Individuals</th><th>Corporates</th><th>Self-employed / SMEs</th></tr><tr><td>Savings</td><td>3.25%</td><td>n/a</td><td>3.25%</td></tr><tr><td>Savings</td><td>3.50%</td><td>n/a</td><td>3.50%</td></tr></table>'
  malformed=b'<table><tr><th></th><th>Individuals</th><th>Corporates</th><th>Self-employed / SMEs</th></tr><tr><td>Savings</td><td>Upon request</td><td>n/a</td><td>3.25%</td></tr></table>'
  for raw in [wrong,duplicate,malformed]:
   with self.assertRaises(ReviewRequired):parse_rules(src,raw)
 def test_cfg_passbook_regex_maps_only_regulated_savings_sentence(self):
  src={'id':'src-981fab275d20596e','target':'Morocco','url':'https://www.cfgbank.com/particuliers/notre-offre/epargne/le-compte-sur-carnet/','rules':[{'kind':'regex','pattern':r'Taux\s+minimum\s+.{0,40}?\s+en\s+vigueur\s+de\s+(?P<rate>\d+(?:[,.]\d+)?\s*%)\s+brut','record_id':'bf05d7499c04c4bf'}]}
  raw='Compte sur carnet. Rémunération: Taux minimum réglementaire en vigueur de 1,61 % brut (du 01/01 au 30/06/2026). Fiscalité 30%.'.encode('utf-8')
  records=parse_rules(src,raw)
  self.assertEqual(records[0]['id'],'bf05d7499c04c4bf');self.assertAlmostEqual(records[0]['rate'],.0161)
  with self.assertRaises(ReviewRequired):parse_rules(src,b'Compte sur carnet. Fiscalite 30%.')


 def test_phase8_non_mauritius_regex_rules_map_exact_live_records(self):
  bicici={'id':'src-03f5f03cf8322000','target':'Cote Divoire','url':'https://www.bicici.ci/special-epargne','rules':[{'kind':'regex','pattern':r'Un\s+taux\s+r\S+mun\S+rateur\s+de\s+(?P<rate>\d+(?:[,.]\d+)?\s*%)\s+par\s+an\s+jusqu.{0,80}?FCFA\s+de\s+d\S+p\S+t','record_id':'77c79ab8942a9190'}]}
  bicici_raw='Compte spécial épargne. Un taux rémunérateur de 3,5% par an jusqu’à 10 000 000 FCFA de dépôt.'.encode('utf-8')
  cbao={'id':'src-85fc6b655cb3e5ad','target':'Senegal','url':'https://cbaobank.com/sites/default/files/CONDITIONS%20GENERALES%20CBAO%20SN%20Juin%202026.pdf','rules':[{'kind':'regex','pattern':r'2\.1\.8\.4\s+Int\S+r\S+ts\s+cr\S+diteurs\s+pour\s+les\s+comptes\s+d[\S\s]{0,20}?pargne\s+simple\s+(?P<rate>\d+(?:[,.]\d+)?\s*%)\s+l[\S\s]{0,5}?an','record_id':'ca8ccb1104402be2'}]}
  cbao_raw="2.1.8.4 Intérêts créditeurs pour les comptes d'épargne simple 3,5% l'an".encode('utf-8')
  for src,raw,record_id in [(bicici,bicici_raw,'77c79ab8942a9190'),(cbao,cbao_raw,'ca8ccb1104402be2')]:
   with self.subTest(src=src['id']):
    records=parse_rules(src,raw)
    self.assertEqual(records[0]['id'],record_id);self.assertEqual(records[0]['source_url'],src['url'])
 def test_phase8_non_mauritius_rules_reject_wrong_product_currency_and_duplicates(self):
  bicici={'id':'src-03f5f03cf8322000','target':'Cote Divoire','url':'https://www.bicici.ci/special-epargne','rules':[{'kind':'regex','pattern':r'Un\s+taux\s+r\S+mun\S+rateur\s+de\s+(?P<rate>\d+(?:[,.]\d+)?\s*%)\s+par\s+an\s+jusqu.{0,80}?FCFA\s+de\s+d\S+p\S+t','record_id':'77c79ab8942a9190'}]}
  wrong_product='Un taux rémunérateur de 3,5% par an pour dépôt à terme FCFA de dépôt.'.encode('utf-8')
  wrong_currency='Un taux rémunérateur de 3,5% par an jusqu’à 10 000 000 USD de dépôt.'.encode('utf-8')
  duplicate=('Un taux rémunérateur de 3,5% par an jusqu’à 10 000 000 FCFA de dépôt. '*2).encode('utf-8')
  malformed='Un taux rémunérateur de négociable par an jusqu’à 10 000 000 FCFA de dépôt.'.encode('utf-8')
  for raw in [wrong_product,wrong_currency,duplicate,malformed,b'<table><tr><td>Fees</td><td>3.5%</td></tr></table>']:
   with self.assertRaises(ReviewRequired):parse_rules(bicici,raw)
 def test_phase8_sbm_and_bank_one_rules_map_exact_live_records(self):
  sbm={'id':'src-cd0ea2cb49049d0a','target':'Mauritius','url':'https://banking.sbmgroup.mu/individual/interest-rates','rules':[{'kind':'table','row_label':r'Savings\ Account','label_column':0,'column':1,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?','record_id':'c97791493abc9fdd'},{'kind':'table','table_header':['INTEREST RATES ON MUR TERM DEPOSITS – EFFECTIVE 05 JUNE 2026 (Applicable for individual customers only)'],'row_label':r'12\ Months','label_column':0,'column':1,'value_pattern':r'.*\((?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?\)','record_id':'1d4a911081bbbca9'}]}


  sbm_raw = (


    '<table>'
    '<tr><th>INTEREST RATES ON SAVINGS/CURRENT ACCOUNTS &ndash; EFFECTIVE 05 JUNE 2026</th></tr>'
    '<tr><td>Savings Account</td><td>3.35% p.a.</td></tr>'
    '</table>'
    '<table>'
    '<tr><th>INTEREST RATES ON MUR TERM DEPOSITS &ndash; EFFECTIVE 05 JUNE 2026 (Applicable for individual customers only)</th></tr>'
    '<tr><td>12 Months</td><td>0.20% over Savings Rate presently being 3.35% p.a (3.55% p.a)</td><td>Half Yearly</td></tr>'
    '</table>'
    ).encode('utf-8')  


  records=parse_rules(sbm,sbm_raw)
  self.assertEqual([r['id'] for r in records],['c97791493abc9fdd','1d4a911081bbbca9'])
  bank_one={'id':'src-e0c3794479e44377','target':'Mauritius','url':'https://bankone.mu/en/tarrifs/','rules':[{'kind':'regex','pattern':r'Savings\s+(?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?\s+on\s+balance\s+between\s+Rs\s*10,000\s+and\s+Rs\s*1,000,000','record_id':'50b2f0241b37b51c'},{'kind':'regex','pattern':r'on\s+balance\s+between\s+Rs\s*10,000\s+and\s+Rs\s*1,000,000\s+(?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?\s+on\s+balance\s+between\s+Rs\s*1,000,000\s+and\s+Rs\s*2,000,000','record_id':'50b2f0241b37b51c-e82cfddd'},{'kind':'regex','pattern':r'on\s+balance\s+between\s+Rs\s*1,000,000\s+and\s+Rs\s*2,000,000\s+(?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?\s+on\s+balance\s+above\s+Rs\s*2,000,000','record_id':'50b2f0241b37b51c-d84bf1c2'},{'kind':'regex','pattern':r'Moneytree\s+(?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?\s*\(BSR\s*\+\s*0\.05%\s+on\s+balance\s+on\s+excess\s+of\s+Rs1m\)','record_id':'0ba341b1bc65072e'},{'kind':'regex','pattern':r'POP\s+Save\s+(?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?','record_id':'0ba341b1bc65072e-dad7c69c'}]}
  bank_one_raw=b'Savings 3.20% p.a. on balance between Rs 10,000 and Rs 1,000,000 3.25% p.a. on balance between Rs 1,000,000 and Rs 2,000,000 3.40% p.a. on balance above Rs 2,000,000 Moneytree 3.25% p.a (BSR + 0.05% on balance on excess of Rs1m) POP Save 3.30% p.a.'
  records=parse_rules(bank_one,bank_one_raw)
  self.assertEqual([r['id'] for r in records],['50b2f0241b37b51c','50b2f0241b37b51c-e82cfddd','50b2f0241b37b51c-d84bf1c2','0ba341b1bc65072e','0ba341b1bc65072e-dad7c69c'])
 def test_phase8_table_and_regex_rules_fail_safely(self):
  sbm={'id':'src-cd0ea2cb49049d0a','target':'Mauritius','url':'https://banking.sbmgroup.mu/individual/interest-rates','rules':[{'kind':'table','row_label':r'Savings\ Account','label_column':0,'column':1,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)\s*p\.?a\.?','record_id':'c97791493abc9fdd'}]}
  for raw in ['<table><tr><th>INTEREST RATES ON SAVINGS/CURRENT ACCOUNTS – EFFECTIVE 05 JUNE 2026</th></tr><tr><td>Savings Account</td><td>negotiable</td></tr></table>'.encode('utf-8'),'<table><tr><th>INTEREST RATES ON SAVINGS/CURRENT ACCOUNTS – EFFECTIVE 05 JUNE 2026</th></tr><tr><td>Savings Account</td><td>3.35% p.a.</td></tr><tr><td>Savings Account</td><td>3.40% p.a.</td></tr></table>'.encode('utf-8')]:
   with self.assertRaises(ReviewRequired):parse_rules(sbm,raw)

 def test_phase9_mcb_rules_map_exact_live_records(self):
  mcb={'id':'src-a866ecbbd99927df','target':'Mauritius','url':'https://mcb.mu/rates-fees','rules':[{'kind':'regex','pattern':r'Savings\s+rate\s+(?P<rate>\d+(?:\.\d+)?\s*%)\s*p\.?a\s+Effective\s+as\s+from\s+\d{2}\s+June\s+2026','record_id':'cbed3baca38afbf3'},{'kind':'table','table_header':['','7 Days','3 Months'],'row_label':r'Rates\ p\.a\.:','label_column':0,'column':2,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)','record_id':'d4736feb26068a47'},{'kind':'table','row_label':'12','label_column':0,'column':1,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)','record_id':'a9fc59997c16ed6a'},{'kind':'table','row_label':'12','label_column':0,'column':2,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)','record_id':'a9fc59997c16ed6a-bbec7dd4'},{'kind':'table','row_label':'12','label_column':0,'column':3,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)','record_id':'a9fc59997c16ed6a-4aff2e78'},{'kind':'table','row_label':'12','label_column':0,'column':4,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)','record_id':'a9fc59997c16ed6a-68c9cb98'}]}
  raw=('Savings rate 3.35 % p.a Effective as from 01 June 2026 <table><tr><th></th><th>7 Days</th><th>3 Months</th></tr><tr><td>Rates p.a.:</td><td>1.25%</td><td>1.75%</td></tr></table><table><tr><td>12</td><td>3.48%</td><td>3.49%</td><td>3.53%</td><td>3.53%</td></tr></table>').encode('utf-8')
  records=parse_rules(mcb,raw)
  self.assertEqual([r['id'] for r in records],['cbed3baca38afbf3','d4736feb26068a47','a9fc59997c16ed6a','a9fc59997c16ed6a-bbec7dd4','a9fc59997c16ed6a-4aff2e78','a9fc59997c16ed6a-68c9cb98'])
 def test_phase9_mcb_rules_fail_safely(self):
  mcb={'id':'src-a866ecbbd99927df','target':'Mauritius','url':'https://mcb.mu/rates-fees','rules':[{'kind':'table','table_header':['','7 Days','3 Months'],'row_label':r'Rates\ p\.a\.:','label_column':0,'column':2,'value_pattern':r'(?P<rate>\d+(?:\.\d+)?%)','record_id':'d4736feb26068a47'}]}
  for raw in [b'<table><tr><th></th><th>7 Days</th><th>6 Months</th></tr><tr><td>Rates p.a.:</td><td>1.25%</td><td>1.75%</td></tr></table>',b'<table><tr><th></th><th>7 Days</th><th>3 Months</th></tr><tr><td>Rates p.a.:</td><td>1.25%</td><td>negotiable</td></tr></table>',b'<table><tr><th></th><th>7 Days</th><th>3 Months</th></tr><tr><td>Rates p.a.:</td><td>1.25%</td><td>1.75%</td></tr><tr><td>Rates p.a.:</td><td>1.30%</td><td>1.80%</td></tr></table>']:
   with self.assertRaises(ReviewRequired):parse_rules(mcb,raw)
 def test_phase9_uba_zambia_rules_map_exact_live_records(self):
  uba={'id':'src-580ac56e8bbdabec','target':'Zambia','url':'https://www.ubazambia.com/personal-banking/accounts/uba-savings-account/','rules':[{'kind':'regex','pattern':r'UBA\s+Kiddies\s+Account[\s\S]{0,500}?Benefits[\s\S]{0,80}?(?P<rate>\d+\s*%)\s+interest\s+per\s+annum\s+paid\s+quarterly','record_id':'7ea55f7bd0dc0e60'},{'kind':'regex','pattern':r'UBA\s+Teens\s+Account[\s\S]{0,500}?Benefits[\s\S]{0,80}?(?P<rate>\d+\s*%)\s+interest\s+per\s+annum\s+paid\s+quarterly','record_id':'7ea55f7bd0dc0e60-1ad277ee'},{'kind':'regex','pattern':r'UBA\s+NextGen\s+Account[\s\S]{0,500}?Benefits[\s\S]{0,80}?(?P<rate>\d+\s*%)\s+interest\s+per\s+annum\s+paid\s+quarterly','record_id':'7ea55f7bd0dc0e60-eabe7eb9'},{'kind':'regex','pattern':r'UBA\s+Freedom\s+Account[\s\S]{0,500}?Benefits[\s\S]{0,80}?(?P<rate>\d+\s*%)\s+interest\s+per\s+annum\s+paid\s+quarterly','record_id':'7ea55f7bd0dc0e60-b22151da'},{'kind':'regex','pattern':r'UBA\s+Bumper\s+Account[\s\S]{0,500}?Benefits[\s\S]{0,80}?(?P<rate>\d+\s*%)\s+interest\s+per\s+annum\s+paid\s+quarterly','record_id':'e9c8f9311512100a'}]}
  raw=('UBA Kiddies Account Benefits •4 % interest per annum paid quarterly Features. UBA Teens Account Benefits •4 % interest per annum paid quarterly Features. UBA NextGen Account Benefits •4 % interest per annum paid quarterly Features. UBA Freedom Account Benefits • 3% Interest per annum paid quarterly Features. UBA Bumper Account Benefits • 5 % interest per annum paid quarterly Features.').encode('utf-8')
  records=parse_rules(uba,raw)
  self.assertEqual([r['id'] for r in records],['7ea55f7bd0dc0e60','7ea55f7bd0dc0e60-1ad277ee','7ea55f7bd0dc0e60-eabe7eb9','7ea55f7bd0dc0e60-b22151da','e9c8f9311512100a'])
 def test_phase9_uba_zambia_rules_reject_wrong_or_ambiguous_product(self):
  uba={'id':'src-580ac56e8bbdabec','target':'Zambia','url':'https://www.ubazambia.com/personal-banking/accounts/uba-savings-account/','rules':[{'kind':'regex','pattern':r'UBA\s+Kiddies\s+Account[\s\S]{0,500}?Benefits[\s\S]{0,80}?(?P<rate>\d+\s*%)\s+interest\s+per\s+annum\s+paid\s+quarterly','record_id':'7ea55f7bd0dc0e60'}]}
  wrong=b'UBA Teens Account Benefits \xe2\x80\xa24 % interest per annum paid quarterly Features.'
  duplicate=('UBA Kiddies Account Benefits •4 % interest per annum paid quarterly. '*2).encode('utf-8')
  malformed='UBA Kiddies Account Benefits • negotiable interest per annum paid quarterly.'.encode('utf-8')
  unrelated=b'<table><tr><td>Fees</td><td>4%</td></tr></table>'
  for raw in [wrong,duplicate,malformed,unrelated]:
   with self.assertRaises(ReviewRequired):parse_rules(uba,raw)

 def test_phase8_source_rules_do_not_store_current_rates(self):
  import json
  from pathlib import Path
  sources=json.loads(Path('sources.json').read_text(encoding='utf-8'))
  for sid in ['src-03f5f03cf8322000','src-85fc6b655cb3e5ad','src-cd0ea2cb49049d0a','src-e0c3794479e44377','src-a866ecbbd99927df','src-580ac56e8bbdabec']:
   src=next(s for s in sources if s['id']==sid)
   for rule in src['rules']:
    self.assertNotIn('rate',rule)
    self.assertIn('record_id',rule)


 def test_bceao_country_parser_uses_exact_country_rows(self):
  raw=b"""Monthly Statistical Bulletin - July 2026
Table 2.2.2.4.1 : Lending rates according to the type of borrower (%)
Cote d'Ivoire 8.45 7.34 6.72 9.86 6.27 6.13 7.09 7.14 8.47 5.43 5.12 4.91 6.33 6.35
Senegal 6.39 12.00 5.68 5.57 8.04 8.17 7.53 7.79 6.13 6.24 6.03
Table 2.2.2.4.2 : Average lending rates according to loan purpose (%)
Table 2.2.2.4.3 : Average deposit rates by type of depositor (%)
Cote d'Ivoire 6.07 5.63 5.27 5.35 4.25 4.24 4.90 4.77 4.66 4.15 5.48 5.53 4.61 4.45
Senegal 5.90 5.26 4.20 5.31 5.80 5.73 5.90 5.92 3.50 5.87 7.10 5.86 5.50 5.76
Source : BCEAO."""
  sen={'id':'cb-senegal','country':'Senegal','target':'Senegal CB data','url':'https://www.bceao.int/bulletin.pdf','scope':'BCEAO','bceao_country_label':'Senegal'}
  ci={'id':'cb-cote-divoire','country':'Cote Divoire','target':'Cote Divoire CB data','url':'https://www.bceao.int/bulletin.pdf','scope':'BCEAO','bceao_country_label':"Cote d'Ivoire"}
  sen_records=parse_bceao_country(sen,raw);ci_records=parse_bceao_country(ci,raw)
  self.assertEqual([r['id'] for r in sen_records],['cb-senegal:avg_lending_combined','cb-senegal:avg_deposit_combined'])
  self.assertAlmostEqual(sen_records[0]['value'],.0603);self.assertAlmostEqual(sen_records[1]['value'],.0576)
  self.assertAlmostEqual(ci_records[0]['value'],.0635);self.assertAlmostEqual(ci_records[1]['value'],.0445)
  self.assertEqual(sen_records[0]['period'],'July 2026')

 def test_zambia_api_parser_uses_latest_official_records(self):
  src={'id':'cb-zambia','target':'Zambia CB data','url':'https://www.boz.zm/markets-securities/overnight-interbank-interest-rates','scope':'Official Bank of Zambia overnight market rates'}
  payload={
   'interbank':[{'overnight_interest_rate_date':'<time datetime="2026-10-01T13:30:00Z">1 Oct 2026 - 15:30</time>','overnight_interbank_interest_rate':'10.7500','overnight_interest_rate_description':'<p>Overnight Interbank Interest Rate</p>'}],
   'olf':[{'overnight_lending_facility_rate_date':'<time datetime="2026-09-30T12:00:00Z">30 Sep 2026 - 12:00</time>','overnight_lending_facility_rate':'22.25','overnight_lending_facility_rate_description':'Overnight Lending Facility Rate'}]
  }
  import json
  records=parse_zambia_api(src,json.dumps(payload).encode())
  self.assertEqual([r['id'] for r in records],['cb-zambia:overnight_interbank','cb-zambia:overnight_lending_facility'])
  self.assertAlmostEqual(records[0]['value'],.1075);self.assertAlmostEqual(records[1]['value'],.2225)
  self.assertEqual(records[0]['source_url'],src['url'])
 def test_central_rules_parse_policy_rate(self):
  src={'id':'cb-seychelles','target':'Seychelles CB data','url':'https://www.cbs.sc/','scope':'Central-bank published aggregate or policy data','rules':[{'kind':'regex','key':'mpr','metric':'Monetary Policy Rate','pattern':r'Monetary\s+Policy\s+Rate\s*:\s*(?:<[^>]+>\s*)?(?P<value>\d+(?:\.\d+)?%)','unit':'%'}]}
  raw=b'<h5>Monetary Policy Rate : <a>1.75%</a></h5>'
  records=parse_central_rules(src,raw)
  self.assertEqual(records[0]['id'],'cb-seychelles:mpr');self.assertEqual(records[0]['target'],'Seychelles CB data');self.assertAlmostEqual(records[0]['value'],.0175);self.assertEqual(records[0]['source_url'],src['url'])
 def test_namibia_repo_sentence_avoids_duplicate_headline(self):
  src={'id':'cb-namibia','target':'Namibia CB data','url':'https://www.bon.com.na/','rules':[{'kind':'regex','key':'repo','metric':'Repo Rate','pattern':r'decided\s+to\s+maintain\s+the\s+Repo\s+rate\s+at\s+(?P<value>\d+(?:\.\d+)?)\s*percent','unit':'%'}]}
  raw=b'Repo Rate Maintained at 6.75 Percent. The MPC unanimously decided to maintain the Repo rate at 6.75 percent. The MPC unanimously decided to maintain the Repo rate at 6.75 percent.'
  records=parse_central_rules(src,raw)
  self.assertEqual(records[0]['id'],'cb-namibia:repo');self.assertAlmostEqual(records[0]['value'],.0675)
 def test_central_rules_reject_duplicate_or_qualified_values(self):
  src={'id':'cb-test','target':'Test CB data','url':'https://bank.example/','rules':[{'kind':'regex','key':'policy','metric':'Policy Rate','pattern':r'Policy\s+Rate\s+(?P<value>\d+(?:\.\d+)?%)'}]}
  with self.assertRaises(ReviewRequired):parse_central_rules(src,b'Policy Rate 5% Policy Rate 6%')
  src['rules'][0]['pattern']=r'Policy\s+Rate\s+(?P<value>Up to \d+(?:\.\d+)?%)'
  with self.assertRaises(ReviewRequired):parse_central_rules(src,b'Policy Rate Up to 5%')

 def test_uganda_central_rules_extract_bou_benchmarks_without_hardcoded_values(self):
  import json
  from pathlib import Path
  sources=json.loads(Path('sources.json').read_text(encoding='utf-8'))
  src=next(s for s in sources if s['id']=='cb-68a0f1d7cecdc13b')
  raw=("""
  Monetary Policy Decision: The Monetary Policy Committee maintained the Central Bank Rate at 9.75 % in May 2026.
  The Bank of Uganda increased the Cash Reserve Requirement from 9.5% to 11%.
  Annual headline inflation rose to 3.0 % from 2.8% in March 2026, while core inflation increased to 3.0% from 2.9%.
  Money market rates stayed within the CBR band, with the overnight interbank rate and the 7-day weighted average rate rising by 17 basis points and 30 basis points to 10.09 % and 10.5% in April 2026, respectively.
  Q-Apr'26 10.3 11.3 12.3 13.4 13.7 14.5 15.5 15.9 16.0
  The weighted average shilling lending rate fell to 18.65% in the three months to March 2026 compared to 18.71% in the three months to December 2025.
  The lending rate on foreign currency denominated loans fell to 6.98% compared to 7.96% over the same period.
  """).encode('utf-8')
  records=parse_central_rules(src,raw)
  values={r['metric']:r['value'] for r in records}
  self.assertAlmostEqual(values['Central Bank Rate (CBR)'],.0975)
  self.assertAlmostEqual(values['Cash Reserve Requirement (CRR)'],.11)
  self.assertAlmostEqual(values['Headline Inflation Rate'],.03)
  self.assertAlmostEqual(values['Core Inflation Rate'],.03)
  self.assertAlmostEqual(values['Overnight Interbank Cash Rate'],.1009)
  self.assertAlmostEqual(values['7-Day Interbank Cash Market Rate'],.105)
  self.assertAlmostEqual(values['Treasury Bills (91-Day Yield)'],.103)
  self.assertAlmostEqual(values['Treasury Bills (182-Day Yield)'],.113)
  self.assertAlmostEqual(values['Treasury Bills (364-Day Yield)'],.123)
  self.assertAlmostEqual(values['Commercial Bank Weighted Lending Rate (UGX)'],.1865)
  self.assertAlmostEqual(values['Commercial Bank Weighted Lending Rate (Foreign Currency)'],.0698)
  self.assertTrue(all(r['source_url']==src['url'] for r in records))
  for rule in src['rules']:
   self.assertNotIn('rate',rule)
   self.assertNotIn('final_value',rule)

 def test_uganda_central_rules_fail_safely_when_publication_wording_changes(self):
  import json
  from pathlib import Path
  sources=json.loads(Path('sources.json').read_text(encoding='utf-8'))
  src=next(s for s in sources if s['id']=='cb-68a0f1d7cecdc13b')
  with self.assertRaises(ReviewRequired):
   parse_central_rules(src,b'Bank of Uganda Monetary Policy Report. The policy stance is unchanged but no exact numeric benchmark table is present.')

 def test_central_source_targets_are_standardized_for_all_countries(self):
  import json
  from pathlib import Path
  sources=json.loads(Path('sources.json').read_text(encoding='utf-8'))
  countries={s['country'] for s in sources if s.get('group')=='central'}
  self.assertEqual(countries,{'Mauritius','Seychelles','Ghana','Nigeria','Kenya','South Africa','Tanzania','Cote Divoire','Senegal','Egypt','Morocco','Botswana','Namibia','Uganda','Zambia'})
  for src in [s for s in sources if s.get('group')=='central']:
   self.assertEqual(src['target'],src['country']+' CB data')

 def test_units(self):
  import json
  s={'id':'cb-test','target':'Test','url':'https://bank.example/'}
  base={'Name':'SARB Policy Rate','SectionName':'Money Market Rates','TimeseriesCode':'A','Date':'2026-09-10','Value':7}
  gold=dict(base,Name='US Dollar',SectionId='CMRLGP',SectionName='London gold price',Value=4405.7,TimeseriesCode='B')
  out=parse_sarb(s,json.dumps([base,gold]).encode());self.assertEqual(out[0]['value'],.07);self.assertEqual(out[1]['value'],4405.7);self.assertEqual(out[1]['unit'],'USD per fine ounce')
if __name__=='__main__':unittest.main()


