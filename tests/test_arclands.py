import copy
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/issuers/arclands'))
from arclands_parser import parse_pages

class ArclandsTests(unittest.TestCase):
    def page(self):
        s=dict(code='1',name='かつや 札幌店',address_name='北海道札幌市中央区',coord={'lat':43.06,'lon':141.35},status='normal',categories=[{'code':'01'}],detail_groups=[{'flags':[{'details':[{'code':'00145','label':'株主優待券使用不可','value':False},{'code':'00146','label':'優待券テイクアウトのみ使用可','value':False}]}]}])
        stores=[dict(copy.deepcopy(s),code=str(i)) for i in range(600)]
        return [{'count':{'total':600,'offset':0,'limit':600},'items':stores}]
    def test_eligibility_and_takeout(self):
        p=self.page();s=p[0]['items']
        s[0]['detail_groups'][0]['flags'][0]['details'][0]['value']=True
        s[1]['detail_groups'][0]['flags'][0]['details'][1]['value']=True
        s[2]['code']='os600000' # Overseas directory placeholders can have Okinawa coordinates.
        s[3]['from_date']='2099-01-01T00:00:00+09:00'
        rows,excluded,total=parse_pages(p,date(2026,10,9))
        self.assertEqual(len(rows),597);self.assertEqual(total,600)
        self.assertEqual(len(excluded),3)
        self.assertIn('持帰りのみ',rows[0]['name'])
    def test_missing_page_preserves_database(self):
        p=self.page();p[0]['items'].pop()
        with self.assertRaises(ValueError):parse_pages(p,date.today())
    def test_unknown_voucher_schema_fails(self):
        p=self.page()
        for s in p[0]['items']:s['detail_groups']=[]
        with self.assertRaises(ValueError):parse_pages(p,date.today())
    def test_vending_machine_excluded(self):
        p=self.page();p[0]['items'][0]['detail_groups'][0]['flags'][0]['details'].append({'code':'00027','label':'券売機','value':True})
        rows,_,_=parse_pages(p,date.today());self.assertEqual(len(rows),599)
