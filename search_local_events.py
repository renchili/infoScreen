#!/usr/bin/env python3
from __future__ import annotations
import json,re,sys,time,urllib.parse
import search_local_events_v21 as c

BLOCK_RE=re.compile(r"</?(?:br|p|div|section|article|main|header|footer|h1|h2|h3|h4|li|ul|ol|table|tr|td|th|span)[^>]*>",re.I)
TIME_RE=re.compile(r"\b(?:\d{1,2}(?:\.\d{2})?\s*(?:am|pm)|daily|all day|selected dates|last admission|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend)\b",re.I)
VENUE_RE=re.compile(r"\b(?:gallery|galleries|museum|level|foyer|green|b1|l1|l2|room|hall|theatre|zoo|safari|paradise|cove|concourse|atrium|basement)\b",re.I)
SEP=r"(?:-|–|—|to|until|till)"
FULL_RANGE_RE=re.compile(rf"\b(\d{{1,2}})\s+({c.MW})[a-z]*\s+(20\d{{2}})\s*{SEP}\s*(\d{{1,2}})\s+({c.MW})[a-z]*\s+(20\d{{2}})\b",re.I)
END_YEAR_RANGE_RE=re.compile(rf"\b(\d{{1,2}})\s+({c.MW})[a-z]*\s*{SEP}\s*(\d{{1,2}})\s+({c.MW})[a-z]*\s+(20\d{{2}})\b",re.I)
SAME_MONTH_RANGE_RE=re.compile(rf"\b(\d{{1,2}})\s*{SEP}\s*(\d{{1,2}})\s+({c.MW})[a-z]*\s*(20\d{{2}})?\b",re.I)
OPEN_START_RE=re.compile(rf"\b(?:from|since|starting|starts)\s+(\d{{1,2}})\s+({c.MW})[a-z]*\s+(20\d{{2}})\b",re.I)
UNTIL_RE=re.compile(rf"\b(?:until|till)\s+(\d{{1,2}})\s+({c.MW})[a-z]*\s+(20\d{{2}})\b",re.I)

def _line(x):
    x=c.html.unescape(str(x or '')).replace('\\/','/').replace('\\u002F','/').replace('\\u002f','/')
    x=re.sub(r'#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}',' ',x)
    return re.sub(r'[ \t\r\f\v]+',' ',x).strip(' |•\t')

def lines(page):
    text=c.SCRIPT_STYLE_RE.sub(' ',page)
    text=BLOCK_RE.sub('\n',text)
    text=c.TAG_RE.sub(' ',text)
    text=c.html.unescape(text).replace('\\/','/').replace('\\u002F','/').replace('\\u002f','/')
    text=re.sub(r"\s+(?=(?:From\s+)?\d{1,2}\s+(?:%s))"%c.MW,'\n',text,flags=re.I)
    text=re.sub(r"\s+(?=(?:Daily|Fridays?|Saturdays?|Sundays?)\s*[-–])",'\n',text,flags=re.I)
    text=re.sub(r"\s+(?=Asian Civilisations Museum\b|National Museum of Singapore\b|Night Safari\b|Singapore Zoo\b)",'\n',text,flags=re.I)
    out=[]
    for raw in text.split('\n'):
        v=_line(raw)
        if v: out.append(v)
    return out

def block(page,title):
    ls=lines(page)
    if not ls: return []
    title=c.clean(title); toks=[title.lower()]
    for sep in (':','|','-'):
        if sep in title: toks.append(title.split(sep,1)[0].strip().lower())
    start=0
    for i,l in enumerate(ls):
        low=l.lower()
        if any(t and t in low for t in toks): start=i; break
    return ls[start:min(len(ls),start+38)]

def dates(label):
    label=c.clean(label); out=[]
    for d1,m1,y1,d2,m2,y2 in FULL_RANGE_RE.findall(label): out += [c.mkdate(d1,m1,y1,False),c.mkdate(d2,m2,y2,False)]
    for d1,m1,d2,m2,y in END_YEAR_RANGE_RE.findall(label): out += [c.mkdate(d1,m1,y,False),c.mkdate(d2,m2,y,False)]
    for d1,d2,m,y in SAME_MONTH_RANGE_RE.findall(label): out += [c.mkdate(d1,m,y or None,not bool(y)),c.mkdate(d2,m,y or None,not bool(y))]
    for d,m,y in OPEN_START_RE.findall(label): out.append(c.mkdate(d,m,y,False))
    for d,m,y in UNTIL_RE.findall(label): out.append(c.mkdate(d,m,y,False))
    out += c.label_dates(label)
    return sorted({x for x in out if x})

def session(label,ongoing=False):
    label=c.clean(label); ds=dates(label)
    if not ds: return None
    on=bool(ongoing or OPEN_START_RE.search(label))
    if on or max(ds)>=c.TODAY-c.timedelta(days=c.PAST_GRACE): return {'label':label,'dates':ds,'ongoing':on}
    return None

