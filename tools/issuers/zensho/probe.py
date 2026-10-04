#!/usr/bin/env python3
import json, re, urllib.request, urllib.parse
from collections import Counter

BASE="https://maps.zensho.co.jp"
UA="Mozilla/5.0 yutai-map-zensho-probe/1.0"

def post(pairs):
    body=urllib.parse.urlencode(pairs).encode()
    req=urllib.request.Request(
        BASE+"/api/search",data=body,
        headers={
          "User-Agent":UA,
          "Accept-Language":"ja,en;q=0.8",
          "X-Requested-With":"XMLHttpRequest",
          "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8",
          "Referer":BASE+"/jp/shop.html"
        }
    )
    with urllib.request.urlopen(req,timeout=180) as r:
        raw=r.read().decode("utf-8","replace")
        print("STATUS",getattr(r,"status",None),"BYTES",len(raw),"QUERY",pairs)
        return json.loads(raw)

for pairs in [
    [("brand[]",""),("facility[]","shareholder_coupon")],
    [("facility[]","shareholder_coupon"),("morelist","5000")],
    [("brand[]","1"),("facility[]","shareholder_coupon"),("morelist","5000")],
]:
    try:
        d=post(pairs)
        html=d.get("list") or ""
        m=re.search(r'検索結果：<strong>([\d,]+)</strong>件',html)
        ids=re.findall(r'/jp/detail/(\d+)\.html',html)
        md=d.get("mapdata") or []
        print("COUNT",m.group(1) if m else "?","LIST_IDS",len(ids),"MAPDATA",len(md))
        print("UNIQUE_IDS",len(set(ids)))
        brands=Counter(str(x.get("brand") or "") for x in md if isinstance(x,dict))
        print("BRANDS",json.dumps(brands,ensure_ascii=False,sort_keys=True))
        print("FIRST",json.dumps(md[:2],ensure_ascii=False)[:3000])
        print("OPTIONS",Counter(o for x in md if isinstance(x,dict) for o in (x.get("options") or [])))
        print("LAST_IDS",ids[-10:])
    except Exception as e:
        print("ERROR",pairs,repr(e))
