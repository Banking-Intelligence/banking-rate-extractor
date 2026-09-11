import unittest, math
from extractor import rate,ReviewRequired,allowed,parse_sarb
class ExtractionTests(unittest.TestCase):
 def test_midpoint(self):
  r=rate('2%–3%');self.assertAlmostEqual(r['rate'],.025);self.assertEqual(r['method'],'Calculated midpoint')
 def test_french_decimal(self):self.assertAlmostEqual(rate('1,75% - 2,00%')['rate'],.01875)
 def test_zero_is_not_missing(self):self.assertEqual(rate('0%')['rate'],0)
 def test_qualifiers_not_guessed(self):
  for v in ['Up to 3%','From 2%','Prime + 2%','Negotiable','N/A','3% - 2%','2% monthly','2.5% / 3.5%']:
   with self.subTest(v=v),self.assertRaises(ReviewRequired):rate(v)
 def test_publisher_allowlist(self):
  s={'allowed_hosts':['bank.example']}
  self.assertTrue(allowed('https://bank.example/rates.pdf',s))
  for u in ['http://bank.example/','https://evil.example/','https://bank.example.evil.test/','https://u:p@bank.example/','https://bank.example:8080/']:
   self.assertFalse(allowed(u,s))
 def test_units(self):
  import json
  s={'id':'cb-test','target':'Test','url':'https://bank.example/'}
  base={'Name':'SARB Policy Rate','SectionName':'Money Market Rates','TimeseriesCode':'A','Date':'2026-09-10','Value':7}
  gold=dict(base,Name='US Dollar',SectionId='CMRLGP',SectionName='London gold price',Value=4405.7,TimeseriesCode='B')
  out=parse_sarb(s,json.dumps([base,gold]).encode());self.assertEqual(out[0]['value'],.07);self.assertEqual(out[1]['value'],4405.7);self.assertEqual(out[1]['unit'],'USD per fine ounce')
if __name__=='__main__':unittest.main()
