import test from 'node:test';
import assert from 'node:assert/strict';
import {voucherEntriesFromLedger} from '../expiry.js';

test('new issuer connects to confirmed ledger by code while retaining explicit links', () => {
  const base={id:'chimney',code:'3178',issuer_id:'',expiry_type:'利用期限',status:'confirmed',expiry_date:'2026-11-30'};
  const rows=[base,{...base,id:'explicit',issuer_id:'existing'},
    {...base,id:'unverified',status:'unconfirmed'}, {...base,id:'application',expiry_type:'申込期限'},
    {...base,id:'other',code:'9999'}];
  const original=structuredClone(rows);
  const linked=voucherEntriesFromLedger(rows,'利用期限',[{id:'chimney',code:'3178'}]);
  assert.deepEqual(linked.map(row=>[row.id,row.issuer]),[['chimney','chimney'],['explicit','existing']]);
  assert.deepEqual(rows,original);
});
