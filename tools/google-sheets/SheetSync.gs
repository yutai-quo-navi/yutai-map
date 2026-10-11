/** Only expiry_master.csv in the fixed repository may be updated. */
var EXPIRY_GITHUB_PATH='https://api.github.com/repos/yutai-quo-navi/yutai-map/contents/data/expiry_master.csv';
function getExpirySyncStatus() {
  var p=PropertiesService.getScriptProperties();
  return {configured:!!p.getProperty('EXPIRY_GITHUB_TOKEN'),pending:!!p.getProperty('EXPIRY_PENDING'),
    lastSent:p.getProperty('EXPIRY_LAST_SENT')||'',error:p.getProperty('EXPIRY_SYNC_ERROR')||''};
}
function queueExpirySync_() {
  var p=PropertiesService.getScriptProperties();
  p.setProperty('EXPIRY_PENDING',Utilities.getUuid());
  if(!p.getProperty('EXPIRY_GITHUB_TOKEN')) return {queued:false,message:'シートに保存済み。サイトへの自動反映は初期設定待ちです。'};
  if(!ScriptApp.getProjectTriggers().some(function(t){return t.getHandlerFunction()==='syncExpiryToGitHub';}))
    ScriptApp.newTrigger('syncExpiryToGitHub').timeBased().after(60000).create();
  return {queued:true,message:'シートに保存済み。サイトへの反映を予約しました。'};
}
function onExpirySheetEdit(event) {
  if(event&&event.range&&event.range.getSheet().getName()===DB_NAME) queueExpirySync_();
}
function installExpirySync() {
  var book=book_();
  PropertiesService.getScriptProperties().setProperty('EXPIRY_SPREADSHEET_ID',book.getId());
  if(!ScriptApp.getProjectTriggers().some(function(t){return t.getHandlerFunction()==='onExpirySheetEdit';}))
    ScriptApp.newTrigger('onExpirySheetEdit').forSpreadsheet(book).onEdit().create();
  return queueExpirySync_();
}
function csvText_(rows) {
  var quote=function(v){return '"'+String(v==null?'':v).replace(/"/g,'""')+'"';};
  return CSV_FIELDS.join(',')+'\n'+rows.map(function(r){return CSV_FIELDS.map(function(k){return quote(r[k]);}).join(',');}).join('\n')+'\n';
}
function mergeExpiryHistory_(remote,current) {
  var table=Utilities.parseCsv(remote.replace(/^\uFEFF/,'')),headers=table.shift();
  if(JSON.stringify(headers)!==JSON.stringify(CSV_FIELDS)) throw new Error('GitHubのCSV列が変更されています。自動反映を停止しました。');
  var seen={},records={};
  table.forEach(function(values){
    if(!values.some(Boolean)) return;
    if(values.length!==CSV_FIELDS.length) throw new Error('GitHubのCSV行が不正です。');
    var r={};CSV_FIELDS.forEach(function(k,i){r[k]=values[i];});
    if(!r.id||records[r.id]) throw new Error('GitHubの管理IDが空欄・重複です。');
    records[r.id]=r;
  });
  current.forEach(function(row){
    if(!row.id||seen[row.id]) throw new Error('シートの管理IDが空欄・重複です。');
    seen[row.id]=true;var r=normalize_(row);r.id=row.id;records[r.id]=r;
  });
  Object.keys(records).forEach(function(id){
    if(!seen[id]) {
      records[id].status='checking';
      var note='シートに存在しない履歴行。現行の期限として表示しない。';
      if(records[id].notes.indexOf(note)<0) records[id].notes+=(records[id].notes?'／':'')+note;
    }
  });
  var keys={};Object.keys(records).forEach(function(id){var k=key_(records[id]);if(keys[k]) throw new Error('同じ優待・発行回・期限が複数あります。シートを確認してください。');keys[k]=true;});
  return csvText_(Object.keys(records).map(function(id){return records[id];}));
}
function syncExpiryToGitHub() {
  var lock=LockService.getScriptLock();lock.waitLock(20000);
  var p=PropertiesService.getScriptProperties(), pending=p.getProperty('EXPIRY_PENDING');
  try {
    ScriptApp.getProjectTriggers().filter(function(t){return t.getHandlerFunction()==='syncExpiryToGitHub';}).forEach(function(t){ScriptApp.deleteTrigger(t);});
    if(!pending) return;
    var token=p.getProperty('EXPIRY_GITHUB_TOKEN');
    if(!token) throw new Error('GitHub連携の初期設定がまだありません。');
    var headers={Authorization:'Bearer '+token,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};
    var response=UrlFetchApp.fetch(EXPIRY_GITHUB_PATH+'?ref=main',{headers:headers,muteHttpExceptions:true});
    if(response.getResponseCode()!==200) throw new Error('GitHubの読み込みに失敗しました。権限と接続を確認してください。');
    var file=JSON.parse(response.getContentText()),remote=Utilities.newBlob(Utilities.base64Decode(file.content.replace(/\s/g,''))).getDataAsString('UTF-8');
    var next=mergeExpiryHistory_(remote,rows_(sheet_()));
    if(remote!==next){
      var update=UrlFetchApp.fetch(EXPIRY_GITHUB_PATH,{method:'put',headers:headers,contentType:'application/json',muteHttpExceptions:true,
        payload:JSON.stringify({message:'Sync expiry ledger from mobile/Google Sheets',branch:'main',sha:file.sha,content:Utilities.base64Encode(next,Utilities.Charset.UTF_8)})});
      if([200,201].indexOf(update.getResponseCode())<0) throw new Error('GitHubへの反映を確認できませんでした。シートは保存済みです。重複送信せず、再同期で現状を照合してください。');
    }
    p.setProperty('EXPIRY_LAST_SENT',new Date().toISOString());p.deleteProperty('EXPIRY_SYNC_ERROR');
    if(p.getProperty('EXPIRY_PENDING')===pending) p.deleteProperty('EXPIRY_PENDING');
    else queueExpirySync_();
  } catch(error) {
    p.setProperty('EXPIRY_SYNC_ERROR',error.message||'同期を確認できませんでした。');
    throw error;
  } finally {lock.releaseLock();}
}
