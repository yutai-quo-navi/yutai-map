#!/usr/bin/env python3
import json,re,urllib.request,urllib.parse
BASE="https://maps.zensho.co.jp"
UA="Mozilla/5.0 yutai-map-zensho-probe/1.0"
def post(pairs):
    body=urllib.parse.urlencode(pairs).encode()
    req=urllib.request.Request(BASE+"/api/search",data=body,headers={
      "User-Agent":UA,"X-Requested-With":"XMLHttpRequest",
      "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8",
      "Referer":BASE+"/jp/shop.html"})
    with urllib.request.urlopen(req,timeout=180) as r:
      d=json.loads(r.read().decode("utf-8","replace"))
    html=d.get("list") or ""
    m=re.search(r'検索結果：<strong>([\d,]+)</strong>件',html)
    ids=re.findall(r'/jp/detail/(\d+)\.html',html)
    return int((m.group(1) if m else "0").replace(",","")),len(ids),len(d.get("mapdata") or [])
base=[("brand[]","1"),("facility[]","shareholder_coupon")]
for extra in [None,50,100,200,300,500,750,1000,1250,1500,1750,2000,2500]:
    pairs=list(base)
    if extra is not None: pairs.append(("morelist",str(extra)))
    try:
      print("TEST",extra,post(pairs))
    except Exception as e:
      print("ERROR",extra,repr(e))
