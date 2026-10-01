"""Public-source extraction service. No bank credentials or customer data are used."""
import asyncio
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from lxml import html
from pypdf import PdfReader

MAX_BYTES = 20 * 1024 * 1024
CONFIG = Path(__file__).with_name('sources.json')

class ReviewRequired(Exception):
    def __init__(self, message, metadata=None):
        super().__init__(message)
        self.metadata = metadata or {}


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()

def rate(value):
    """Read a published rate or clear range and return a safe numeric value."""
    """Only single percentages and two-ended ranges. Returns decimal Excel values."""
    s = clean(value).replace('−','-').replace('–','-').replace('—','-').replace('�','-')
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

def markdown_tables(raw):
    text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else str(raw or '')
    groups = []
    current = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('|') and stripped.endswith('|') and stripped.count('|') >= 2:
            cells = [clean(c) for c in stripped.strip('|').split('|')]
            if cells and all(re.fullmatch(r':?-{3,}:?', c.replace(' ', '')) for c in cells):
                continue
            current.append(cells)
        elif current:
            if len(current) > 1:
                groups.append(current)
            current = []
    if current and len(current) > 1:
        groups.append(current)
    return groups

def text_content(raw):
    if raw.startswith(b'%PDF'):
        return '\n'.join('[PAGE %d]\n%s'%(i+1,p.extract_text() or '') for i,p in enumerate(PdfReader(io.BytesIO(raw)).pages[:60]))
    doc=html.fromstring(raw)
    for e in doc.xpath('//script|//style'):e.drop_tree()
    return clean(doc.text_content())

def allowed(url,source):
    """Check that a URL belongs to the official approved publisher domain."""
    p=urllib.parse.urlparse(url)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443):return False
    return (p.hostname or '').lower() in source['allowed_hosts']

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,source):self.source=source
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl,self.source):raise ReviewRequired('Redirect left approved publisher domains')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def retrieval_looks_blocked(body):
    return bool(re.search(rb'(?i)<title>\s*(?:just a moment|request rejected|access denied)', body[:10000]))

def retrieval_failure_is_eligible(exc):
    if isinstance(exc, ReviewRequired):
        return 'interactive access' in str(exc).lower()
    if isinstance(exc, (ssl.SSLError, TimeoutError, socket.timeout, ConnectionError)):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (403, 429, 500, 502, 503, 504)
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, 'reason', exc)
        text = str(reason).lower()
        return isinstance(reason, (ssl.SSLError, TimeoutError, socket.timeout, ConnectionError)) or any(
            marker in text for marker in ('ssl', 'certificate', 'timed out', 'timeout', 'connection reset', 'network is unreachable')
        )
    return False

def read_limited_response(response):
    body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ReviewRequired('Publication exceeds extraction size limit')
    return body

def retrieve_http(url, source):
    """Try the normal official HTTPS request first."""
    if not allowed(url, source):
        raise ReviewRequired('URL is not an approved HTTPS publisher URL')
    req = urllib.request.Request(url, headers={
        'User-Agent': 'BankingIntelligence/1.0 (public tariff research)',
        'Accept': 'text/html,application/pdf,application/json,*/*'
    })
    with urllib.request.build_opener(SafeRedirect(source)).open(req, timeout=25) as r:
        body = read_limited_response(r)
        final = r.url
    if retrieval_looks_blocked(body):
        raise ReviewRequired('Publisher requires interactive access')
    return {'body': body, 'url': final, 'retrieval_method': 'direct_http'}

