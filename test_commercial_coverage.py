"""Synthetic rates test new mappings without pinning today's published values."""
import copy,json,unittest
from unittest.mock import patch,Mock
from pathlib import Path
from extractor import parse_rules,ReviewRequired

class CommercialCoverageTests(unittest.TestCase):
 def source(self,id):
  return next(s for s in json.loads(Path('sources.json').read_text(encoding='utf-8')) if s['id']==id)
 def table(self,header,rows):
  return ('| '+' | '.join(header)+' |\n| '+' | '.join(['---']*len(header))+' |\n'+''.join('| '+' | '.join(r)+' |\n' for r in rows)).encode()
 def access(self,values=None):
  s=self.source('bank-eea41274b759');h=s['rules'][0]['table_header']
  r=['Interest Rate (P.A.)']+['1.23%']*10
  r[8]='Tiered: contact bank'
  if values:r[values[0]]=values[1]
  return s,self.table(h,[r])
 def test_retail_consensus_maps_live_id(self):
  s,b=self.access();r=parse_rules(s,b)[0]
  self.assertEqual(r['id'],'d2e5a105f2ed2b1f');self.assertAlmostEqual(r['rate'],.0123)
  self.assertEqual(r['source_url'],'https://www.accessbankplc.com/Rates-Guide/')
 def test_different_retail_products_stay_review(self):
  s,b=self.access((2,'2.34%'))
  with self.assertRaises(ReviewRequired):parse_rules(s,b)
 def test_missing_malformed_monthly_rate_stays_review(self):
  for value in ['N/A','1.2%%','1.2% monthly','up to 1.2%']:
   s,b=self.access((3,value))
   with self.subTest(value=value),self.assertRaises(ReviewRequired):parse_rules(s,b)
 def test_wrong_header_duplicate_row_rejected(self):
  s,b=self.access()
  for raw in [b.replace(b'Early Savers',b'USD Savers'),b+b]:
   with self.assertRaises(ReviewRequired):parse_rules(s,raw)
 def atlantic(self):
  s=self.source('bank-749c4d4e2cf9')
  rows=[['3 months (new clients)','9.99%','10,000','500,000','end of term']]
  rows += [[f'{n} months','1.1% - 1.3%','10,000','1,500,000','end of term'] for n in [3,6,12]]
  return s,self.table(s['rules'][0]['table_header'],rows)
 def test_regular_tenors_exclude_promotion_and_keep_midpoint(self):
  s,b=self.atlantic();r=parse_rules(s,b)
  self.assertEqual([v['id'] for v in r],[v['record_id'] for v in s['rules']])
  for v in r:self.assertAlmostEqual(v['rate'],.012);self.assertAlmostEqual(v['low'],.011)
 def test_wrong_currency_tenor_duplicates_rejected(self):
  s,b=self.atlantic()
  for raw in [b.replace(b'(NAD)',b'(USD)'),b.replace(b'6 months',b'9 months'),b+b]:
   with self.assertRaises(ReviewRequired):parse_rules(s,raw)
 def test_unrelated_table_cannot_supply_rates(self):
  s,b=self.atlantic()
  with self.assertRaises(ReviewRequired):parse_rules(s,b.replace(b'Interest Rate p.a.(%)',b'Branch hours'))

