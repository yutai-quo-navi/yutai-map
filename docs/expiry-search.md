# 失効検索

期限シートの確認済みレコードを店舗検索への登録有無によらず掲載。日本時間の本日から60日後までを分類別に表示し、分類内は期限順。申込み・登録・交換・受取は「カタログ・申込み」に分類。既存のサービス・レジャー分類からホテル・交通・生活サービスを表示時に分ける。シートの既存カテゴリを変更する必要はない。

「持ってる」と優待ごとのアラート日（当日・1・2・3日前）はブラウザのlocalStorageに保存。通知は選択した日だけ、サイトを開いている画面上に表示。端末間同期・プッシュ通知は行わない。券ごとの管理IDで設定を保持するため、翌年の別IDには持ってるを引き継がない。日付が不明な期限月は月表示のみとし、アラート対象にしない。

## シートからの取り込み

認証済みGoogle Drive接続で`yutai-expiry`の「期限DB」を範囲読み取りし、ヘッダーを含む全行を `{"values":[...]}` として一時保存する。非公開シートの共有設定は変更しない。

```sh
python tools/sync_expiry_sheet.py /tmp/sheet-values.json --checked-on YYYY-MM-DD
python tools/build_expiry.py --baseline /tmp/previous-master.csv --draft /tmp/expiry-draft.txt
python tools/build_expiry.py --check --draft /tmp/expiry-draft.txt
```

取り込みは列名・日付・ID・重複・会社対応を検証してからCSVを更新する。シートから消えた統合前の行は履歴として残し、確認待ちにして旧期限の再掲載を防ぐ。日付未入力時に月末を補完しない。

CSVと生成JSON、同期ハッシュを同時に反映し、既存のGitHub Pages構築で公開する。変更がなければコミットしない。同期ハッシュは読み取り値のJSONをUTF-8、ensure_ascii=False、separators=(',', ':')で直列化したSHA256。