def retrieve_jina_reader(url, source):
    """Use Jina Reader only as a fallback while keeping the official source URL."""
    if not allowed(url, source):
        raise ReviewRequired('URL is not an approved HTTPS publisher URL')
    reader_url = 'https://r.jina.ai/' + url
    req = urllib.request.Request(reader_url, headers={
        'User-Agent': 'BankingIntelligence/1.0 (public tariff research)',
        'Accept': 'text/plain,text/markdown,*/*'
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        body = read_limited_response(r)
    if not clean(body.decode('utf-8', 'replace')):
        raise ReviewRequired('Jina Reader returned empty content')
    return {'body': body, 'url': url, 'retrieval_method': 'jina_reader'}

def crawl4ai_enabled(source):
    return source.get('retrieval_fallback') == 'crawl4ai'

def retrieve_crawl4ai(url, source):
    """Render approved dynamic pages when direct text retrieval is not enough."""
    if not allowed(url, source):
        raise ReviewRequired('URL is not an approved HTTPS publisher URL')

    async def run_browser():
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        browser_config = BrowserConfig(headless=True, browser_type='chromium')
        run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, wait_until='networkidle', page_timeout=90000, delay_before_return_html=3.0)
        async with AsyncWebCrawler(config=browser_config) as crawler:
            return await crawler.arun(url=url, config=run_config)

    try:
        result = asyncio.run(run_browser())
    except RuntimeError as exc:
        raise ReviewRequired('Crawl4AI could not run browser renderer: ' + str(exc)[:220])
    except Exception as exc:
        raise ReviewRequired('Crawl4AI retrieval failed: ' + str(exc)[:220])

    if not getattr(result, 'success', False):
        detail = getattr(result, 'error_message', '') or getattr(result, 'status_code', '') or 'unknown renderer failure'
        raise ReviewRequired('Crawl4AI retrieval failed: ' + str(detail)[:220])

    final = getattr(result, 'url', None) or url
    if not allowed(final, source):
        raise ReviewRequired('Crawl4AI final URL left approved publisher domains')

    html_body = getattr(result, 'html', None) or getattr(result, 'cleaned_html', None) or ''
    markdown = getattr(result, 'markdown', None) or ''
    if not isinstance(markdown, str):
        markdown = str(markdown)
    combined = (html_body or '') + '\n' + markdown
    if not clean(combined):
        raise ReviewRequired('Crawl4AI returned empty rendered content')
    body = combined.encode('utf-8', 'replace')
    if len(body) > MAX_BYTES:
        raise ReviewRequired('Rendered publication exceeds extraction size limit')
    return {'body': body, 'url': final, 'retrieval_method': 'crawl4ai', 'render_status': getattr(result, 'status_code', '')}

def retrieve(url, source):
    """Run the safe retrieval chain and report which method produced content."""
    try:
        return retrieve_http(url, source)
    except Exception as exc:
        if not retrieval_failure_is_eligible(exc):
            raise
        try:
            return retrieve_jina_reader(url, source)
        except Exception as fallback_exc:
            raise ReviewRequired('Retrieval failed by direct HTTP and Jina Reader: %s; %s' % (str(exc)[:220], str(fallback_exc)[:220]))

def fetch(url,source):
    retrieved = retrieve(url, source)
    return retrieved['body'], retrieved['url'], {'retrieval_method': retrieved.get('retrieval_method', 'direct_http')}

def observation(source,key,metric,value,period='',unit='%',bank='',notes=''):
    """Build one standard central-bank observation record."""
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



def central_value(text, unit='%'):
    """Parse a central-bank numeric value; percentages are stored as spreadsheet rates."""
    s=clean(text)
    if unit=='%' and re.fullmatch(r'\d+(?:[.,]\d+)?',s):
        return float(s.replace(',','.'))/100,s
    rr=rate(s)
    return rr['rate'], rr['raw']

def parse_central_rules(source,raw):
    """Apply conservative central-bank rules for official macro/rate indicators."""
    out=[];text=text_content(raw);ts=(tables(raw)+markdown_tables(raw)) if not raw.startswith(b'%PDF') else []
    for rule in source.get('rules',[]):
        metric=rule['metric']; key=rule.get('key') or hashlib.sha256(metric.encode()).hexdigest()[:12]
        unit=rule.get('unit','%'); period=rule.get('period',''); notes=rule.get('notes','')
        evidence=''; value_text=''
        if rule['kind']=='regex':
            matches=list(re.finditer(rule['pattern'],text,re.I|re.S))
            if matches:
                unique={}
                value_group=rule.get('value_group','value')
                for match in matches:
                    value_key=clean(match.group(value_group)) if match.groupdict().get(value_group) else clean(match.group(0))
                    evidence_key=re.sub(r'\s+',' ',match.group(0)).strip()
                    unique[(value_key,evidence_key)]=match
                matches=list(unique.values())
            if len(matches)!=1:raise ReviewRequired('Central-bank metric is missing or ambiguous: '+metric)
            match=matches[0]
            value_text=match.group(rule.get('value_group','value'))
            if rule.get('period_group') and match.groupdict().get(rule['period_group']):period=match.group(rule['period_group'])
            evidence=re.sub(r'\s+',' ',match.group(0)).strip()
        elif rule['kind']=='table':
            selected=[t for t in ts if table_header_matches(t, rule.get('table_header'))]
            label_col=rule.get('label_column',0)
            matches=[r for t in selected for r in t if len(r)>label_col and row_label_matches(rule['row_label'],r[label_col])]
            if len(matches)!=1:raise ReviewRequired('Central-bank table row is missing or ambiguous: '+metric)
            row=matches[0]; idx=rule['column']
            if idx>=len(row):raise ReviewRequired('Central-bank value column changed: '+metric)
            value_text=row[idx]
            if rule.get('period_column') is not None and rule['period_column']<len(row):period=row[rule['period_column']]
            evidence=' | '.join(row)
        else:
            raise ReviewRequired('Unsupported central-bank rule kind: '+str(rule.get('kind')))
        value,raw_value=central_value(value_text,unit)
        out.append(observation(source,key,metric,value,period,unit,notes=(notes+'; ' if notes else '')+evidence[:500]))
    if not out:raise ReviewRequired('No reviewed central-bank rules for this publication')
    return out

def parse_bceao_country(source, raw):
    """Extract country-specific BCEAO average lending and deposit rates from the official monthly bulletin PDF."""
    text=text_content(raw)
    period_match=re.search(r'Monthly Statistical Bulletin\s*-\s*([A-Za-z]+\s+\d{4})', text, re.I)
    period=period_match.group(1) if period_match else ''
    country=source.get('bceao_country_label') or source.get('country','')
    labels=[country]
    if 'ivoire' in country.lower():
        labels += [r"C.te d.Ivoire", r"Cote d.Ivoire", r"COTE D.IVOIRE"]
    def section_between(start, end):
        m=re.search(start+r'(?P<body>.*?)'+end, text, re.I|re.S)
        if not m: raise ReviewRequired('BCEAO table section missing: '+start)
        return m.group('body')
    def row_last_value(section, key, name):
        collapsed=clean(section)
        for label in labels:
            m=re.search(label+r'\s+(?P<vals>(?:\d+[.,]\d+\s*){2,})', collapsed, re.I)
            if m:
                nums=re.findall(r'\d+[.,]\d+', m.group('vals'))
                if nums:
                    return observation(source, key, name, float(nums[-1].replace(',','.'))/100, period or 'Latest BCEAO bulletin period', '%', notes=m.group(0)[:500])
        raise ReviewRequired('BCEAO country row missing or ambiguous: '+source.get('country',''))
    lending=section_between(r'Table\s+2\.2\.2\.4\.1\s*:\s*Lending rates according to the type of borrower', r'Table\s+2\.2\.2\.4\.2')
    deposit=section_between(r'Table\s+2\.2\.2\.4\.3\s*:\s*Average deposit rates by type of depositor', r'Source\s*:\s*BCEAO')
    return [
        row_last_value(lending, 'avg_lending_combined', 'Average lending rate — combined'),
        row_last_value(deposit, 'avg_deposit_combined', 'Average deposit rate — combined')
    ]


def parse_zambia_api(source, raw):
    """Use official Bank of Zambia JSON endpoints and take the latest published record from each endpoint."""
    payload=json.loads(raw.decode('utf-8'))
    def first_record(key):
        rows=payload.get(key)
        if not isinstance(rows,list) or not rows:
            raise ReviewRequired('Bank of Zambia API returned no records: '+key)
        return rows[0]
    def time_period(html_text):
        m=re.search(r'datetime=\\?"([^"\\]+)', html_text or '')
        if m: return m.group(1)
        return clean(re.sub(r'<[^>]+>',' ',html_text or ''))
    interbank=first_record('interbank')
    olf=first_record('olf')
    return [
        observation(source,'overnight_interbank','Overnight interbank interest rate',float(interbank['overnight_interbank_interest_rate'])/100,time_period(interbank.get('overnight_interest_rate_date','')),'%',notes=clean(re.sub(r'<[^>]+>',' ',interbank.get('overnight_interest_rate_description','')))),
        observation(source,'overnight_lending_facility','Overnight lending facility rate',float(olf['overnight_lending_facility_rate'])/100,time_period(olf.get('overnight_lending_facility_rate_date','')),'%',notes=clean(re.sub(r'<[^>]+>',' ',olf.get('overnight_lending_facility_rate_description',''))))
    ]


def parse_bom_key(source,raw):
    for t in tables(raw):
        for r in t:
            if len(r)>=2 and re.search(r'\d{4}',r[0]) and re.fullmatch(r'\d+\.\d+',r[1]):
                return [observation(source,'key','Key Rate',float(r[1])/100,r[0])]
    raise ReviewRequired('Mauritius policy table changed')

def table_header_matches(table, expected_header):
    if not expected_header:
        return True
    expected = [re.sub(r'\s+', '', clean(cell)).lower() for cell in expected_header]
    return any([re.sub(r'\s+', '', clean(cell)).lower() for cell in row] == expected for row in table)

def row_label_matches(pattern, value):
    if re.fullmatch(pattern, value, re.I):
        return True
    space_normalized = pattern.replace('\\ ', ' ')
    if space_normalized != pattern and re.fullmatch(space_normalized, value, re.I):
        return True
    literal = pattern.replace('\\ ', ' ').replace('\\(', '(').replace('\\)', ')')
    compact_literal = re.sub(r'\s+', '', clean(literal)).lower()
    compact_value = re.sub(r'\s+', '', clean(value)).lower()
    return bool(compact_literal and compact_literal == compact_value)

def parse_rules(source,raw):
    """Apply deterministic source rules and reject missing or ambiguous matches."""
    out=[];ts=(tables(raw)+markdown_tables(raw)) if not raw.startswith(b'%PDF') else []; text=text_content(raw)
    for rule in source.get('rules',[]):
        if rule['kind']=='table':
            selected=[t for t in ts if table_header_matches(t, rule.get('table_header'))]
            label_col=rule.get('label_column',0)
            matches=[r for t in selected for r in t if len(r)>label_col and row_label_matches(rule['row_label'],r[label_col])]
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
          'morocco_savings':parse_morocco,'bom_key':parse_bom_key,'bceao_country':parse_bceao_country,'zambia_api':parse_zambia_api,'central_rules':parse_central_rules,'rules':parse_rules}

