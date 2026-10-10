"""Verified static benefit guides. No scraping; never query nationwide store tables."""
import argparse
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://yutai-quo-navi.github.io/yutai-map/'
ACCOUNT = 'c5ff1bbead14c4535c94e507b5ae00e6'
DATABASE = '4540cbaa-3214-4111-9c7a-11e18fd067db'
STATE = 'data/seo/brand-state.json'
MANIFEST = 'data/seo/pages.json'
MARK = '__SEO_LASTMOD__'


def read(path, fallback=None):
    return json.loads(path.read_text()) if path.exists() else fallback


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def safe_url(value):
    value = str(value or '')
    parsed = urllib.parse.urlsplit(value)
    return value if parsed.scheme == 'https' and parsed.hostname and not parsed.username else ''


def esc(value):
    return html.escape(str(value or ''), quote=True)


def link(url, label):
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def public_configs(root):
    issuers = []
    for item in read(root / 'data/issuers/index.json')['issuers']:
        if item.get('status') != 'public':
            continue
        path = (root / item['config'].removeprefix('./')).resolve()
        if not path.is_relative_to((root / 'data/issuers').resolve()):
            raise ValueError('Unsafe issuer configuration path')
        config = read(path)
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', config.get('id', '')):
            raise ValueError('Invalid published issuer ID')
        if config.get('status') != 'public' or config['id'] != item['id']:
            raise ValueError('Issuer manifest/config mismatch')
        issuers.append({**config, 'name': item['name']})
    features = [f for f in read(root / 'data/features/index.json')['features']
                if f.get('section') == 'hotel' and f.get('status') == 'public']
    if any(not re.fullmatch(r'[a-z][a-z0-9-]{0,79}', f.get('id', '')) for f in features):
        raise ValueError('Invalid published hotel benefit ID')
    return issuers, features


