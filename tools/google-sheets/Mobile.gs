/** Private web editor: publish with access MYSELF, executeAs USER_ACCESSING. */
function doGet() {
  return HtmlService.createHtmlOutputFromFile('MobileEditor')
    .setTitle('優待を登録').addMetaTag('viewport','width=device-width, initial-scale=1');
}
function companyKey_(value) {
  return String(value||'').normalize('NFKC').toLowerCase()
    .replace(/株式会社|ホールディングス|holdings|[\s・･.\-＆&（）()]/g,'').replace(/hd$/,'');
}
function companyCatalog_() {
  var catalog={};
  LISTED_COMPANIES.forEach(function(v){catalog[v[0]]={code:v[0],company_name:v[1],aliases:[],issuer_id:'',templates:[]};});
  SEARCH_ISSUERS.forEach(function(v){catalog[v.code]=Object.assign(catalog[v.code]||{},v,{templates:[]});});
  rows_(sheet_()).forEach(function(r){
    var v=catalog[r.code]||(catalog[r.code]={code:r.code,aliases:[],templates:[],issuer_id:''});
    v.company_name=r.company_name;
    if(r.issuer_id) v.issuer_id=r.issuer_id;
    v.aliases=v.aliases.concat(r.brands.split('|').filter(Boolean));
    if(!v.templates.some(function(t){return t.benefit_name===r.benefit_name;}))
      v.templates.push({benefit_name:r.benefit_name,category:r.category,expiry_type:r.expiry_type,brands:r.brands,emoji:r.emoji});
  });
  return Object.keys(catalog).map(function(k){return catalog[k];});
}
function getMobileData() {
  return {ledger:getEditorData(),companies:companyCatalog_(),sync:getExpirySyncStatus()};
}
function dateCandidates_(text) {
  var t=String(text||'').normalize('NFKC'), dates=[], re=/(20\d{2}|令和\s*(?:元|\d{1,2})|平成\s*(?:元|\d{1,2}))\s*[年\/.\-]\s*(\d{1,2})\s*[月\/.\-]\s*(\d{1,2})\s*日?/g, match;
  while((match=re.exec(t))){
    var year=match[1],era=/^(令和|平成)/.exec(year);
    if(era) year=(era[1]==='令和'?2018:1988)+Number(year.replace(era[1],'').trim().replace('元','1'));
    var date=year+'-'+('0'+match[2]).slice(-2)+'-'+('0'+match[3]).slice(-2);
    if(!dateValid_(date)) continue;
    var context=t.slice(Math.max(0,match.index-35),Math.min(t.length,re.lastIndex+18));
    if(!dates.some(function(v){return v.date===date;})) dates.push({date:date,context:context,deadline:/期限|有効|まで|必着|消印/.test(context)});
  }
  return dates;
}
function parseCouponText_(text,companies) {
  var normalized=String(text||'').normalize('NFKC'), key=companyKey_(normalized);
  var candidates=companies.filter(function(c){
    var aliases=[c.company_name].concat(c.aliases||[]).map(companyKey_).filter(function(v){return v.length>=3;});
    var code=new RegExp('(?:証券|銘柄|コード)[^0-9A-Z]{0,8}'+c.code+'(?![0-9A-Z])','i');
    return code.test(normalized)||aliases.some(function(v){return key.indexOf(v)>=0;});
  });
  var dates=dateCandidates_(normalized),marked=dates.filter(function(d){return d.deadline;});
  var selected=marked.length===1 ? marked[0].date : '';
  return {companies:candidates.map(function(c){return {code:c.code,company_name:c.company_name};}),dates:dates,
    code:candidates.length===1?candidates[0].code:'',expiry_date:selected,
    text:normalized.slice(0,25000),needsReview:candidates.length!==1||!selected};
}
function recognizeCoupon(image) {
  if(!image||image.mime!=='image/jpeg'||typeof image.base64!=='string'||image.base64.length>2800000||!/^[A-Za-z0-9+/]+=*$/.test(image.base64))
    throw new Error('JPEG画像を2MB以内にして選んでください。');
  var bytes=Utilities.base64Decode(image.base64);
  if(bytes.length<10||bytes.length>2000000||(bytes[0]&255)!==255||(bytes[1]&255)!==216)
    throw new Error('画像形式が不正です。');
  var id=null,cleanupWarning='';
  try {
    var doc=Drive.Files.create({name:'優待券OCR-'+Utilities.getUuid(),mimeType:'application/vnd.google-apps.document'},
      Utilities.newBlob(bytes,'image/jpeg','coupon.jpg'),{ocrLanguage:'ja',fields:'id'});
    id=doc.id;
    var response=UrlFetchApp.fetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'/export?mimeType=text%2Fplain',
      {headers:{Authorization:'Bearer '+ScriptApp.getOAuthToken()},muteHttpExceptions:true});
    if(response.getResponseCode()!==200) throw new Error('文字の読み取りに失敗しました。画像を明るく撮り直すか、手入力してください。');
    var text=response.getContentText('UTF-8');
    if(!text.trim()) throw new Error('文字が見つかりませんでした。手入力もできます。');
    var result=parseCouponText_(text,companyCatalog_());
  } finally {
    if(id) {try {Drive.Files.remove(id);}catch(error){cleanupWarning='読み取り用の一時ファイルを削除できませんでした。Google Driveの「優待券OCR-」ファイルを削除してください。';}}
  }
  if(cleanupWarning) result.warning=cleanupWarning;
  return result;
}
function saveMobileRecord(input) {
  var c=companyCatalog_().find(function(v){return v.code===String(input.code||'');});
  if(!c) throw new Error('会社を検索して候補から選んでください。見つからない会社は銘柄マスターの追加が必要です。');
  // Internal identifiers and official company spelling never come from editable inputs.
  input.company_name=c.company_name;
  input.issuer_id=c.issuer_id||'';
  input.search_brand=input.search_brand||'';
  return saveRecord(input);
}
function checkMobileRecords(inputs) {
  if(!Array.isArray(inputs)||inputs.length<1||inputs.length>10) throw new Error('一度に確認できるのは10件までです。');
  var catalog=companyCatalog_(),rows=rows_(sheet_()),batch={},issues=[];
  inputs.forEach(function(input,index){
    var c=catalog.find(function(v){return v.code===String(input.code||'');});
    if(!c) throw new Error((index+1)+'件目の会社を選んでください。');
    var r=normalize_(Object.assign({},input,{company_name:c.company_name,issuer_id:c.issuer_id||''}));
    var same=rows.find(function(old){return old.id!==input.id&&key_(old)===key_(r);});
    var k=key_(r);
    if(same) issues.push({index:index,kind:'existing',record:same});
    else if(batch[k]!==undefined) issues.push({index:index,kind:'batch',otherIndex:batch[k]});
    else batch[k]=index;
  });
  return {issues:issues};
}
