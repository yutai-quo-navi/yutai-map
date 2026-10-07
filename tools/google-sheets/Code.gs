/** Imported Google Sheet → bound Apps Script editor. No deletion or external writes. */
var DB_NAME = '期限DB';
var FIELDS = ['id','code','company_name','benefit_name','research_year','research_month_number','expiry_date','expiry_type','category','brands','source_url','checked_on','status','notes','issue','secondary_source_url','issuer_id','search_brand','emoji','verification_method'];
var HEADERS = ['管理ID','証券コード','会社名','優待名称','期限年','期限月','期限日','期限種別','カテゴリ','利用可能ブランド','公式URL','最終確認日','確認状態','備考','対象発行回','二次情報URL','店舗検索会社ID','検索ブランド','Xアイコン','確認経路'];
var CSV_FIELDS = ['id','code','company_name','benefit_name','issue','expiry_date','research_month','expiry_type','category','brands','source_url','secondary_source_url','checked_on','status','notes','issuer_id','search_brand','emoji','verification_method'];
var CATEGORIES = {dining:'外食・飲食系',shopping:'買物・割引系',leisure:'サービス・レジャー系',catalog:'カタログ・申込期限',other:'その他'};
var TYPES = ['利用期限','申込期限','登録期限','予約期限','ポイント失効','交換期限','受取期限'];
var ISSUERS = {skylark:'3197',colowide:'7616',create:'3387',zensho:'7550',toridoll:'3397',foodlife:'3563',yoshinoya:'9861',mcd:'2702',monogatari:'3097',kyoritsu:'9616'};

