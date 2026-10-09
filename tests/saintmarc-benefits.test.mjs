import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {saintmarcBenefitForStore} from '../saintmarc-benefit.js';

const company = JSON.parse(readFileSync(new URL('../data/issuers/saintmarc/config.json', import.meta.url),'utf8'));
const sample = (brand_name, name = brand_name + ' ○○店') => ({brand_name,name});

test('official rule matrix has 36 distinct entries and exact 25/11 split', () => {
  const rules=company.benefitRules.eligibleBrands;
  assert.equal(rules.length,36);
  assert.equal(rules.filter(x=>x.discountPercent===20).length,25);
  assert.equal(rules.filter(x=>x.discountPercent===10).length,11);
  assert.equal(new Set(rules.map(x=>x.name)).size,36);
});

test('displays 20% on known Saint Marc brands, including variants', () => {
  for (const brand of ['サンマルクカフェ','サンマルクカフェ＋R','鎌倉パスタ','BAQET','倉式珈琲店']) {
    assert.equal(saintmarcBenefitForStore(company,sample(brand))?.discountPercent,20,brand);
  }
});

test('displays 10% on official 10% brands, including apostrophe variants', () => {
  for (const brand of ['すし処函館市場','宝田水産','京都勝牛','Gottie’s BEEF','喫茶マドラグ']) {
    assert.equal(saintmarcBenefitForStore(company,sample(brand))?.discountPercent,10,brand);
  }
});

test('explicit exceptions are never eligible', () => {
  const names=[
    ['牛カツ京都勝牛','牛カツ京都勝牛 東京ドーム店'],
    ['京都勝牛','牛カツ京都勝牛 みずほPayPayドーム店'],
    ['NICK STOCK','NICK STOCK 東京ドーム店'],
    ['喫茶マドラグ','喫茶マドラグ 大丸神戸社員食堂店'],
    ['喫茶マドラグ','喫茶マドラグ 大丸梅田社員食堂店'],
  ];
  for(const [brand,name] of names) assert.equal(saintmarcBenefitForStore(company,sample(brand,name)),null,name);
});

test('unknown / ambiguous / empty brand is not assigned a percentage', () => {
  for(const brand of ['サンマルク','サンマルクカフェもどき','偽サンマルク','',null,'CoCo壱番屋']) {
    assert.equal(saintmarcBenefitForStore(company,sample(brand)),null,String(brand));
  }
  assert.equal(saintmarcBenefitForStore({...company,id:'royal'},sample('サンマルクカフェ')),null);
});

test('one brand selector remains one issuer; all 36 labels map to one benefit', () => {
  for(const rule of company.benefitRules.eligibleBrands){
    for(const alias of [rule.name,...(rule.variants||[])]){
      const found=saintmarcBenefitForStore(company,sample(alias));
      assert.equal(found?.discountPercent,rule.discountPercent,alias);
    }
  }
});
