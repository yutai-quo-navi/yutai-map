#!/usr/bin/env python3
import json, re, urllib.request, urllib.parse

BASE="https://maps.zensho.co.jp"
UA="Mozilla/5.0 yutai-map-zensho-probe/1.0"

def post(data):
    body=urllib.parse.urlencode(data,doseq=True).encode()
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
    with urllib.request.urlopen(req,timeout=90) as r:
        raw=r.read().decode("utf-8","replace")
        print("STATUS",getattr(r,"status",None),"BYTES",len(raw),"PAYLOAD",data)
        return json.loads(raw)

def summarize(data):
    print("KEYS",sorted(data.keys()))
    html=data.get("list") or ""
    m=re.search(r'検索結果：<strong>([\d,]+)</strong>件',html)
    print("COUNT",m.group(1) if m else "?")
    ids=re.findall(r'/jp/detail/(\d+)\.html',html)
    print("LIST_IDS",len(ids),ids[:8],ids[-3:])
    more=re.findall(r'morelist\((\d+)\)',html)
    print("MORELIST",more[:20],"...",more[-5:])
    md=data.get("mapdata")
    print("MAPDATA_TYPE",type(md).__name__)
    if isinstance(md,list):
        print("MAPDATA_LEN",len(md))
        print("MAPDATA_SAMPLE",json.dumps(md[:2],ensure_ascii=False)[:4000])
    elif isinstance(md,dict):
        print("MAPDATA_KEYS",list(md)[:20])
        print("MAPDATA_SAMPLE",json.dumps(md,ensure_ascii=False)[:4000])
    else:
        print("MAPDATA",repr(md)[:2000])
    return ids,more

tests=[
  {"facility":["shareholder_coupon"]},
  {"facility":["shareholder_coupon"],"map":1},
  {"facility":["shareholder_coupon"],"morelist":2},
  {"facility":["shareholder_coupon"],"morelist":50},
]
for t in tests:
    try:
        d=post(t); summarize(d)
    except Exception as e:
        print("ERROR",t,repr(e))