function onOpen() { SpreadsheetApp.getUi().createMenu('優待期限').addItem('編集画面を開く','openEditor').addToUi(); }
function openEditor() { SpreadsheetApp.getUi().showModelessDialog(HtmlService.createHtmlOutputFromFile('Editor').setWidth(1200).setHeight(780),'優待期限の編集'); }
function today_() { return Utilities.formatDate(new Date(),'Asia/Tokyo','yyyy-MM-dd'); }
function sheet_() {
  var s = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(DB_NAME);
  if (!s) throw new Error('「期限DB」シートが見つかりません。移行ファイルを読み込んでください。');
  if (JSON.stringify(s.getRange(1,1,1,HEADERS.length).getValues()[0]) !== JSON.stringify(HEADERS)) throw new Error('列名・列順が違います。1行目を元に戻してください。');
  return s;
}
function token_(r) { return Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,JSON.stringify(FIELDS.map(function(k){return r[k] || ''; })),Utilities.Charset.UTF_8)); }
function rows_(s) {
  if (s.getLastRow()<2) return [];
  return s.getRange(2,1,s.getLastRow()-1,HEADERS.length).getValues().map(function(values,index) {
    var r = {};
    FIELDS.forEach(function(k,i) { var v=values[i]; r[k] = v instanceof Date ? Utilities.formatDate(v,'Asia/Tokyo','yyyy-MM-dd') : String(v == null ? '' : v).trim(); });
    r.research_month = r.research_year+'-'+('0'+r.research_month_number).slice(-2);
    r._row = index+2; r._version=token_(r); return r;
  }).filter(function(r){return !!r.id;});
}
function getEditorData() { return {rows:rows_(sheet_()),today:today_(),categories:CATEGORIES,types:TYPES}; }
function dateValid_(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  var d=new Date(value+'T00:00:00Z'); return !isNaN(d.getTime()) && d.toISOString().slice(0,10)===value;
}
function normalize_(input) {
  var r={}; FIELDS.forEach(function(k){r[k]=String(input[k] == null ? '' : input[k]).trim();});
  r.code=r.code.normalize('NFKC').toUpperCase();
  var y=Number(r.research_year), m=Number(r.research_month_number);
  if (!/^[0-9]{3}[0-9A-Z]$/.test(r.code)) throw new Error('証券コードは4桁で入力してください。');
  if (!r.company_name || !r.benefit_name) throw new Error('会社名と優待名称を入力してください。');
  if (!Number.isInteger(y)||y<2000||y>2199||!Number.isInteger(m)||m<1||m>12) throw new Error('期限の年・月を入力してください。');
  r.research_year=String(y); r.research_month_number=String(m); r.research_month=y+'-'+('0'+m).slice(-2);
  if (r.expiry_date && (!dateValid_(r.expiry_date)||r.expiry_date.slice(0,7)!==r.research_month)) throw new Error('期限日は指定した年・月の日付にしてください。日が不明なら空欄にできます。');
  if (TYPES.indexOf(r.expiry_type)<0 || !CATEGORIES[r.category] || ['confirmed','checking','secondary'].indexOf(r.status)<0) throw new Error('種別・カテゴリ・確認状態を選択してください。');
  r.checked_on=r.checked_on||today_(); r.verification_method=r.verification_method||'user';
  if (!dateValid_(r.checked_on)) throw new Error('最終確認日が不正です。');
  ['source_url','secondary_source_url'].forEach(function(k){if(r[k]&&!/^https?:\/\/[^\s/]+(?:\/[^\s]*)?$/.test(r[k])) throw new Error('出典はhttp(s)のURLで入力してください。');});
  if(['user','official'].indexOf(r.verification_method)<0) throw new Error('確認経路が不正です。');
  if(r.status==='secondary'&&!r.secondary_source_url) throw new Error('二次情報URLを入力してください。');
  if(r.status==='confirmed'&&r.verification_method==='official'&&(!r.expiry_date||!r.source_url||!r.issue)) throw new Error('公式確認には期限日・公式URL・対象発行回を入力してください。');
  r.brands=Array.from(new Set(r.brands.split('|').map(function(b){return b.trim();}).filter(Boolean))).join('|');
  if(r.issuer_id&&ISSUERS[r.issuer_id]!==r.code) throw new Error('店舗検索会社IDと証券コードが一致しません。対象外の会社は空欄で保存できます。');
  if(r.search_brand&&(!r.issuer_id||r.brands.split('|').indexOf(r.search_brand)<0)) throw new Error('検索ブランドは会社IDと利用可能ブランドも必要です。');
  return r;
}
function key_(r) {return JSON.stringify([r.code,r.benefit_name,r.issue,r.expiry_type,r.expiry_date||r.research_month]);}
function literal_(v) { return /^[=+\-@]/.test(String(v)) ? "'"+v : v; }
function saveRecord(input) {
  var lock=LockService.getDocumentLock(); lock.waitLock(20000);
  try {
    var s=sheet_(), rows=rows_(s), old=input.id ? rows.find(function(r){return r.id===input.id;}) : null;
    if(input.id&&!old) throw new Error('元の記録が見つかりません。再読み込みしてください。');
    if(old&&old._version!==input._version) throw new Error('別の編集が入っています。再読み込みしてから保存してください。');
    var r=normalize_(input), newYear=old&&r.research_year!==old.research_year;
    var target=old&&!newYear ? old : null;
    if(rows.some(function(v){return (!target||v.id!==target.id)&&key_(v)===key_(r);})) throw new Error('同じ優待・発行回・期限が既にあります。既存の記録を編集してください。');
    r.id=target ? target.id : 'exp-'+Utilities.getUuid().toLowerCase();
    var line=target ? target._row : s.getLastRow()+1;
    var values=FIELDS.map(function(k){return k==='research_year'||k==='research_month_number' ? Number(r[k]) : literal_(r[k]);});
    s.getRange(line,1,1,HEADERS.length).setValues([values]);
    SpreadsheetApp.flush();
    return {id:r.id,created:!target,keptPreviousYear:!!newYear,data:getEditorData()};
  } finally {lock.releaseLock();}
}
function exportMasterCsv() {
  var rows=rows_(sheet_());
  var quote=function(v){return '"'+String(v==null?'':v).replace(/"/g,'""')+'"';};
  return '\uFEFF'+[CSV_FIELDS.join(',')].concat(rows.map(function(r){return CSV_FIELDS.map(function(k){return quote(r[k]);}).join(',');})).join('\r\n')+'\r\n';
}
