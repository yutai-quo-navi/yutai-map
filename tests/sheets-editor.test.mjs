import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import crypto from 'node:crypto';
const code=fs.readFileSync(new URL('../tools/google-sheets/Code.gs',import.meta.url),'utf8');
function setup(){
 const c={Date,JSON,Array,Number,String,Set,isNaN};vm.createContext(c);vm.runInContext(code,c);
 const base={id:'old-2026',code:'9672',company_name:'東京都競馬',benefit_name:'サマーランド',research_year:'2026',research_month_number:'10',expiry_date:'2026-10-12',expiry_type:'利用期限',category:'leisure',status:'confirmed',checked_on:'2026-10-05',verification_method:'user'};
 const table=[Array.from(c.HEADERS),Array.from(c.FIELDS,k=>base[k]||'')];let locked=false;
 const s={getLastRow:()=>table.length,getRange:(row,col,n,m)=>({getValues:()=>table.slice(row-1,row-1+n).map(v=>v.slice(col-1,col-1+m)),setValues:values=>{for(let i=0;i<n;i++){table[row-1+i]||=[];values[i].forEach((v,j)=>table[row-1+i][col-1+j]=typeof v==='string'&&v.startsWith("'")?v.slice(1):v);}}})};
 c.SpreadsheetApp={getActiveSpreadsheet:()=>({getSheetByName:()=>s}),flush:()=>{}};
 c.LockService={getDocumentLock:()=>({waitLock:()=>{assert.equal(locked,false);locked=true;},releaseLock:()=>{locked=false;}})};
 c.Utilities={formatDate:d=>d.toISOString().slice(0,10),base64EncodeWebSafe:v=>Buffer.from(v).toString('base64url'),computeDigest:(_a,v)=>crypto.createHash('sha256').update(v).digest(),DigestAlgorithm:{SHA_256:'sha256'},Charset:{UTF_8:'utf8'},getUuid:()=>crypto.randomUUID()};
 return {c,table,get:()=>c.getEditorData().rows[0],base};
}
test('sorting does not change the record selected for correction',()=>{const{c,table,get}=setup();const original=get();table.push([...table[1]]);table[2][0]='other-id';table.reverse();table.unshift(table.pop());c.saveRecord({...original,benefit_name:'訂正版'});assert.equal(c.getEditorData().rows.find(r=>r.id===original.id).benefit_name,'訂正版');assert.equal(table.length,3);});
test('changing year retains the original record',()=>{const{c,get}=setup();const r=c.saveRecord({...get(),research_year:'2027',expiry_date:'2027-10-31'});assert.equal(r.keptPreviousYear,true);assert.equal(r.data.rows.length,2);assert.equal(r.data.rows.find(v=>v.id==='old-2026').expiry_date,'2026-10-12');});
test('month-only deadlines stay blank and round-trip to master CSV',()=>{const{c,get}=setup();c.saveRecord({...get(),expiry_date:''});assert.equal(get().expiry_date,'');assert.match(c.exportMasterCsv(),/"2026-10","利用期限"/);});
test('duplicates and concurrent edits are rejected without writes',()=>{const{c,get}=setup();const old=get();assert.throws(()=>c.saveRecord({...old,id:'',_version:''}),/既に/);c.saveRecord({...old,notes:'先に更新'});assert.throws(()=>c.saveRecord({...old,notes:'上書き'}),/別の編集/);assert.equal(get().notes,'先に更新');});
test('invalid dates and mismatched months are rejected',()=>{const{c,get}=setup();for(const date of ['2026-02-30','2026-11-01'])assert.throws(()=>c.saveRecord({...get(),expiry_date:date}),/期限日/);});
test('formula text is stored as literal content',()=>{const{c,get}=setup();c.saveRecord({...get(),notes:'=IMPORTXML("https://example.com")'});assert.equal(get().notes,'=IMPORTXML("https://example.com")');assert.equal(c.literal_('=1+2'),"'=1+2");});
test('X drafts contain only confirmed records and distinguish booking deadlines',()=>{const html=fs.readFileSync(new URL('../tools/google-sheets/Editor.html',import.meta.url),'utf8');const start=html.indexOf('function makeDraft('),end=html.indexOf('function download(',start);const context={data:{categories:{leisure:'サービス'},rows:[{research_month:'2026-10',expiry_date:'2026-10-31',status:'confirmed',category:'leisure',code:'6577',company_name:'クルーズ',benefit_name:'予約券',expiry_type:'予約期限',notes:'旅行日ではなく予約期限'},{research_month:'2026-10',status:'checking',category:'leisure',company_name:'要確認'}]}};vm.createContext(context);vm.runInContext(html.slice(start,end),context);const draft=context.makeDraft('2026-10');assert.match(draft,/10\/31まで／予約期限/);assert.match(draft,/旅行日ではなく予約期限/);assert.doesNotMatch(draft,/要確認/);});
