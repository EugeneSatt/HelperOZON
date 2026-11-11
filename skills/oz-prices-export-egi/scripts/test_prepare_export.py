"""Synthetic behavioral tests; never collect real marketplace data."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from prepare_export import prepare, parse_price, write_csv, BASE_DEFINITION

def fixture():
    return {'meta':{'region':'Тестовый город','started_at':'2026-10-28T10:00:00+03:00','finished_at':'2026-10-28T10:10:00+03:00','demo':True},
      'requests':[{'id':'r1','type':'sku','value':'1000000001'}],
      'sources':[{'id':'p','kind':'ozon_public_ui','captured_at':'2026-10-28T10:03:00+03:00','locator':'Synthetic card only','url':'https://example.com/public'},
                 {'id':'b','kind':'ozon_seller_ui','captured_at':'2026-10-28T10:02:00+03:00','locator':'Synthetic base only','url':'https://example.com/base'}],
      'rows':[{'request_ids':['r1'],'sku':'1000000001','title':'Условный товар, не рыночные данные','seller_id':'1001','seller_name':'Тестовый магазин','variant':'5 л, 1 шт.','identity_verified':True,'identity_source_id':'p','region':'Тестовый город','captured_at':'2026-10-28T10:03:00+03:00','status':'ok','url':'https://example.com/item',
        'other_banks':{'value':1000,'source_id':'p','label':'С другими банками'},'bank_offer':{'value':900,'source_id':'p','label':'С банками','includes_ozon_bank':True},
        'seller_base':{'value':1250,'source_id':'b','definition':BASE_DEFINITION,'sku':'1000000001','seller_id':'1001','variant':'5 л, 1 шт.','region':'Тестовый город','conditions_comparable':True}}]}

def store_fixture():
    d=fixture();d['requests']=[{'id':'r1','type':'store','value':'https://example.com/store','seller_id':'1001'}]
    d['catalogs']=[{'request_id':'r1','seller_id':'1001','source_id':'p','discovered_skus':['1000000001','1000000001'],'complete':True,'stop_reason':'end_of_catalog','expected_count':1}]
    return d

class PriceTests(unittest.TestCase):
    def test_bank_and_spp_are_independent(self):
        d=fixture();r=prepare(d)['rows'][0]
        self.assertEqual(r['spp_rate'],0.2)
        d['rows'][0]['bank_offer']['value']=500
        self.assertEqual(prepare(d)['rows'][0]['spp_rate'],0.2)
        self.assertNotIn('bank_discount_rate',r);self.assertNotIn('spp_rub',r)

    def test_missing_base_is_not_zero_or_card_difference(self):
        d=fixture();d['rows'][0]['seller_base']=None;r=prepare(d)['rows'][0]
        self.assertIsNone(r['spp_rate']);self.assertEqual(r['price_ozon_card'],900)

    def test_confirmed_zero_survives(self):
        d=fixture();d['rows'][0]['seller_base']['value']=1000;d['rows'][0]['bank_offer']['value']=1000
        r=prepare(d)['rows'][0];self.assertEqual(r['spp_rate'],0)

    def test_partner_bank_not_assumed_to_be_ozon(self):
        d=fixture();d['rows'][0]['bank_offer']['includes_ozon_bank']=None;r=prepare(d)['rows'][0]
        self.assertIsNone(r['price_ozon_card']);self.assertEqual(r['price_other_banks'],1000);self.assertEqual(r['status'],'partial')

    def test_base_binding_definition_and_conditions(self):
        for key,bad in [('sku','1000000002'),('seller_id','2'),('variant','1 л'),('region','Другой город'),('definition','crossed_out'),('conditions_comparable',False)]:
            d=fixture();d['rows'][0]['seller_base'][key]=bad
            r=prepare(d)['rows'][0];self.assertIsNone(r['spp_rate']);self.assertEqual(r['price_other_banks'],1000)

    def test_historical_base_not_used_as_current(self):
        d=fixture();d['sources'][1]['captured_at']='2026-10-27T10:00:00+03:00'
        self.assertIsNone(prepare(d)['rows'][0]['spp_rate'])

    def test_crossed_public_price_not_base(self):
        d=fixture();d['rows'][0]['seller_base']['source_id']='p';self.assertIsNone(prepare(d)['rows'][0]['spp_rate'])

    def test_unverified_offer_has_no_discounts(self):
        d=fixture();d['rows'][0]['identity_verified']=False;r=prepare(d)
        self.assertIsNone(r['rows'][0]['spp_rate']);self.assertFalse(r['coverage']['complete'])

    def test_negative_difference_not_clamped_to_discount(self):
        d=fixture();d['rows'][0]['seller_base']['value']=950;r=prepare(d)['rows'][0]
        self.assertAlmostEqual(r['spp_rate'],-50/950);self.assertIn('серая цена выше',r['spp_reason'])

    def test_missing_explicit_sku_stays_in_file(self):
        d=fixture();d['rows']=[];r=prepare(d)
        self.assertEqual(r['rows'][0]['sku'],'1000000001');self.assertEqual(r['rows'][0]['status'],'not_found');self.assertFalse(r['coverage']['complete'])

    def test_repeated_tiles_do_not_change_expected_unique_count(self):
        r=prepare(store_fixture());self.assertTrue(r['coverage']['complete']);self.assertEqual(r['coverage']['offers'],1)

    def test_catalog_limit_cannot_be_complete(self):
        d=store_fixture();d['catalogs'][0]['stop_reason']='page_limit'
        with self.assertRaises(ValueError):prepare(d)
        d['catalogs'][0]['complete']=False;self.assertFalse(prepare(d)['coverage']['complete'])

    def test_unprocessed_catalog_sku_gets_error_row(self):
        d=store_fixture();d['catalogs'][0]['discovered_skus'].append('1000000002');d['catalogs'][0]['expected_count']=2
        r=prepare(d);self.assertFalse(r['coverage']['complete']);self.assertEqual(next(x for x in r['rows'] if x['sku']=='1000000002')['status'],'load_error')

    def test_separate_sellers_and_variants_not_collapsed(self):
        d=fixture();r=copy.deepcopy(d['rows'][0]);r['seller_id']='1002';d['rows'].append(r)
        r=copy.deepcopy(d['rows'][0]);r['variant']='1 л';d['rows'].append(r)
        self.assertEqual(prepare(d)['coverage']['offers'],3)

    def test_latest_snapshot_keeps_all_request_bindings(self):
        d=fixture();r=copy.deepcopy(d['rows'][0]);r['captured_at']='2026-10-28T10:04:00+03:00';r['other_banks']['value']=1100;d['rows'].append(r)
        out=prepare(d);self.assertEqual(out['rows'][0]['price_other_banks'],1100);self.assertTrue(out['coverage']['warnings'])
        d['rows'][1]['captured_at']=d['rows'][0]['captured_at']
        with self.assertRaises(ValueError):prepare(d)

    def test_money_parser_preserves_decimal_and_rejects_mixed_values(self):
        self.assertEqual(parse_price('1\u202f234,50 ₽'),1234.5)
        for value in ['100 ₽/мес','от 100 ₽','100–200 ₽','10%','0 ₽']:
            with self.assertRaises(ValueError):parse_price(value)

    def test_invalid_prices_do_not_become_zero(self):
        for bad in [0,-1,0.001,1.001,float('nan'),float('inf'),True,'1000']:
            d=fixture();d['rows'][0]['other_banks']['value']=bad
            with self.assertRaises(ValueError):prepare(d)

    def test_csv_formula_injection_and_numbers(self):
        d=fixture();d['rows'][0]['title']=' =HYPERLINK("bad")';r=prepare(d)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'prices.csv';write_csv(r,p)
            with p.open(encoding='utf-8-sig') as f:values=list(csv.reader(f,delimiter=';'))
            self.assertTrue(values[1][2].startswith("'"));self.assertEqual(values[1][7],'900');self.assertEqual(values[1][9],'0,2')

    def test_same_sku_in_two_regions_is_not_collapsed(self):
        d=fixture();d['meta']['regions']=['Тестовый город','Другой город']
        other=copy.deepcopy(d['rows'][0]);other['region']='Другой город';other['other_banks']['value']=1100
        for row in [d['rows'][0],other]:row['seller_base']['regions']=d['meta']['regions']
        d['rows'].append(other);out=prepare(d)
        self.assertTrue(out['coverage']['complete']);self.assertEqual(len(out['rows']),2)
        self.assertEqual({r['region']:r['spp_rate'] for r in out['rows']},{'Тестовый город':0.2,'Другой город':0.12})

    def test_missing_region_stays_as_error_row(self):
        d=fixture();d['meta']['regions']=['Тестовый город','Другой город'];out=prepare(d)
        self.assertEqual(len(out['rows']),2);self.assertFalse(out['coverage']['complete'])
        self.assertEqual(next(r for r in out['rows'] if r['region']=='Другой город')['status'],'not_found')

    def test_price_cap_and_seller_url_binding(self):
        d=fixture();r=d['rows'][0];r.pop('seller_id');r['seller_url']='https://example.com/seller'
        r['seller_base'].update(seller_url=r['seller_url'],definition='seller_price_cap',label='Предельная цена, руб.')
        out=prepare(d)['rows'][0];self.assertEqual(out['spp_rate'],0.2)
        self.assertEqual(out['cabinet_field'],'Предельная цена, руб.')

    def test_stale_cabinet_visible_but_spp_blank(self):
        d=fixture();d['sources'][1]['captured_at']='2026-10-27T10:00:00+03:00'
        r=prepare(d)['rows'][0];self.assertEqual(r['seller_base_price'],1250)
        self.assertIsNone(r['spp_rate']);self.assertEqual(r['cabinet_captured_at'],'2026-10-27T10:00:00+03:00')

if __name__=='__main__':
    import sys
    if len(sys.argv)==3 and sys.argv[1]=='--fixture':
        d=fixture();d['requests']=[];d['rows']=[]
        for i in range(5):
            sk=str(1000000001+i);rid='r'+str(i+1);d['requests'].append({'id':rid,'type':'sku','value':sk})
            row=copy.deepcopy(fixture()['rows'][0]);row.update(request_ids=[rid],sku=sk)
            row['seller_base']['sku']=sk
            if i==1:row['seller_base']=None;row['bank_offer']['includes_ozon_bank']=None
            if i==2:row['bank_offer']=None
            if i==3:row['seller_base']['value']=1000;row['bank_offer']['value']=1000
            if i==4:row.update(status='unavailable',notes='Синтетический пример: нет в наличии',other_banks=None,bank_offer=None,seller_base=None)
            d['rows'].append(row)
        Path(sys.argv[2]).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    else:unittest.main()
