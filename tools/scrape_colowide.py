import json, re, urllib.parse, urllib.request
from bs4 import BeautifulSoup

URL = "https://www.colowide.co.jp/gs/search_keyword_results.php"
TARGET = "コロワイド/カッパ・クリエイト/アトム株主優待"

PREFS = [
"北海道","青森県","岩手県","宮城県","秋田県","山形県","福島県","茨城県","栃木県","群馬県",
"埼玉県","千葉県","東京都","神奈川県","新潟県","富山県","石川県","福井県","山梨県","長野県",
"岐阜県","静岡県","愛知県","三重県","滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県",
"鳥取県","島根県","岡山県","広島県","山口県","徳島県","香川県","愛媛県","高知県",
"福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県","沖縄県"
]
addr_re = re.compile(r"^(?:" + "|".join(map(re.escape, PREFS)) + r").+")
phone_re = re.compile(r"0\d{1,4}-\d{1,4}-\d{3,4}")

req = urllib.request.Request(URL, headers={"User-Agent":"Mozilla/5.0 yutai-map-alpha"})
with urllib.request.urlopen(req, timeout=60) as r:
    html = r.read().decode("utf-8", "replace")

soup = BeautifulSoup(html, "html.parser")
stores = []
seen = set()

for h3 in soup.find_all("h3"):
    chosen = None
    node = h3
    for _ in range(10):
        node = node.parent
        if not node:
            break
        txt = "\n".join(node.stripped_strings)
        if TARGET in txt and len(node.find_all("h3")) == 1:
            chosen = node
            break
    if not chosen:
        continue

    name = " ".join(h3.stripped_strings).strip()
    if not name or name in seen:
        continue

    lines = [x.strip() for x in chosen.stripped_strings if x.strip()]
    benefit_lines = [x for x in lines if "株主優待" in x]
    if not any(TARGET in x for x in benefit_lines):
        continue

    address = next((x for x in lines if addr_re.match(x)), "")
    phone = ""
    for x in lines:
        m = phone_re.search(x)
        if m:
            phone = m.group(0)
            break

    a = h3.find("a", href=True)
    detail_url = urllib.parse.urljoin(URL, a["href"]) if a else ""

    stores.append({
        "name": name,
        "address": address,
        "phone": phone,
        "benefits": benefit_lines,
        "official_url": detail_url
    })
    seen.add(name)

page_text = " ".join(soup.stripped_strings)
m = re.search(r"(\d[\d,]*)\s*店舗", page_text)

out = {
    "source": URL,
    "target_benefit": TARGET,
    "source_store_count": int(m.group(1).replace(",", "")) if m else None,
    "eligible_count": len(stores),
    "stores": stores
}

with open("data/colowide_stores.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(json.dumps({
    "source_store_count": out["source_store_count"],
    "eligible_count": out["eligible_count"]
}, ensure_ascii=False))