def parse_with_handler(source, raw, url, retrieval_meta):
    """Choose the right parser and attach provenance metadata to every record."""
    fingerprint=hashlib.sha256(raw).hexdigest()
    handler=ADAPTERS.get(source['adapter'])
    if handler:
        try:
            records=handler(source,raw)
            if not records:raise ReviewRequired('No usable observations')
        except ReviewRequired as exc:
            metadata={'source_url':url,'fingerprint':fingerprint,'stage':'parsing',**retrieval_meta}
            metadata.update(getattr(exc,'metadata',{}))
            raise ReviewRequired(str(exc), metadata)
        return {'status':'ok','records':records,'source_url':url,'fingerprint':fingerprint,**retrieval_meta}
    txt=text_content(raw)
    lines=txt.splitlines() if '\n' in txt else re.split(r'(?<=[.;])\s+',txt)
    snippets=[l[:1200] for l in lines if re.search(r'interest|deposit|lending|savings|taux',l,re.I) and re.search(r'\d',l)][:30]
    return {'status':'review','records':[],'source_url':url,'fingerprint':fingerprint,
            'message':'Publication retrieved; product/period mapping needs review','evidence':snippets,**retrieval_meta}

def fetch_publication(source):
    """Fetch one publication and keep enough metadata for review diagnostics."""
    if source.get('data_urls'):
        payload={};methods=[];effective=[]
        for key,data_url in source['data_urls'].items():
            part_raw,part_url,part_meta=fetch(data_url,source)
            payload[key]=json.loads(part_raw.decode('utf-8'))
            methods.append(part_meta.get('retrieval_method','direct'))
            effective.append(part_url)
        raw=json.dumps(payload,sort_keys=True).encode('utf-8')
        return dict(source,url=source['url']), raw, source['url'], {'retrieval_method':'official_json_api','data_urls':effective,'component_methods':methods}
    raw,url,retrieval_meta=fetch(source['url'],source)
    current=dict(source,url=url)
    if source.get('publication_link_pattern'):
        doc=html.fromstring(raw)
        links=[urllib.parse.urljoin(url,a.get('href')) for a in doc.xpath('//a[@href]') if re.search(source['publication_link_pattern'],a.get('href')+' '+clean(a.text_content()),re.I)]
        links=list(dict.fromkeys(links))
        if not links:raise ReviewRequired('No matching publication on the official index')
        raw,url,retrieval_meta=fetch(links[0],source);current['url']=url
    return current, raw, url, retrieval_meta

