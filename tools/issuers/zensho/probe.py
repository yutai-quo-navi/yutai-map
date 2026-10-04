#!/usr/bin/env python3
import re, urllib.request, urllib.parse

BASE="https://maps.zensho.co.jp"
URL=BASE+"/jp/shop.html"
UA="Mozilla/5.0 yutai-map-zensho-probe/1.0"

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept-Language":"ja,en;q=0.8"})
    with urllib.request.urlopen(req,timeout=60) as r:
        data=r.read().decode("utf-8","replace")
        print("FETCH",url,"status",getattr(r,"status",None),"bytes",len(data))
        return data

html=fetch(URL)
print("\n=== FORMS ===")
for m in re.finditer(r"<form\b[^>]*>(.*?)</form>",html,re.I|re.S):
    head=m.group(0)[:500]
    print(re.sub(r"\s+"," ",head))
    names=sorted(set(re.findall(r'\bname=["\']([^"\']+)',m.group(0),re.I)))
    if names: print("names=",names)

scripts=re.findall(r'<script\b[^>]*\bsrc=["\']([^"\']+)',html,re.I)
print("\n=== SCRIPTS ===")
for s in scripts: print(urllib.parse.urljoin(URL,s))

patterns=[
    r'https?://[^"\'\s)]+',
    r'["\']([^"\']*(?:api|ajax|json|search|shop|store)[^"\']*)["\']'
]
keys=("api","ajax","json","search","shop","store","yutai","株主","優待","lat","lng","latitude","longitude")

for s in scripts:
    u=urllib.parse.urljoin(URL,s)
    if not u.startswith(BASE): continue
    try: js=fetch(u)
    except Exception as e:
        print("SCRIPT ERROR",u,repr(e)); continue
    print("\n---",u,"---")
    hits=[]
    for line in js.splitlines():
        low=line.lower()
        if any(k.lower() in low for k in keys):
            hits.append(line.strip())
    if len(js.splitlines())<10:
        # minified: extract URL-ish and endpoint-ish strings
        vals=[]
        for pat in patterns:
            for x in re.findall(pat,js,re.I):
                if isinstance(x,tuple): x="".join(x)
                if any(k.lower() in x.lower() for k in keys):
                    vals.append(x)
        for x in sorted(set(vals))[:300]: print("TOKEN",x[:500])
    else:
        for h in hits[:300]: print("LINE",h[:1200])

print("\n=== INLINE URL/ENDPOINT TOKENS ===")
for pat in patterns:
    vals=re.findall(pat,html,re.I)
    out=[]
    for x in vals:
        if isinstance(x,tuple): x="".join(x)
        if any(k.lower() in x.lower() for k in keys):
            out.append(x)
    for x in sorted(set(out))[:300]: print("HTMLTOKEN",x[:500])
