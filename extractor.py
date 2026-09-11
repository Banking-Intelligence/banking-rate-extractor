"""Public-source extraction service. No bank credentials or customer data are used."""
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from lxml import html
from pypdf import PdfReader

MAX_BYTES = 20 * 1024 * 1024
CONFIG = Path(__file__).with_name('sources.json')

class ReviewRequired(Exception):
    pass

def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()

def rate(value):
    """Only single percentages and two-ended ranges. Returns decimal Excel values."""
    s = clean(value).replace('−','-').replace('–','-').replace('—','-')
    s = re.sub(r'(?<=\d),(?=\d)', '.', s)
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*%?\s*(?:-|to|à)\s*(\d+(?:\.\d+)?)\s*%(?:\s*(?:p\.?a\.?|per annum))?',s,re.I)
    if m:
        lo,hi = [float(x)/100 for x in m.groups()]
        if lo > hi: raise ReviewRequired('Reversed published range')
        return {'rate':(lo+hi)/2,'low':lo,'high':hi,'method':'Calculated midpoint','raw':s}
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*%(?:\s*(?:p\.?a\.?|per annum))?',s,re.I)
    if m:
        n=float(m.group(1))/100
        return {'rate':n,'low':n,'high':n,'method':'Published rate','raw':s}
    raise ReviewRequired('Rate is missing, qualified, linked, or not a simple published range')

def tables(raw):
    doc=html.fromstring(raw)
    return [[[clean(c.text_content()) for c in r.xpath('./th|./td')] for r in t.xpath('.//tr')] for t in doc.xpath('//table')]

def text_content(raw):
    if raw.startswith(b'%PDF'):
        return '\n'.join('[PAGE %d]\n%s'%(i+1,p.extract_text() or '') for i,p in enumerate(PdfReader(io.BytesIO(raw)).pages[:60]))
    doc=html.fromstring(raw)
    for e in doc.xpath('//script|//style'):e.drop_tree()
    return clean(doc.text_content())

def allowed(url,source):
    p=urllib.parse.urlparse(url)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443):return False
    return (p.hostname or '').lower() in source['allowed_hosts']

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,source):self.source=source
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl,self.source):raise ReviewRequired('Redirect left approved publisher domains')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url,source):
    if not allowed(url,source):raise ReviewRequired('URL is not an approved HTTPS publisher URL')
    req=urllib.request.Request(url,headers={'User-Agent':'BankingIntelligence/1.0 (public tariff research)','Accept':'text/html,application/pdf,application/json,*/*'})
    with urllib.request.build_opener(SafeRedirect(source)).open(req,timeout=25) as r:
        body=r.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES:raise ReviewRequired('Publication exceeds extraction size limit')
        final=r.url
    if re.search(rb'(?i)<title>\s*(?:just a moment|request rejected|access denied)',body[:10000]):
        raise ReviewRequired('Publisher requires interactive access')
    return body,final

def observation(source,key,metric,value,period='',unit='%',bank='',notes=''):
    return {'id':source['id']+':'+key,'target':source['target'],'metric':metric,'value':value,
            'unit':unit,'period':period,'bank':bank,'scope':source.get('scope',''),
            'source_url':source['url'],'notes':notes,'status':'Verified official source'}

def parse_sarb(source,raw):
    data=json.loads(raw); out=[]
    if not isinstance(data,list) or not data:raise ReviewRequired('SARB response is not an indicator array')
    for x in data:
        for k in ('TimeseriesCode','Name','Value','Date','SectionName'):
            if k not in x:raise ReviewRequired('SARB indicator schema changed')
        section=x['SectionName']; name=x['Name']; percent=bool(re.search('money market|capital market',section,re.I))
        unit='%' if percent else ('Index' if 'effective exchange' in name.lower() else ('ZAR per currency unit' if name.startswith('Rand per') else ('USD per fine ounce' if name=='US Dollar' else 'ZAR per fine ounce') if x.get('SectionId')=='CMRLGP' else section))
        out.append(observation(source,x['TimeseriesCode'],name,float(x['Value'])/(100 if percent else 1),x['Date'],unit,notes=section))
    return out

def parse_kenya(source,raw):
    ts=tables(raw); t=next((t for t in ts if t and 'Asset Finance' in t[0]),None)
    if not t:raise ReviewRequired('Kenya lending table header changed')
    labels=t[0][2:]; bank='';out=[]
    for row in t[1:]:
        if len(row)==1:bank=row[0];continue
        if len(row)!=7 or row[0] not in ('Central Bank Rate (CBR) + Bank Premium (K)','KESONIA + Premium'):continue
        for label,cell in zip(labels,row[1:]):
            m=re.search(r'(\d+(?:\.\d+)?)%',cell); date=re.search(r'(\d{2})/(\d{2})/(\d{4})',cell)
            if not m:continue
            if not date:raise ReviewRequired('Missing per-category Kenya update date')
            period='-'.join((date[3],date[2],date[1]))
            key=hashlib.sha256((bank+'|'+label+'|'+row[0]).encode()).hexdigest()[:16]
            out.append(observation(source,key,label,float(m[1])/100,period,bank=bank,notes=row[0]+'; indicative average, not a customer quote'))
    if len(out)<20:raise ReviewRequired('Unexpectedly small Kenya table')
    return out

