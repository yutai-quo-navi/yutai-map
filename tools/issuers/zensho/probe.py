#!/usr/bin/env python3
import json,re,urllib.request,urllib.parse,http.cookiejar

BASE="https://maps.zensho.co.jp"
UA="Mozilla/5.0 yutai-map-zensho-probe/1.0"

def session():
    jar=http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)),jar

def post(opener,pairs):
    body=urllib.parse.urlencode(pairs).encode()
    req=urllib.request.Request(BASE+"/api/search",data=body,headers={
      "User-Agent":UA,"X-Requested-With":"XMLHttpRequest",
      "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8",
      "Referer":BASE+"/jp/shop.html"})
    with opener.open(req,timeout=180) as r:
      d=json.loads(r.read().decode("utf-8","replace"))
    html=d.get("list") or ""
    m=re.search(r'検索結果：<strong>([\d,]+)</strong>件',html)
    ids=re.findall(r'/jp/detail/(\d+)\.html',html)
    return int((m.group(1) if m else "0").replace(",","")),ids,d.get("mapdata") or []

for brand in ["1","16","70"]:
    op,jar=session()
    try:
      count,ids,md=post(op,[("brand[]",brand),("facility[]","shareholder_coupon")])
      print("INITIAL",brand,"count",count,"rows",len(ids),"cookies",[(x.name,x.value[:20]) for x in jar])
      if count>50:
        more=count-50
        count2,ids2,md2=post(op,[("morelist",str(more))])
        print("MORE",brand,"arg",more,"count",count2,"rows",len(ids2),"map",len(md2),"unique",len(set(ids2)),"last",ids2[-5:])
    except Exception as e:
      print("ERROR",brand,repr(e))
