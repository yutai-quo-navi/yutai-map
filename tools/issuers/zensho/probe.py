#!/usr/bin/env python3
import json,re,urllib.request,urllib.parse,http.cookiejar
BASE="https://maps.zensho.co.jp"
UA="Mozilla/5.0 yutai-map-zensho-probe/1.0"
def one(pairs):
  jar=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
  body=urllib.parse.urlencode(pairs).encode()
  req=urllib.request.Request(BASE+"/api/search",data=body,headers={
    "User-Agent":UA,"X-Requested-With":"XMLHttpRequest",
    "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8","Referer":BASE+"/jp/address.html"})
  with op.open(req,timeout=120) as r: d=json.loads(r.read().decode("utf-8","replace"))
  html=d.get("list") or ""; m=re.search(r'検索結果：<strong>([\d,]+)</strong>件',html)
  ids=re.findall(r'/jp/detail/(\d+)\.html',html)
  return int((m.group(1) if m else "0").replace(",","")),len(ids),ids[:3],ids[-3:]
for addr in ["北海道","東京都","大阪府","沖縄県","札幌市","東京"]:
  try:
    print("ADDR",addr,one([("brand[]","1"),("facility[]","shareholder_coupon"),("address",addr)]))
  except Exception as e: print("ERROR",addr,repr(e))
