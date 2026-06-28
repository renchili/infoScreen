#!/usr/bin/env python3
from __future__ import annotations
import html,json,os,re,sys,time,urllib.parse,urllib.request
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse

BASE=Path(__file__).resolve().parent
OUT=BASE/'local_event_search_results.json'
REG=BASE/'official_source_registry.json'
TODAY=date.today()
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
MAX_SECONDS=float(os.environ.get('LOCAL_EVENTS_MAX_SECONDS','95'))
MAX_PAGES=int(os.environ.get('LOCAL_EVENTS_MAX_PAGES_PER_SOURCE','70'))
MAX_PER_SOURCE=int(os.environ.get('LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE','8'))
MAX_TOTAL=int(os.environ.get('LOCAL_EVENTS_MAX_TOTAL_EVENTS','60'))
PAST_GRACE=int(os.environ.get('LOCAL_EVENTS_PAST_GRACE_DAYS','1'))
MONTHS={'jan':1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,'sep':9,'sept':9,'september':9,'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12}
MW='jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december'
DATE_RE=re.compile(r'\b20\d{2}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|'+rf'\b\d{{1,2}}\s+(?:{MW})[a-z]*\s*(?:-|to|–|—|until|till)?\s*\d{{0,2}}\s*(?:{MW})?[a-z]*\s*\d{{0,4}}\b|'+rf'\b(?:{MW})[a-z]*\s+\d{{1,2}},?\s*\d{{0,4}}\b',re.I)
EVENT_WORDS=('event','programme','program','workshop','activity','course','class','session','talk','tour','storytelling','storytime','festival','performance','concert','carnival','reading','exhibition','show','camp','walk','trail','experience','drop-in','holiday','screening','guided','open house','lecture')
EVENT_RE=re.compile(r'\b('+'|'.join(re.escape(x) for x in EVENT_WORDS)+r')\b',re.I)
STATIC_RE=re.compile(r'\.(png|jpe?g|gif|svg|webp|ico|pdf|zip|css|js|mp4|mp3|woff2?|ttf|eot)(\?|$)',re.I)
SCRIPT_STYLE_RE=re.compile(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>',re.I)
SCRIPT_JSON_RE=re.compile(r'<script[^>]+type=["\']application/(?:ld\+)?json["\'][^>]*>([\s\S]*?)</script>',re.I)
TAG_RE=re.compile(r'<[^>]+>')
HREF_RE=re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',re.I)
JSON_URL_RE=re.compile(r'["\'](?:href|url|link|path|slug|canonicalUrl|pageUrl)["\']\s*:\s*["\']([^"\']+)["\']',re.I)
RAW_PATH_RE=re.compile(r'/(?:whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|activities?|happenings?|courses|workshops?|things-to-do)/[^"\'<>\\\s]+',re.I)
ABS_RE=re.compile(r'https?://[^"\'<>\\\s]+',re.I)
LOC_RE=re.compile(r'<loc>\s*([^<]+)\s*</loc>',re.I)
SITEMAP_RE=re.compile(r'^\s*Sitemap:\s*(\S+)\s*$',re.I|re.M)
LISTING_RE=re.compile(r'/(?:whats-on|whatson|events?|overview|view-all|exhibitions?|exhibition|programmes?|programs?|activities?|happenings?|courses|workshops?)/?$',re.I)
DETAIL_RE=re.compile(r'/(?:whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|activities?|happenings?|courses|workshops?)/.+',re.I)
GENERIC_TITLE_RE=re.compile(r'^(events?|exhibitions?|programmes?|programs?|activities?|guided tours?|past exhibitions?|family programmes?|school programmes?|for seniors|view all|overview|what\'?s on)$',re.I)
OLD_RE=re.compile(r'\b(past|previous|archive|archived)\b',re.I)
CURRENT_RE=re.compile(r'\b(today|upcoming|current|ongoing|now showing|next programme|latest|new|2026|2027)\b',re.I)
LOCAL_TERMS=('punggol','waterway','one punggol','punggol regional library','safra punggol')
ENTRY_PATHS=('/whats-on','/whats-on/overview','/whats-on/view-all','/events','/event','/exhibition','/exhibitions','/programmes','/activities','/en/events','/en/events.html','/en/whats-on','/en/discover-mandai/events','/en/discover-mandai/events.html')

def now_iso(): return datetime.now(timezone.utc).isoformat()
def clean(x):
    t=html.unescape(str(x or '')).replace('\\/','/').replace('\\u002F','/').replace('\\u002f','/')
    t=SCRIPT_STYLE_RE.sub(' ',t); t=TAG_RE.sub(' ',t)
    t=re.sub(r'#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}',' ',t)
    return re.sub(r'\s+',' ',t).strip()
def short(x,n):
    t=clean(x); return t if len(t)<=n else t[:n-1].rstrip()+'…'
def norm(u,base=''):
    u=html.unescape(str(u or '')).strip().replace('\\/','/').replace('\\u002F','/')
    if u.startswith('//'): u='https:'+u
    if base: u=urljoin(base,u)
    p=urlparse(u)
    if p.scheme not in ('http','https') or not p.netloc: return ''
    q=[(k,v) for k,v in urllib.parse.parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_')]
    return urllib.parse.urlunparse((p.scheme,p.netloc.lower(),p.path or '/', '', urllib.parse.urlencode(q),''))
def host(u): return urlparse(u).netloc.lower().replace('www.','')
def root(u):
    p=urlparse(u); return urllib.parse.urlunparse((p.scheme,p.netloc.lower(),'/','','',''))
def key_url(u):
    p=urlparse(u); return urllib.parse.urlunparse((p.scheme,p.netloc.lower(),p.path.rstrip('/'),'',p.query,'')).lower()
def same(u,domains):
    h=host(u); return bool(h) and any(h==d or h.endswith('.'+d) for d in domains)
def static(u):
    path=urllib.parse.unquote(urlparse(u).path)
    return bool(STATIC_RE.search(path)) or '/api/media/' in path or '/content/dam/' in path or '/_jcr_content/' in path
def fetch(u,timeout=10,max_bytes=2500000):
    req=urllib.request.Request(u,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        ct=r.headers.get('Content-Type','')
        if ct and not re.search(r'text|html|json|xml|javascript',ct,re.I): raise ValueError('non_text_content')
        raw=r.read(max_bytes); m=re.search(r'charset=([\w.-]+)',ct,re.I)
        return raw.decode(m.group(1) if m else 'utf-8','replace')
def meta(page,names):
    for name in names:
        e=re.escape(name)
        for pat in (rf'<meta[^>]+(?:name|property)=["\']{e}["\'][^>]+content=["\']([^"\']+)["\']',rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{e}["\']'):
            m=re.search(pat,page,re.I|re.S)
            if m and clean(m.group(1)): return clean(m.group(1))
    return ''
def title_of(page,fallback=''):
    vals=[meta(page,['og:title','twitter:title'])]
    for pat in (r'<h1[^>]*>([\s\S]*?)</h1>',r'<title[^>]*>([\s\S]*?)</title>'):
        m=re.search(pat,page,re.I)
        if m: vals.append(clean(m.group(1)))
    vals.append(fallback)
    for v in vals:
        v=clean(v)
        if v and '#{' not in v and '{{' not in v: return v
    return ''
def summary(page): return short(meta(page,['og:description','description','twitter:description']),260) or 'Open the official page for details.'
def month(m): return MONTHS.get(str(m).lower()[:3])
def mkdate(d,m,y=None,roll=True):
    mn=month(m)
    if not mn: return None
    yy=int(y) if y else TODAY.year
    try: x=date(yy,mn,int(d))
    except ValueError: return None
    if roll and not y and x<TODAY-timedelta(days=PAST_GRACE):
        try: x=date(yy+1,mn,int(d))
        except ValueError: return None
    return x
def label_dates(text):
    text=clean(text); out=[]; years=[int(y) for y in re.findall(r'\b(20\d{2})\b',text)]; inherited=years[-1] if years else None
    for d1,m1,d2,m2,y in re.findall(rf'\b(\d{{1,2}})\s+({MW})[a-z]*\s*(?:-|to|–|—|until|till)\s*(\d{{1,2}})\s+({MW})[a-z]*\s*(20\d{{2}})?\b',text,re.I):
        y=y or inherited
        for d,m in ((d1,m1),(d2,m2)):
            x=mkdate(d,m,y,not y)
            if x: out.append(x)
    for d1,d2,m,y in re.findall(rf'\b(\d{{1,2}})\s*(?:-|to|–|—|until|till)\s*(\d{{1,2}})\s+({MW})[a-z]*\s*(20\d{{2}})?\b',text,re.I):
        y=y or inherited
        for d in (d1,d2):
            x=mkdate(d,m,y,not y)
            if x: out.append(x)
    for y,m,d in re.findall(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b',text):
        try: out.append(date(int(y),int(m),int(d)))
        except ValueError: pass
    for d,m,y in re.findall(rf'\b(\d{{1,2}})\s+({MW})[a-z]*\s*(20\d{{2}})?\b',text,re.I):
        y=y or inherited; x=mkdate(d,m,y,not y)
        if x: out.append(x)
    for m,d,y in re.findall(rf'\b({MW})[a-z]*\s+(\d{{1,2}}),?\s*(20\d{{2}})?\b',text,re.I):
        y=y or inherited; x=mkdate(d,m,y,not y)
        if x: out.append(x)
    return sorted(set(out))
def sessions_from_text(text,limit=12):
    res=[]; seen=set(); txt=clean(text)[:300000]
    for m in DATE_RE.finditer(txt):
        lab=clean(m.group(0)); k=lab.lower()
        if k in seen: continue
        seen.add(k); ds=label_dates(lab)
        if ds and max(ds)>=TODAY-timedelta(days=PAST_GRACE): res.append({'label':lab,'dates':ds})
        if len(res)>=limit: break
    return res
def best_date(sessions):
    ds=[]
    for s in sessions: ds+=s.get('dates') or []
    future=[d for d in ds if d>=TODAY-timedelta(days=PAST_GRACE)]
    return min(future or ds) if ds else TODAY
def when(sessions):
    labs=[]
    for s in sessions:
        if s.get('label') and s['label'] not in labs: labs.append(s['label'])
    return ' / '.join(labs[:4])+((f' / +{len(labs)-4} more') if len(labs)>4 else '')
def json_objs(page):
    out=[]
    for m in SCRIPT_JSON_RE.finditer(page):
        try: out.append(json.loads(html.unescape(m.group(1)).strip()))
        except Exception: pass
    return out
def walk(v):
    st=[v]
    while st:
        x=st.pop(); yield x
        if isinstance(x,dict): st+=list(x.values())
        elif isinstance(x,list): st+=x
def is_event_obj(x):
    if not isinstance(x,dict): return False
    t=x.get('@type') or x.get('type'); arr=t if isinstance(t,list) else [t]
    return any(str(i).lower()=='event' for i in arr)
def loc_from_obj(x):
    if isinstance(x,dict):
        l=x.get('location')
        if isinstance(l,str): return clean(l)[:120]
        if isinstance(l,dict): return clean(l.get('name') or l.get('address') or '')[:120]
    return ''
def location(source,page,obj=None):
    if obj:
        l=loc_from_obj(obj)
        if l: return l
    txt=clean(page[:120000])
    for name in [source.get('default_venue') or source.get('name') or '']+(source.get('aliases') or []):
        if name and re.search(r'\b'+re.escape(name)+r'\b',txt,re.I): return name
    return source.get('default_venue') or source.get('name')
def listing(u):
    p=urlparse(u); return bool(LISTING_RE.search(p.path.lower().rstrip('/') or '/')) or bool(p.query and re.search(r'\b(category|filter|time|date|type|page)=',p.query,re.I))
def detail(u): return bool(DETAIL_RE.search(urlparse(u).path.lower().rstrip('/'))) and not listing(u) and not static(u)
def old_signal(u,text):
    hay=urllib.parse.unquote(urlparse(u).path.replace('-',' ').replace('_',' ')+' '+clean(text[:1000])).lower()
    return bool(OLD_RE.search(hay)) and not CURRENT_RE.search(hay)
def generic_title(t,u):
    t=clean(t); slug=urlparse(u).path.rstrip('/').split('/')[-1].replace('-',' ').lower()
    return bool(GENERIC_TITLE_RE.match(t) or (t.lower()==slug and GENERIC_TITLE_RE.match(slug)))
def make_event(source,u,t,sessions,page,obj=None,structured=False):
    if not t or not sessions or generic_title(t,u): return None
    if max(d for s in sessions for d in s.get('dates',[]))<TODAY-timedelta(days=PAST_GRACE): return None
    if not structured:
        if not detail(u) or old_signal(u,page): return None
        if not EVENT_RE.search(t+' '+urllib.parse.unquote(urlparse(u).path.replace('-',' '))+' '+clean(page[:5000])): return None
    return {'title':short(t,140),'when':when(sessions),'where':location(source,page,obj),'host':source['name'],'source_name':source['name'],'url':u,'summary':summary(page),'start_date':best_date(sessions).isoformat(),'kind':'event','source_type':'official_registry','structured':bool(structured)}
def analyze(source,u,page,label=''):
    out=[]
    for obj in json_objs(page):
        for node in walk(obj):
            if is_event_obj(node):
                t=clean(node.get('name') or node.get('headline') or '')
                s=sessions_from_text(' - '.join(str(node.get(k) or '') for k in ('startDate','endDate','doorTime','datePublished','description')),4)
                ev=make_event(source,u,t,s,page,node,True)
                if ev: out.append(ev)
    if out: return out
    ev=make_event(source,u,title_of(page,label),sessions_from_text(page),page,None,False)
    return [ev] if ev else []
def score(source,u,label,ctx):
    if not same(u,source['domains']) or static(u): return -999
    route=urllib.parse.unquote((urlparse(u).path+' '+urlparse(u).query).replace('-',' ').replace('_',' ')).lower(); txt=clean(label+' '+ctx[:1800]).lower()
    if old_signal(u,txt): return -200
    s=0
    if detail(u): s+=80
    if listing(u): s+=45
    if EVENT_RE.search(route): s+=20
    if EVENT_RE.search(txt): s+=20
    if DATE_RE.search(txt): s+=25
    if CURRENT_RE.search(txt) or CURRENT_RE.search(route): s+=25
    if any(x in txt or x in route for x in LOCAL_TERMS): s+=8
    return s
def discover(source,page,base):
    found={}
    def add(raw,label,ctx):
        u=norm(raw,base); sc=score(source,u,label,ctx) if u else -999
        if sc<35: return
        k=key_url(u); item=(sc,u,clean(label)[:140])
        if k not in found or item[0]>found[k][0]: found[k]=item
    for m in HREF_RE.finditer(page): add(m.group(1),m.group(2),page[max(0,m.start()-900):m.end()+1400])
    dec=html.unescape(page).replace('\\/','/').replace('\\u002F','/')
    for rgx in (JSON_URL_RE,RAW_PATH_RE,ABS_RE):
        for m in rgx.finditer(dec): add(m.group(1) if rgx is JSON_URL_RE else m.group(0),m.group(0),dec[max(0,m.start()-700):m.end()+1000])
    return sorted(found.values(),key=lambda x:(-x[0],x[1]))
def sitemap_links(source,deadline):
    rootu=root(source['official_site']); urls=[urljoin(rootu,'/sitemap.xml'),urljoin(rootu,'/sitemap_index.xml')]
    try: urls += [norm(x,rootu) for x in SITEMAP_RE.findall(fetch(urljoin(rootu,'/robots.txt'),6,400000))]
    except Exception: pass
    pend=[(u,0) for u in dict.fromkeys(u for u in urls if u and same(u,source['domains']))]; seen=set(); found={}
    while pend and time.time()<deadline and len(seen)<18 and len(found)<120:
        u,depth=pend.pop(0); k=key_url(u)
        if k in seen: continue
        seen.add(k)
        try: xml=fetch(u,8,2500000)
        except Exception: continue
        for loc in LOC_RE.findall(xml):
            lu=norm(loc,u)
            if not lu or not same(lu,source['domains']) or static(lu): continue
            if ('sitemap' in lu.lower() or lu.lower().endswith('.xml')) and depth<1: pend.append((lu,depth+1)); continue
            sc=score(source,lu,lu,'')
            if sc>=35: found[key_url(lu)]=(sc+10,lu,'sitemap')
    return sorted(found.values(),key=lambda x:(-x[0],x[1]))
def canonical(u):
    p=urlparse(u); path=urllib.parse.unquote(p.path.lower()).rstrip('/'); path=re.sub(r'\.html$','',path)
    path=re.sub(r'^/en/discover-mandai','',path)
    path=re.sub(r'^/whats-on/(exhibition|exhibitions|programme|programmes|event|events)/',r'/\1/',path)
    path=path.replace('/exhibitions/','/exhibition/').replace('/programmes/','/programme/').replace('/events/','/event/')
    return host(u)+path
def load_sources():
    data=json.loads(REG.read_text(encoding='utf-8')); out=[]
    for e in data.get('institutions') or []:
        if e.get('status')!='confirmed': continue
        site=norm(e.get('official_site')); name=clean(e.get('name'))
        if not site or not name: continue
        domains=[]
        for d in [host(site)]+[str(x).lower().replace('www.','').strip() for x in e.get('allowed_domains') or []]:
            if d and d not in domains: domains.append(d)
        seeds=[site]
        for sub in e.get('official_subsites') or []:
            if isinstance(sub,dict):
                u=norm(sub.get('url'))
                if u and same(u,domains) and u not in seeds: seeds.append(u)
        out.append({'name':name,'default_venue':name,'aliases':[clean(x) for x in e.get('aliases') or [] if clean(x)],'official_subsites':e.get('official_subsites') or [],'official_site':site,'domains':domains,'seeds':seeds})
    if not out: raise SystemExit('official_source_registry.json has no confirmed institutions')
    return out
def crawl(source,location,deadline):
    q=[]; queued=set(); fetched=set(); results=[]; rkeys=set()
    dbg={'source':source['name'],'official_site':source['official_site'],'domains':source['domains'],'seeds':[],'runtime_entry_preview':[],'sitemap_preview':[],'pages_fetched':0,'queue_seen':0,'discovered_preview':[],'fetched_preview':[],'accepted_preview':[],'rejected_preview':[]}
    def push(u,sc,label):
        u=norm(u)
        if not u or not same(u,source['domains']) or static(u): return False
        k=key_url(u)
        if k in queued: return False
        queued.add(k); q.append((sc,u,label)); return True
    for s in source['seeds']:
        if push(s,100,'official-site'): dbg['seeds'].append(s)
    for base in [root(x) for x in source['seeds']]:
        for p in ENTRY_PATHS:
            u=norm(p,base); sc=score(source,u,p,'upcoming current today')
            if sc>=35 and push(u,sc+5,'common-entry') and len(dbg['runtime_entry_preview'])<30: dbg['runtime_entry_preview'].append({'score':sc+5,'url':u,'label':'common-entry'})
    for sc,u,l in sitemap_links(source,deadline):
        if push(u,sc,l) and len(dbg['sitemap_preview'])<30: dbg['sitemap_preview'].append({'score':sc,'url':u,'label':l})
    dbg['queue_seen']=len(queued)
    while q and time.time()<deadline and len(fetched)<MAX_PAGES and len(results)<MAX_PER_SOURCE:
        q.sort(key=lambda x:(-x[0],x[1])); sc,u,label=q.pop(0); k=key_url(u)
        if k in fetched: continue
        fetched.add(k)
        try: page=fetch(u)
        except Exception as e:
            if len(dbg['rejected_preview'])<30: dbg['rejected_preview'].append({'url':u,'reason':'fetch:'+type(e).__name__,'label':label})
            continue
        dbg['pages_fetched']+=1
        if len(dbg['fetched_preview'])<40: dbg['fetched_preview'].append({'url':u,'score':sc,'label':label})
        before=len(results)
        for ev in analyze(source,u,page,label):
            ck=canonical(ev['url'])
            if ck in rkeys: continue
            rkeys.add(ck); results.append(ev); dbg['accepted_preview'].append({'title':ev['title'],'url':ev['url'],'when':ev['when'],'where':ev.get('where')})
            if len(results)>=MAX_PER_SOURCE: break
        if before==len(results) and detail(u) and len(dbg['rejected_preview'])<30: dbg['rejected_preview'].append({'url':u,'reason':'not_confirmed_current_event','label':label})
        for lsc,lu,ll in discover(source,page,u):
            lk=key_url(lu)
            if lk in fetched or lk in queued: continue
            queued.add(lk); q.append((lsc,lu,ll))
            if len(dbg['discovered_preview'])<40: dbg['discovered_preview'].append({'score':lsc,'url':lu,'label':ll})
        dbg['queue_seen']=len(queued)
    dbg['accepted']=len(results); return results,dbg
def sort_results(items,location):
    def ls(x):
        txt=' '.join(str(x.get(k,'')) for k in ('title','where','summary','source_name')).lower()
        return sum(1 for t in LOCAL_TERMS if t in txt)
    return sorted(items,key=lambda x:(-ls(x),x.get('source_name',''),x.get('start_date',''),x.get('title','')))
def main():
    location=' '.join(sys.argv[1:]).strip() or 'Punggol Singapore'; deadline=time.time()+MAX_SECONDS; sources=load_sources(); all_items=[]; debug=[]; seen=set()
    for src in sources:
        if time.time()>=deadline or len(all_items)>=MAX_TOTAL: break
        items,dbg=crawl(src,location,deadline); debug.append(dbg)
        for it in items:
            ck=canonical(it['url'])
            if ck in seen: continue
            seen.add(ck); all_items.append(it)
            if len(all_items)>=MAX_TOTAL: break
    all_items=sort_results(all_items,location)[:MAX_TOTAL]
    payload={'ok':True,'version':21,'extractor':'official-registry-strict-current-events-v21','updated_at':now_iso(),'location':location,'source_registry':REG.name,'source_count':len(sources),'per_source_limit':MAX_PER_SOURCE,'count':len(all_items),'sources':[{'title':s['name'],'url':s['official_site']} for s in sources],'results':all_items,'debug_by_source':debug}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
