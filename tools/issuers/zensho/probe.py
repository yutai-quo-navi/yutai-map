#!/usr/bin/env python3
import re, urllib.request, urllib.parse, html

BASE="https://maps.zensho.co.jp"
URL=BASE+"/jp/address.html"
UA="Mozilla/5.0 yutai-map-zensho-probe/1.0"

req=urllib.request.Request(URL,headers={"User-Agent":UA,"Accept-Language":"ja,en;q=0.8"})
with urllib.request.urlopen(req,timeout=120) as r:
    text=r.read().decode("utf-8","replace")

print("BYTES",len(text))

print("\n=== LINKS WITH PREF/ADDRESS/AREA ===")
for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>',text,re.I|re.S):
    attrs=m.group(1)
    label=re.sub(r'<[^>]+>',' ',m.group(2))
    label=html.unescape(re.sub(r'\s+',' ',label)).strip()
    hrefm=re.search(r'href=["\']([^"\']+)',attrs,re.I)
    href=hrefm.group(1) if hrefm else ""
    blob=(href+" "+attrs+" "+label)
    if any(k in blob.lower() for k in ["pref","address","area","hokkaido","tokyo"]) or re.search(r'(北海道|東京都|京都府|大阪府|県)',label):
        print("LINK",label,"=>",href,"ATTRS",re.sub(r'\s+',' ',attrs)[:500])

print("\n=== INPUTS / SELECTS ===")
for m in re.finditer(r'<(input|select|option)\b[^>]*>',text,re.I):
    tag=m.group(0)
    if any(k in tag.lower() for k in ["pref","address","area","name=","value="]):
        print("TAG",re.sub(r'\s+',' ',tag)[:1000])

print("\n=== SCRIPT LINES ===")
scripts=re.findall(r'<script\b[^>]*\bsrc=["\']([^"\']+)',text,re.I)
for s in scripts:
    u=urllib.parse.urljoin(URL,s)
    if not u.startswith(BASE): continue
    try:
        req=urllib.request.Request(u,headers={"User-Agent":UA})
        with urllib.request.urlopen(req,timeout=120) as r:
            js=r.read().decode("utf-8","replace")
    except Exception as e:
        print("ERR",u,repr(e)); continue
    for line in js.splitlines():
        low=line.lower()
        if any(k in low for k in ["pref","address","area","/api/"]):
            print("JS",u,re.sub(r'\s+',' ',line.strip())[:1500])