def parse_morocco(source,raw):
    ts=tables(raw);out=[];mode=source['adapter']
    if mode=='morocco_term':
        t=next((t for t in ts if t and t[0][0]=='Month'),None)
        if not t or len(t[1])!=3:raise ReviewRequired('Term deposit table changed')
        for i,months in enumerate((6,12),1):
            rr=rate(t[1][i]);out.append(observation(source,str(months),f'{months}-month term deposits weighted average',rr['rate'],t[1][0]))
    elif mode=='morocco_savings':
        t=next((t for t in ts if len(t)>2 and 'Beginning' in t[1]),None)
        if not t or len(t[2])!=3:raise ReviewRequired('Savings table changed')
        row=t[2];out.append(observation(source,'passbook','Regulated passbook savings rate',rate(row[2])['rate'],row[0]+' to '+row[1]))
    else:
        t=next((t for t in ts if any(r and r[0]=='Lending rates' for r in t)),None)
        dates=next((t for t in ts if t and t[0][0]=='Edition'),None)
        if not t or not dates:raise ReviewRequired('Lending table changed')
        period=dates[1][0]
        for row in t[2:]:
            cells=[x for x in row[1:] if re.fullmatch(r'\d+\.\d+',x)]
            if not cells:continue
            out.append(observation(source,hashlib.sha256(row[0].encode()).hexdigest()[:12],row[0],float(cells[-1])/100,period,notes='Published '+dates[1][1]))
    return out

def parse_bom_key(source,raw):
    for t in tables(raw):
        for r in t:
            if len(r)>=2 and re.search(r'\d{4}',r[0]) and re.fullmatch(r'\d+\.\d+',r[1]):
                return [observation(source,'key','Key Rate',float(r[1])/100,r[0])]
    raise ReviewRequired('Mauritius policy table changed')

def parse_rules(source,raw):
    out=[];ts=tables(raw) if not raw.startswith(b'%PDF') else []; text=text_content(raw)
    for rule in source.get('rules',[]):
        if rule['kind']=='table':
            selected=[t for t in ts if not rule.get('table_header') or rule['table_header'] in t]
            label_col=rule.get('label_column',0)
            matches=[r for t in selected for r in t if len(r)>label_col and re.fullmatch(rule['row_label'],r[label_col],re.I)]
            if len(matches)!=1:raise ReviewRequired('Product row is missing or ambiguous: '+rule['row_label'])
            row=matches[0]; idx=rule['column']
            if idx>=len(row):raise ReviewRequired('Rate column changed')
            cell=row[idx]
            if rule.get('value_pattern'):
                m=re.fullmatch(rule['value_pattern'],cell,re.I)
                if not m:raise ReviewRequired('Qualified rate wording changed')
                cell=m.group('rate')
            rr=rate(cell); evidence=' | '.join(row)
        else:
            matches=list(re.finditer(rule['pattern'],text,re.I))
            if len(matches)!=1:raise ReviewRequired('Publication wording changed or is ambiguous')
            rr=rate(matches[0].group('rate'));evidence=matches[0].group(0)
        out.append({'id':rule['record_id'],'target':source['target'],**rr,'source_url':source['url'],
                    'evidence':evidence,'status':'Verified bank source','period':'',
                    'source_id':source['id'],'effective_date':'','published_date':''})
    if not out:raise ReviewRequired('No reviewed product mapping rules for this publication')
    return out

ADAPTERS={'sarb':parse_sarb,'kenya':parse_kenya,'morocco_term':parse_morocco,'morocco_lending':parse_morocco,
          'morocco_savings':parse_morocco,'bom_key':parse_bom_key,'rules':parse_rules}

def extract(source):
    raw,url=fetch(source['url'],source);source=dict(source,url=url)
    if source.get('publication_link_pattern'):
        doc=html.fromstring(raw)
        links=[urllib.parse.urljoin(url,a.get('href')) for a in doc.xpath('//a[@href]') if re.search(source['publication_link_pattern'],a.get('href')+' '+clean(a.text_content()),re.I)]
        links=list(dict.fromkeys(links))
        if not links:raise ReviewRequired('No matching publication on the official index')
        raw,url=fetch(links[0],source);source['url']=url
    fingerprint=hashlib.sha256(raw).hexdigest()
    handler=ADAPTERS.get(source['adapter'])
    if handler:
        records=handler(source,raw)
        if not records:raise ReviewRequired('No usable observations')
        return {'status':'ok','records':records,'source_url':url,'fingerprint':fingerprint}
    txt=text_content(raw)
    lines=txt.splitlines() if '\n' in txt else re.split(r'(?<=[.;])\s+',txt)
    snippets=[l[:1200] for l in lines if re.search(r'interest|deposit|lending|savings|taux',l,re.I) and re.search(r'\d',l)][:30]
    return {'status':'review','records':[],'source_url':url,'fingerprint':fingerprint,
            'message':'Publication retrieved; product/period mapping needs review','evidence':snippets}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,code,data):
        body=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        self.respond(200 if self.path=='/health' else 404,{'status':'ready' if self.path=='/health' else 'not found'})
    def do_POST(self):
        key=os.environ.get('EXTRACTOR_KEY','')
        if not key or not hmac.compare_digest(self.headers.get('X-Banking-Key',''),key):return self.respond(401,{'error':'Unauthorized'})
        if self.path!='/extract':return self.respond(404,{'error':'Not found'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<4096:return self.respond(400,{'error':'Invalid request length'})
            req=json.loads(self.rfile.read(size));sid=req.get('source_id','')
            sources=json.loads(CONFIG.read_text(encoding='utf-8'))
            source=next((s for s in sources if s['id']==sid),None)
            if not source:return self.respond(404,{'error':'Unknown source identifier'})
            result=extract(source);result['checked_at']=dt.datetime.now(dt.timezone.utc).isoformat();self.respond(200,result)
        except Exception as e:self.respond(200,{'status':'review','records':[],'message':str(e)[:500]})

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler).serve_forever()
