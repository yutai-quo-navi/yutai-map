import copy
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

spec = importlib.util.spec_from_file_location('seo_guides', Path(__file__).resolve().parents[1] / 'tools/seo/build_guides.py')
seo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seo)


def fixture():
    return {'issuers': [{'id': 'sample', 'code': '0000', 'name': '見本会社', 'status': 'public', 'sourceUrl': 'https://example.com/benefits'}],
            'state': {'version': 1, 'issuers': {'sample': {'revision': 1, 'brands': [{'brand_name': '和食 <見本>', 'store_count': 4}]}}},
            'features': [{'id': 'sample-hotels', 'shortName': '見本宿泊', 'title': '宿泊券', 'voucherName': '宿泊割引券', 'section': 'hotel', 'status': 'public', 'updateMode': 'scheduled', 'issuer': {'id': 'sample', 'name': '見本会社', 'code': '0000'}, 'description': '電話予約・現地払い。', 'sourceUrl': 'https://example.com/benefits', 'checkedOn': '2026-10-10', 'stores': [{'id': 'hotel-1', 'name': '見本ホテル', 'address': '東京都見本町1', 'conditions': '事前決済は対象外。', 'sourceUrl': 'https://example.com/hotel'}]}]}


class SeoGuidesTest(unittest.TestCase):
    def test_unchanged_lastmod_and_removal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = fixture()
            original = seo.publish(root, source, '2026-10-11')
            again = seo.publish(root, source, '2026-10-12')
            self.assertEqual(original, again)
            hotel = seo.hotel_path('sample-hotels', source['features'][0]['stores'][0])
            source['features'][0]['stores'] = []
            source['state']['issuers']['sample']['brands'] = [{'brand_name': '新しい店', 'store_count': 5}]
            new = seo.publish(root, source, '2026-10-13')
            self.assertFalse((root / hotel).exists())
            self.assertFalse((root / seo.brand_path('sample', '和食 <見本>')).exists())
            self.assertTrue((root / seo.brand_path('sample', '新しい店')).exists())
            self.assertNotIn(seo.url(hotel), (root / 'sitemap.xml').read_text())
            self.assertEqual(new['guides/hotels/index.html']['lastmod'], '2026-10-13')
            ElementTree.parse(root / 'sitemap.xml')

    def test_links_escape_canonical_jsonld_and_csp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = fixture()
            seo.publish(root, source, '2026-10-11')
            pages = list(root.glob('guides/**/index.html'))
            self.assertEqual(len(pages), 6)
            for path in pages:
                content = path.read_text()
                structured = re.search(r'<script type="application/ld\+json">(.*?)</script>', content, re.S).group(1)
                data = json.loads(structured)
                self.assertEqual(data['@graph'][0]['dateModified'], '2026-10-11')
                self.assertNotIn('__SEO_', content)
                self.assertIn("'sha256-", content)
                self.assertIn(seo.url(path.relative_to(root).as_posix()), content)
                for target in re.findall(r'href="([^"]+)"', content):
                    if target.startswith(seo.BASE + 'guides/'):
                        self.assertTrue((root / target.removeprefix(seo.BASE) / 'index.html').exists(), target)
            brand = (root / seo.brand_path('sample', '和食 <見本>')).read_text()
            self.assertIn('和食 &lt;見本&gt;', brand)
            self.assertIn('issuer=sample&amp;brand=', brand)
            self.assertNotIn('href="javascript:', brand)
            self.assertEqual(seo.safe_url('javascript:alert(1)'), '')
            self.assertEqual(seo.safe_url('https://user:password@example.com'), '')

    def configure(self, root, source):
        p = root / 'data/issuers/sample'
        p.mkdir(parents=True)
        (p / 'config.json').write_text(json.dumps(source['issuers'][0]))
        (root / 'data/issuers/index.json').write_text(json.dumps({'issuers': [{**source['issuers'][0], 'config': './data/issuers/sample/config.json'}]}))
        p = root / 'data/features'
        p.mkdir(parents=True)
        (p / 'index.json').write_text(json.dumps({'features': source['features']}))

    def test_only_changed_brand_aggregate_read_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = fixture()
            self.configure(root, source)
            calls = []
            snapshot = copy.deepcopy(source['features'][0])
            snapshot['stores'][0]['verified'] = True
            stats = [{'issuer_id': 'sample', 'catalog_revision': 1, 'geo_count': 4, 'reference_count': 0}]
            def query(sql, params=None):
                calls.append(sql)
                self.assertNotRegex(sql, r'\b(?:stores|store_raw|reference_stores)\b')
                if 'issuer_stats' in sql: return stats
                if 'brand_catalog' in sql: return source['state']['issuers']['sample']['brands']
                if 'feature_snapshots' in sql: return [{'feature_id': 'sample-hotels', 'payload_json': json.dumps(snapshot)}]
                raise AssertionError(sql)
            collected = seo.collect(root, query)
            seo.publish(root, collected, '2026-10-11')
            calls.clear()
            cached = seo.collect(root, query)
            self.assertEqual(len(calls), 2)
            self.assertNotIn('brand_catalog', '\n'.join(calls))
            self.assertNotIn('lat', cached['features'][0]['stores'][0])
            # Unnamed stores are intentionally absent from the trigger-maintained catalogue.
            stats[0]['reference_count'] = 14
            seo.collect(root, query)
            stats[0]['geo_count'] = 0
            stats[0]['reference_count'] = 3
            with self.assertRaises(ValueError): seo.collect(root, query)
            stats[0]['geo_count'] = 4
            stats[0]['reference_count'] = 0
            saved = (root / 'sitemap.xml').read_text()
            snapshot['stores'][0]['verified'] = False
            with self.assertRaises(ValueError): seo.collect(root, query)
            self.assertEqual(saved, (root / 'sitemap.xml').read_text())

    def test_openpoi_only_brand_uses_reviewed_labels_without_inventing_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = fixture()
            source['issuers'][0]['catalogBrands'] = ['和食 <見本>']
            self.configure(root, source)
            snapshot = copy.deepcopy(source['features'][0])
            snapshot['stores'][0]['verified'] = True
            def query(sql, params=None):
                if 'issuer_stats' in sql: return []
                if 'feature_snapshots' in sql: return [{'feature_id': 'sample-hotels', 'payload_json': json.dumps(snapshot)}]
                raise AssertionError('Unexpected D1 catalogue query')
            collected = seo.collect(root, query)
            self.assertIsNone(collected['state']['issuers']['sample']['brands'][0]['store_count'])
            seo.publish(root, collected, '2026-10-11')
            brand = (root / seo.brand_path('sample', '和食 <見本>')).read_text()
            self.assertIn('集計なし', brand)
            self.assertNotIn('0店舗', brand)


if __name__ == '__main__':
    unittest.main()