def sessions_from_block(page,title):
    b=block(page,title); scored=[]
    for i,l in enumerate(b):
        if FULL_RANGE_RE.search(l) or END_YEAR_RANGE_RE.search(l) or OPEN_START_RE.search(l) or UNTIL_RE.search(l) or c.DATE_RE.search(l):
            w=' '.join(b[i:min(len(b),i+5)]); score=0
            if FULL_RANGE_RE.search(l) or END_YEAR_RANGE_RE.search(l): score+=30
            if OPEN_START_RE.search(l): score+=24
            if SAME_MONTH_RANGE_RE.search(l) or c.DATE_RE.search(l) or UNTIL_RE.search(l): score+=12
            if TIME_RE.search(w): score+=8
            if VENUE_RE.search(w): score+=8
            if i<=20: score+=6
            if len(l)>160: score-=16
            if re.search(r'\b(programmes on selected dates|stay tuned|newsletter|last updated|terms|conditions|copyright)\b',l,re.I): score-=20
            if score>0: scored.append((score,i,l))
    if not scored: return []
    scored.sort(key=lambda x:(-x[0],x[1]))
    s=session(scored[0][2],bool(OPEN_START_RE.search(scored[0][2])))
    return [s] if s else []

def sessions_text(text,limit=12):
    text=c.clean(text)[:300000]; out=[]; seen=set()
    def add(label,on=False):
        k=c.clean(label).lower()
        if not k or k in seen: return
        seen.add(k); s=session(label,on)
        if s: out.append(s)
    for rgx,on in ((FULL_RANGE_RE,False),(END_YEAR_RANGE_RE,False),(OPEN_START_RE,True),(UNTIL_RE,False),(c.DATE_RE,False)):
        for m in rgx.finditer(text):
            add(m.group(0),on)
            if len(out)>=limit: return out[:limit]
    return out[:limit]

def loc(source,page,title,obj=None):
    if obj:
        v=c.loc_from_obj(obj)
        if v: return v
    b=block(page,title)
    for i,l in enumerate(b):
        if FULL_RANGE_RE.search(l) or END_YEAR_RANGE_RE.search(l) or OPEN_START_RE.search(l) or c.DATE_RE.search(l):
            for x in b[i+1:i+8]:
                v=c.clean(x)
                if VENUE_RE.search(v) and not c.DATE_RE.search(v) and not TIME_RE.search(v): return c.short(v,120)
    return c.location(source,page,obj)

def current(sessions):
    ds=[]
    for s in sessions:
        if s.get('ongoing'): return True
        ds += s.get('dates') or []
    return bool(ds and max(ds)>=c.TODAY-c.timedelta(days=c.PAST_GRACE))

def best(sessions):
    future=[]; all_ds=[]
    for s in sessions:
        all_ds += s.get('dates') or []
        future += [d for d in s.get('dates') or [] if d>=c.TODAY-c.timedelta(days=c.PAST_GRACE)]
    return min(future or all_ds or [c.TODAY])

def make(source,url,title,sessions,page,obj=None,structured=False):
    title=c.clean(title)
    if not title or not sessions or not current(sessions) or c.generic_title(title,url): return None
    if not structured and not c.detail(url): return None
    return {'title':c.short(title,140),'when':c.when(sessions),'where':loc(source,page,title,obj),'host':source['name'],'source_name':source['name'],'url':url,'summary':c.summary(page),'start_date':best(sessions).isoformat(),'kind':'event','source_type':'official_registry','structured':bool(structured)}

def analyze(source,url,page,label=''):
    evs=[]
    for obj in c.json_objs(page):
        for node in c.walk(obj):
            if c.is_event_obj(node):
                title=c.clean(node.get('name') or node.get('headline') or '')
                dt=' - '.join(str(node.get(k) or '') for k in ('startDate','endDate','doorTime','datePublished','description'))
                ev=make(source,url,title,sessions_text(dt,4),page,node,True)
                if ev: evs.append(ev)
    if evs: return evs
    title=c.title_of(page,label)
    ses=sessions_from_block(page,title) or sessions_text(page+' '+str(label or ''),16)
    ev=make(source,url,title,ses,page,None,False)
    return [ev] if ev else []

def score(source,url,label,context):
    if not c.same(url,source['domains']) or c.static(url): return -999
    p=c.urlparse(url); route=urllib.parse.unquote((p.path+' '+p.query).replace('-',' ').replace('_',' ')).lower(); text=c.clean(str(label or '')+' '+str(context or '')[:1800]).lower(); s=0
    if c.detail(url): s+=80
    if c.listing(url): s+=45
    if c.EVENT_RE.search(route): s+=20
    if c.EVENT_RE.search(text): s+=20
    if c.DATE_RE.search(text): s+=25
    if c.CURRENT_RE.search(text) or c.CURRENT_RE.search(route): s+=25
    if any(t in text or t in route for t in c.LOCAL_TERMS): s+=8
    return s

def main():
    c.old_signal=lambda url,text: False; c.score=score; c.sessions_from_text=sessions_text; c.make_event=make; c.analyze=analyze
    location=' '.join(sys.argv[1:]).strip() or 'Punggol Singapore'; deadline=time.time()+c.MAX_SECONDS; sources=c.load_sources(); items=[]; debug=[]; seen=set()
    for src in sources:
        if time.time()>=deadline or len(items)>=c.MAX_TOTAL: break
        got,dbg=c.crawl(src,location,deadline); debug.append(dbg)
        for it in got:
            ck=c.canonical(it['url'])
            if ck in seen: continue
            seen.add(ck); items.append(it)
            if len(items)>=c.MAX_TOTAL: break
    items=c.sort_results(items,location)[:c.MAX_TOTAL]
    payload={'ok':True,'version':23,'extractor':'official-registry-primary-detail-fields-v23','updated_at':c.now_iso(),'location':location,'source_registry':c.REG.name,'source_count':len(sources),'per_source_limit':c.MAX_PER_SOURCE,'count':len(items),'sources':[{'title':s['name'],'url':s['official_site']} for s in sources],'results':items,'debug_by_source':debug}
    c.OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