class EgyptPdfTests(unittest.TestCase):
 def source(self,id):return next(s for s in json.loads(Path("sources.json").read_text(encoding="utf-8")) if s["id"]==id)
 def source_pdf(self):return self.source('bank-5cfa550f9cc9')
 def content(self):
  return ('Term Deposit in foreign currencies\n'
   'From 500 unit till 25,000 unit in foreign currency\n'
   'Currency/Tenor WEEK MONTH 2 MONTHS 3 MONTHS 6 MONTHS YEAR\n'
   'US DOLLAR (USD) 1% 2% 3% 4% 5% 6%\n'
   'More than 25,000 unit till 100,000 unit in foreign currency\n'
   'US DOLLAR (USD) 7% 8% 9% 10% 11% 12%')
 def parse_pdf(self,texts):
  pages=[Mock() for t in texts]
  for page,t in zip(pages,texts):page.extract_text.return_value=t
  with patch('extractor.PdfReader',return_value=Mock(pages=pages)):
   return parse_rules(self.source_pdf(),b'%PDF synthetic fixture')
 def test_exact_usd_year_lower_tier(self):
  r=self.parse_pdf([self.content()])[0]
  self.assertEqual(r['id'],'84fb22a27adbbaee');self.assertAlmostEqual(r['rate'],.06)
  self.assertIn('banquemisr.com',r['source_url']);self.assertIn('500',r['evidence'])
 def test_wrong_currency_tenor_tier_malformed_missing_rejected(self):
  text=self.content()
  bad=[text.replace('US DOLLAR (USD)','EURO'),text.replace('6 MONTHS YEAR','6 MONTHS TWO YEARS'),
   text.replace('From 500 unit','From 900 unit'),text.replace('5% 6%','5% broken'),text.replace('US DOLLAR (USD) 1% 2% 3% 4% 5% 6%','')]
  for t in bad:
   with self.subTest(t=t),self.assertRaises(ReviewRequired):self.parse_pdf([t])
 def test_duplicate_page_or_row_rejected(self):
  t=self.content()
  for pages in [[t,t],[t.replace('More than 25,000','US DOLLAR (USD) 1% 2% 3% 4% 5% 6%\nMore than 25,000')]]:
   with self.assertRaises(ReviewRequired):self.parse_pdf(pages)
 def test_html_and_unrelated_pdf_rejected(self):
  with self.assertRaises(ReviewRequired):parse_rules(self.source_pdf(),b'<html>6%</html>')
  with self.assertRaises(ReviewRequired):self.parse_pdf(['Other bank product 6%'])

class AuditDiscoveryTests(unittest.TestCase):
 def test_discovery_never_authorizes_external_publisher(self):
  from audit_commercial_coverage import publication_links
  raw=b'<a href="/rates">Rates</a><a href="https://evil.example/rates">Rates</a><a href="https://r.jina.ai/https://bank.example/rates">Rates</a>'
  found=publication_links(raw,'https://bank.example/',{'allowed_hosts':['bank.example']})
  self.assertEqual(found,[{'url':'https://bank.example/rates','label':'Rates'}])
 def test_audit_is_read_only_and_percentages_are_not_records(self):
  from audit_commercial_coverage import inspect_source
  source={'id':'bank-test','country':'Nigeria','name':'Test Bank','adapter':'review','url':'https://bank.example/','allowed_hosts':['bank.example']}
  with patch('audit_commercial_coverage.fetch_publication',return_value=(source,b'<p>News: profits grew 40%</p>',source['url'],{'retrieval_method':'direct_http'})):
   result=inspect_source(source)
  self.assertEqual(result['status'],'retrieved');self.assertNotIn('records',result)
  self.assertEqual(result['mapped_record_ids'],[])

class MauBankFormatTests(unittest.TestCase):
 def source(self):return next(s for s in json.loads(Path('sources.json').read_text(encoding='utf-8')) if s['id']=='src-b0673db44f87164a')
 def test_same_identity_in_html_and_jina_plain_text(self):
  for body in [b'<table><tr><td>Savings Rate Household </td><td>1.23% p.a </td></tr><tr><td>Savings Base Rate</td><td>2.34% p.a</td></tr></table>',b'Markdown Content:\nSavings Rate Household 1.23% p.a\nSavings Base Rate 2.34% p.a']:
   r=parse_rules(self.source(),body)[0];self.assertEqual(r['id'],'a025681fd400c0e9');self.assertAlmostEqual(r['rate'],.0123)
 def test_duplicate_wrong_product_and_qualified_rate_rejected(self):
  body=b'Savings Rate Household 1.23% p.a Savings Base Rate 2.34% p.a'
  for raw in [body+body,body.replace(b'Household',b'Corporate'),body.replace(b'1.23%',b'Up to 1.23%')]:
   with self.assertRaises(ReviewRequired):parse_rules(self.source(),raw)

if __name__=='__main__':unittest.main()
