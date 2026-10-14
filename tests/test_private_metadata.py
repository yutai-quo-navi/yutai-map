import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('private_metadata', Path(__file__).resolve().parents[1] / 'tools/seo/private_metadata.py')
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


def release():
    return {'version': 1, 'issuer_id': 'zensho', 'generated_at': '2026-10-15T05:00:00+09:00',
            'brands': {'source': 'https://maps.zensho.co.jp/jp/shop.html', 'generated_at': '2026-10-15T05:00:00+09:00',
                       'eligible_filter': 'shareholder_coupon', 'brands': [{'name': 'すき家', 'eligible_store_count': 2003}]},
            'events': [{'event_id': 'new', 'issuer_id': 'zensho', 'kind': 'added', 'at': '2026-10-15T05:00:00+09:00'}]}


class PrivateMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data/issuers/zensho').mkdir(parents=True)
        self.updates = self.root / 'data/updates.json'
        self.updates.write_text(json.dumps({'version': 1, 'event_count': 1, 'events': [{'event_id': 'other', 'issuer_id': 'mos', 'at': '2026-10-12'}]}))

    def query(self, data):
        def get(sql, params):
            self.assertIn(params[0], metadata.ISSUERS)
            if params[0] != 'zensho': return []
            self.assertEqual(sql, 'SELECT current_meta_json FROM issuer_state WHERE issuer_id=?')
            return [{'current_meta_json': json.dumps(data)}]
        return get

    def test_public_history_merge_is_repeatable_and_preserves_other_issuers(self):
        query = self.query({'public_release': release()})
        metadata.publish_private_metadata(self.root, query)
        first = self.updates.read_text()
        self.assertEqual({e['event_id'] for e in json.loads(first)['events']}, {'new', 'other'})
        metadata.publish_private_metadata(self.root, query)
        self.assertEqual(first, self.updates.read_text())
        self.assertEqual(json.loads((self.root / 'data/issuers/zensho/brands.json').read_text())['brands'][0]['eligible_store_count'], 2003)

    def test_private_fields_and_foreign_issuer_fail_without_changes(self):
        for mutate in [lambda d: d.update(stores=[{}]),
                       lambda d: d['events'][0].update(issuer_id='mos'),
                       lambda d: d['brands'].update(raw_json='private')]:
            data = release()
            mutate(data)
            before = self.updates.read_text()
            with self.assertRaises(ValueError):
                metadata.publish_private_metadata(self.root, self.query({'public_release': data}))
            self.assertEqual(before, self.updates.read_text())
            self.assertFalse((self.root / 'data/issuers/zensho/brands.json').exists())

    def test_precutover_or_older_state_preserves_current_publication(self):
        before = self.updates.read_text()
        metadata.publish_private_metadata(self.root, self.query({}))
        self.assertEqual(before, self.updates.read_text())
        path = self.root / 'data/issuers/zensho/brands.json'
        path.write_text(json.dumps({'generated_at': '2026-10-16T05:00:00+09:00'}))
        metadata.publish_private_metadata(self.root, self.query({'public_release': release()}))
        self.assertEqual(before, self.updates.read_text())

    def test_generic_private_release_publishes_only_registered_public_files(self):
        data = {'version':2,'issuer_id':'zensho','generated_at':'2026-10-15T05:00:00+09:00',
                'events':release()['events'],'files':{'brands.json':{'brands':[{'name':'test','count':1}]}}}
        metadata.publish_private_metadata(self.root,self.query({'public_release':data}))
        self.assertEqual(json.loads((self.root/'data/issuers/zensho/brands.json').read_text())['brands'][0]['count'],1)
        for name, payload in [('current.json',{}),('brands.json',{'stores':[{'address':'private'}]})]:
            invalid=copy.deepcopy(data);invalid['files']={name:payload}
            with self.assertRaises(ValueError):metadata.validate_release('zensho',invalid)


if __name__ == '__main__':
    unittest.main()