class D1:
    def __init__(self):
        self.token = os.environ.get('CF_API_TOKEN', '').strip()
        if not self.token:
            raise RuntimeError('CF_API_TOKEN is required')
        self.rows_read = 0

    def __call__(self, sql, params=None):
        body = json.dumps({'sql': sql, 'params': params or []}).encode()
        request = urllib.request.Request(
            f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/d1/database/{DATABASE}/query',
            data=body, headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.load(response)
        if not data.get('success') or any(not r.get('success') for r in data['result']):
            raise RuntimeError('D1 source read failed; existing guides are preserved')
        self.rows_read += sum(r.get('meta', {}).get('rows_read', 0) for r in data['result'])
        return [row for result in data['result'] for row in result['results']]


def collect(root, query):
    issuers, features = public_configs(root)
    previous = read(root / STATE, {'version': 1, 'issuers': {}})
    # Existing trigger-maintained counters: ~20 rows, no stores/reference_stores scan.
    stats = {row['issuer_id']: row for row in query('SELECT issuer_id,catalog_revision,geo_count,reference_count FROM issuer_stats')}
    state = {'version': 1, 'issuers': {}}
    refreshed = False
    for config in issuers:
        issuer = config['id']
        current = stats.get(issuer)
        if not current:
            if config.get('catalogBrands'):
                # Explicit reviewed labels for OpenPOI-only issuers; never invent counts.
                state['issuers'][issuer] = {'revision': 'config:' + digest(json.dumps(config['catalogBrands'], ensure_ascii=False)),
                                          'brands': [{'brand_name': name, 'store_count': None} for name in config['catalogBrands']]}
                continue
            raise ValueError(f'Missing published issuer statistics: {issuer}')
        revision = current['catalog_revision']
        cached = previous.get('issuers', {}).get(issuer)
        if cached and cached['revision'] == revision:
            brands = cached['brands']
        else:
            refreshed = True
            brands = query('SELECT brand_name,store_count FROM brand_catalog WHERE issuer_id=? AND store_count>0 ORDER BY brand_name', [issuer])
        # Existing triggers exclude unnamed brands; issuer totals include them.
        # Use only named catalogue counts, without inventing the missing labels.
        if any(not b['brand_name'] or b['store_count'] <= 0 for b in brands) or sum(b['store_count'] for b in brands) > current['geo_count'] + current['reference_count']:
            raise ValueError(f'Incomplete brand projection: {issuer}')
        state['issuers'][issuer] = {'revision': revision, 'brands': brands}
    # A hotel catalogue is ALREADY stored as one snapshot per voucher. Only ~13 rows.
    snapshots = {row['feature_id']: json.loads(row['payload_json']) for row in query('SELECT feature_id,payload_json FROM feature_snapshots')}
    projected = []
    for config in features:
        snapshot = snapshots.get(config['id']) if config.get('updateMode') == 'scheduled' else config
        if not snapshot or not snapshot.get('stores') or not snapshot.get('checkedOn'):
            raise ValueError(f'Missing verified hotel snapshot: {config["id"]}')
        stores = []
        ids = set()
        for store in snapshot['stores']:
            if not store.get('verified') or not store.get('id') or not store.get('name') or not store.get('address'):
                raise ValueError('Unverified or incomplete hotel; preserve previous publication')
            if store['id'] in ids:
                raise ValueError('Duplicate hotel ID')
            ids.add(store['id'])
            # Public guide fields only. No coordinates, raw payloads, collection internals.
            stores.append({key: store.get(key, '') for key in ['id', 'name', 'address', 'conditions', 'sourceUrl', 'eligibilitySourceUrl']})
        projected.append({**config, 'checkedOn': snapshot['checkedOn'], 'stores': stores})
    # Detect a collector finishing mid-build before committing a mismatched brand projection.
    if refreshed and stats != {row['issuer_id']: row for row in query('SELECT issuer_id,catalog_revision,geo_count,reference_count FROM issuer_stats')}:
        raise RuntimeError('Brand catalogue changed during generation; retry on the next run')
    return {'issuers': issuers, 'features': projected, 'state': state}


def search_url(**params):
    return BASE + '?' + urllib.parse.urlencode(params)


def issuer_path(issuer):
    return f'guides/dining/issuers/{issuer}/index.html'


def brand_path(issuer, brand):
    return f'guides/dining/brands/{issuer}/{digest(brand)[:16]}/index.html'


def feature_path(feature):
    return f'guides/hotels/benefits/{feature}/index.html'


def hotel_path(feature, store):
    return f'guides/hotels/hotels/{feature}/{digest(store["id"])[:16]}/index.html'


def url(path):
    return BASE + path.removesuffix('index.html')


def page(path, title, description, body, crumbs, entity=None):
    breadcrumbs = [{'@type': 'ListItem', 'position': i + 1, 'name': name, 'item': target}
                   for i, (name, target) in enumerate([('店舗検索', BASE), *crumbs])]
    graph = [{'@type': 'WebPage', '@id': url(path), 'url': url(path), 'name': title,
              'description': description, 'inLanguage': 'ja', 'dateModified': MARK},
             {'@type': 'BreadcrumbList', 'itemListElement': breadcrumbs}]
    if entity:
        graph.append(entity)
    structured = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    # Hash the JSON-LD after date substitution at publish time.
    relative = '../' * (len(Path(path).parts) - 1)
    crumb_html = ' / '.join(link(target, name) for name, target in [('店舗検索', BASE), *crumbs])
    return f'''<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' https://www.googletagmanager.com __JSONLD_CSP__; style-src 'self'; img-src 'self' data: https://*.google-analytics.com https://www.googletagmanager.com; connect-src 'self' https://www.googletagmanager.com https://*.google-analytics.com https://*.google.com; object-src 'none'; base-uri 'none'; form-action 'self'; frame-src 'none'; upgrade-insecure-requests">
<meta name="referrer" content="strict-origin-when-cross-origin"><meta name="robots" content="index,follow">
<title>{esc(title)}｜株主優待のお店検索</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{url(path)}">
<meta property="og:type" content="article"><meta property="og:locale" content="ja_JP"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{url(path)}">
<meta name="twitter:card" content="summary"><meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(description)}">
<link rel="stylesheet" href="{relative}guide.css?v=20261011"><script type="application/ld+json">{structured}</script>
<script type="module" src="{relative}analytics.js?v=20261011"></script>
</head><body><header><a class="site-name" href="{BASE}">株主優待のお店検索</a><nav aria-label="ガイド">{link(url('guides/dining/index.html'), '優待・ブランドガイド')} {link(url('guides/hotels/index.html'), '宿泊優待ガイド')}</nav></header>
<main><nav class="breadcrumbs" aria-label="パンくず">{crumb_html}</nav><article><h1>{esc(title)}</h1><p class="lead">{esc(description)}</p>{body}</article>
<aside class="notice"><p>掲載情報は変更される場合があります。利用・予約前に各社公式情報とお手持ちの券面をご確認ください。対象施設の掲載は予約の可否を保証しません。</p></aside></main>
<footer>{link(BASE, '近くの優待店を検索')} {link(BASE + 'privacy.html', 'プライバシー')}<p>運営：<a href="https://x.com/yutai_samurai">優待サムライ</a></p></footer></body></html>
'''


def sources(*pairs):
    links = [link(safe_url(target), label) for target, label in pairs if safe_url(target)]
    return '<h2>公式情報</h2><ul>' + ''.join(f'<li>{item}</li>' for item in links) + '</ul>'


def ul(items):
    return '<ul class="guide-list">' + ''.join(f'<li>{item}</li>' for item in items) + '</ul>'


def render(source):
    pages = {}
    dining = 'guides/dining/index.html'
    hotels = 'guides/hotels/index.html'
    issuer_links = []
    # Do not copy operational config notes into product copy.
    for issuer in source['issuers']:
        iid, name = issuer['id'], issuer['name']
        entry = source['state']['issuers'][iid]
        brands = entry['brands']
        ipath = issuer_path(iid)
        total = sum(b['store_count'] or 0 for b in brands)
        count_label = f'掲載{total:,}店舗' if all(b['store_count'] is not None for b in brands) else '店舗件数の集計なし'
        issuer_links.append(link(url(ipath), name) + f' <span>{len(brands)}ブランド・{count_label}</span>')
        links = [link(url(brand_path(iid, b['brand_name'])), b['brand_name']) + (' <span>対象店舗を検索</span>' if b['store_count'] is None else f' <span>掲載{b["store_count"]:,}店舗</span>') for b in brands]
        text = f'{name}（{issuer["code"]}）の株主優待に対応する掲載ブランドと店舗件数を確認し、近くのお店を検索できます。'
        body = f'<p><a class="cta" href="{esc(search_url(issuer=iid))}">{esc(name)}の対象店を探す</a></p><h2>掲載ブランド</h2>' + ul(links)
        body += '<h2>利用前に確認すること</h2><p>優待の種類、券面の有効期限、対象外店舗、利用上限や併用条件は公式案内をご確認ください。掲載件数はこのサイトの検索対象件数です。</p>'
        body += sources((issuer.get('sourceUrl'), '株主優待の公式案内'), (issuer.get('storeSearchUrl'), '公式店舗検索'))
        pages[ipath] = page(ipath, name + 'の株主優待・対象ブランド', text, body, [('優待・ブランドガイド', url(dining)), (name, url(ipath))])
        for brand in brands:
            bname, count = brand['brand_name'], brand['store_count']
            count_text = f'{count:,}店舗' if count is not None else '集計なし（公式店舗検索で確認）'
            bpath = brand_path(iid, bname)
            title = bname + 'で使える株主優待・対象店の探し方'
            description = f'{bname}は{name}の優待で検索できる掲載ブランドです。近くの対象店舗の探し方と、利用前の公式確認先を案内します。'
            body = f'<h2>対応する優待会社</h2><p>{link(url(ipath), name)}（証券コード：{esc(issuer["code"])}）</p><p>このブランドの掲載件数：<strong>{esc(count_text)}</strong>。同じブランドでも対象外店舗があるため、ブランド名だけで利用可否を判断せず、対象店舗と券面を確認してください。</p><p><a class="cta" href="{esc(search_url(issuer=iid, brand=bname))}">{esc(bname)}の対象店を探す</a></p>'
            note = issuer.get('note', '')
            if note and not any(word in note for word in ['DB', 'API', '定期取得', '分割取得', '月次', '正本']):
                body += '<h2>利用時の注意</h2><p>' + esc(note) + '</p>'
            rules = issuer.get('benefitRules', {}).get('eligibleBrands', [])
            rule = next((r for r in rules if bname in [r['name'], *r.get('variants', [])]), None)
            if rule and rule.get('discountPercent'):
                body += f'<h2>掲載されている優待内容</h2><p>株主様ご優待カードによる{int(rule["discountPercent"])}％割引。対象店舗・適用条件は公式案内をご確認ください。</p>'
            body += '<h2>近くの対象店舗を探す手順</h2><ol><li>上の検索リンクから、この会社・ブランドを選択した画面を開く。</li><li>現在地、または行きたい場所を指定して検索する。</li><li>対象店舗を確認し、利用前に公式案内と券面の条件を確認する。</li></ol>'
            body += sources((issuer.get('sourceUrl'), name + 'の株主優待案内'), (issuer.get('storeSearchUrl'), '公式店舗検索'))
            body += '<h2>同じ優待で探せるブランド</h2>' + ul(link(url(brand_path(iid, b['brand_name'])), b['brand_name']) for b in brands if b['brand_name'] != bname)
            pages[bpath] = page(bpath, title, description, body, [('優待・ブランドガイド', url(dining)), (name, url(ipath)), (bname, url(bpath))])
    pages[dining] = page(dining, '優待・ブランドガイド', '掲載中の優待会社とブランドから、株主優待が使える対象店の探し方や公式確認先を調べられます。', '<h2>優待会社から選ぶ</h2>' + ul(issuer_links), [('優待・ブランドガイド', url(dining))])
    feature_links = []
    for feature in source['features']:
        fid, name = feature['id'], feature.get('shortName') or feature['issuer']['name']
        fpath = feature_path(fid)
        stores = feature['stores']
        feature_links.append(link(url(fpath), name) + f' <span>掲載{len(stores)}施設</span>')
        intro = feature.get('description', '')
        body = f'<h2>利用する優待</h2><p>{esc(feature.get("voucherName") or feature["title"])}</p><p>{esc(intro)}</p><p>対象施設の確認日：<time>{esc(feature["checkedOn"])}</time></p><p><a class="cta" href="{esc(search_url(section="hotel", feature=fid))}">この宿泊優待で探す</a></p><h2>掲載ホテル・施設</h2>'
        body += ul(link(url(hotel_path(fid, s)), s['name']) + '<br><span>' + esc(s['address']) + '</span>' for s in stores)
        body += sources((feature.get('sourceUrl'), '株主優待の公式案内'))
        pages[fpath] = page(fpath, name + 'の宿泊優待・対象ホテル', f'{name}の宿泊優待に対応する掲載{len(stores)}施設の住所・利用条件・公式確認先を案内します。', body, [('宿泊優待ガイド', url(hotels)), (name, url(fpath))])
        for store in stores:
            path = hotel_path(fid, store)
            title = store['name'] + '｜' + name + 'の宿泊優待'
            description = f'{store["name"]}での{name}の宿泊優待について、所在地・予約時の注意・公式確認先を案内します。'
            body = f'<h2>所在地</h2><p>{esc(store["address"])}</p><h2>利用する優待</h2><p>{link(url(fpath), name)}：{esc(feature.get("voucherName") or feature["title"])}</p><h2>予約・利用条件</h2><p>{esc(store.get("conditions") or intro)}</p>'
            if store.get('conditions') and store['conditions'] != intro:
                body += f'<h3>優待全体の案内</h3><p>{esc(intro)}</p>'
            body += f'<p>対象施設の確認日：<time>{esc(feature["checkedOn"])}</time>。券の利用期限は、お手持ちの券面をご確認ください。</p><p><a class="cta" href="{esc(search_url(section="hotel", feature=fid))}">この優待のホテルを検索</a></p>'
            body += sources((store.get('sourceUrl'), store['name'] + 'の公式サイト'), (store.get('eligibilitySourceUrl') or feature.get('sourceUrl'), '株主優待の公式案内'))
            map_url = 'https://www.google.com/maps/search/?' + urllib.parse.urlencode({'api': 1, 'query': store['name'] + ' ' + store['address']})
            body += '<p>' + link(map_url, '所在地を地図で確認') + '</p><h2>同じ宿泊優待の施設</h2><p>' + link(url(fpath), name + 'のホテル一覧に戻る') + '</p>'
            entity = {'@type': 'LodgingBusiness', '@id': url(path) + '#hotel', 'name': store['name'], 'address': {'@type': 'PostalAddress', 'streetAddress': store['address'], 'addressCountry': 'JP'}}
            official = safe_url(store.get('sourceUrl'))
            if official:
                entity['sameAs'] = official
            pages[path] = page(path, title, description, body, [('宿泊優待ガイド', url(hotels)), (name, url(fpath)), (store['name'], url(path))], entity)
    pages[hotels] = page(hotels, '宿泊優待ガイド', '株主優待で宿泊できる掲載ホテル・施設を、優待の種類から確認できます。予約方法、現地決済などの条件と公式情報を案内します。', '<h2>宿泊優待から選ぶ</h2>' + ul(feature_links), [('宿泊優待ガイド', url(hotels))])
    return pages


def publish(root, source, today=None):
    import base64
    today = today or datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    pages = render(source)  # Complete validation/render BEFORE modifying existing publication.
    previous = read(root / MANIFEST, {'pages': {}})['pages']
    manifest = {}
    for path, content in pages.items():
        hashed = digest(content)
        old = previous.get(path, {})
        lastmod = old.get('lastmod') if old.get('hash') == hashed else today
        content = content.replace(MARK, lastmod)
        structured = re.search(r'<script type="application/ld\+json">(.*?)</script>', content, re.S).group(1)
        csp_hash = base64.b64encode(hashlib.sha256(structured.encode()).digest()).decode()
        content = content.replace('__JSONLD_CSP__', f"'sha256-{csp_hash}'")
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text() != content:
            target.write_text(content)
        manifest[path] = {'hash': hashed, 'lastmod': lastmod}
    for removed in previous.keys() - pages.keys():
        target = root / removed
        if target.is_relative_to(root / 'guides') and target.name == 'index.html':
            target.unlink(missing_ok=True)
    (root / 'data/seo').mkdir(parents=True, exist_ok=True)
    (root / STATE).write_text(json.dumps(source['state'], ensure_ascii=False, indent=2) + '\n')
    (root / MANIFEST).write_text(json.dumps({'version': 1, 'pages': manifest}, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    entries = [f'<url><loc>{BASE}</loc></url>'] + [f'<url><loc>{esc(url(path))}</loc><lastmod>{m["lastmod"]}</lastmod></url>' for path, m in sorted(manifest.items())]
    (root / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(entries) + '\n</urlset>\n')
    print(json.dumps({'pages': len(pages), 'removed': len(previous.keys() - pages.keys())}))
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    query = D1()
    source = collect(args.root, query)
    publish(args.root, source)
    record = f'SEO generation: D1 rows_read={query.rows_read}; rows_written=0. No nationwide store scan.\n'
    print(record)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write(record)


if __name__ == '__main__':
    main()