def extract(source):
    """Return ok, review, or failed for one configured source without guessing."""
    current,raw,url,retrieval_meta=fetch_publication(source)
    try:
        return parse_with_handler(current, raw, url, retrieval_meta)
    except ReviewRequired as first_exc:
        if not crawl4ai_enabled(source):
            raise
        try:
            rendered=retrieve_crawl4ai(source['url'], source)
            rendered_source=dict(source,url=rendered['url'])
            return parse_with_handler(rendered_source, rendered['body'], rendered['url'], {'retrieval_method':'crawl4ai','render_status':rendered.get('render_status','')})
        except ReviewRequired as crawl_exc:
            metadata=getattr(crawl_exc,'metadata',{}) or {}
            if not metadata:
                metadata=getattr(first_exc,'metadata',{})
            if metadata.get('retrieval_method') != 'crawl4ai' and 'source_url' in metadata:
                metadata=dict(metadata, crawl4ai_message=str(crawl_exc)[:220])
            raise ReviewRequired(str(crawl_exc), metadata)

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
        except ReviewRequired as e:
            payload={'status':'review','records':[],'message':str(e)[:500]}
            payload.update(getattr(e,'metadata',{}))
            self.respond(200,payload)
        except Exception as e:self.respond(200,{'status':'review','records':[],'message':str(e)[:500]})

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler).serve_forever()
