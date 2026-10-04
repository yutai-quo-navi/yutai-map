#!/usr/bin/env python3
import json, re, urllib.request, urllib.parse

BASE="https://maps.zensho.co.jp"
URL=BASE+"/jp/shop.html"
UA="Mozilla/5.0 yutai-map-zensho-probe/1.0"

def fetch(url, data=None):
    headers={"User-Agent":UA,"Accept-Language":"ja,en;q=0.8","X-Requested-With":"XMLHttpRequest"}
    if data is not None:
        body=urllib.parse.urlencode(data,doseq=True).encode()
        headers["Content-Type"]="application/x-www-form-urlencoded; charset=UTF-8"
    else:
        body=None
    req=urllib.request.Request(url,data=body,headers=headers)
    with urllib.request.urlopen(req,timeout=90) as r:
        raw=r.read()
        text=raw.decode("utf-8","replace")
        print("FETCH",url,"status",getattr(r,"status",None),"bytes",len(raw),"ctype",r.headers.get("Content-Type"))
        return text

html=fetch(URL)

print("\n=== BRAND/FACILITY INPUTS ===")
for m in re.finditer(r'<input\b[^>]*\bname=["\'](brand|facility)["\'][^>]*>',html,re.I):
    tag=m.group(0)
    name=re.search(r'\bname=["\']([^"\']+)',tag,re.I)
    value=re.search(r'\bvalue=["\']?([^"\' >]+)',tag,re.I)
    iid=re.search(r'\bid=["\']([^"\']+)',tag,re.I)
    ident=iid.group(1) if iid else ""
    tail=html[m.end():m.end()+500]
    label=""
    lm=re.search(r'<label[^>]*for=["\']'+re.escape(ident)+r'["\'][^>]*>(.*?)</label>',tail,re.I|re.S) if ident else None
    if lm:
        label=re.sub(r'<[^>]+>',' ',lm.group(1))
        label=re.sub(r'\s+',' ',label).strip()
        imgalt=re.search(r'alt=["\']([^"\']+)',lm.group(1),re.I)
        if imgalt: label=(label+" "+imgalt.group(1)).strip()
    print("INPUT",name.group(1) if name else "",value.group(1) if value else "","id="+ident,"label="+label)

common=fetch(BASE+"/jp/js/common.js")
print("\n=== COMMON.JS SEARCH FUNCTIONS ===")
for fn in ["_search","_search_ajax","_update_shops"]:
    pos=common.find("function "+fn)
    if pos>=0:
        print("\nFUNCTION",fn)
        print(common[pos:pos+4500])

print("\n=== TEST API: empty search ===")
for payload in [
    {},
    {"facility":"1"},
    {"facility":"株主優待券利用可"},
]:
    try:
        text=fetch(BASE+"/api/search",payload)
        print("PAYLOAD",payload)
        print(text[:5000])
    except Exception as e:
        print("API ERROR",payload,repr(e))
