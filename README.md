# 株主優待券が使えるお店検索

現在地や指定した場所から、株主優待券が使えるお店を近い順に探せる、ログイン不要のサービスです。

[お店を探す](https://yutai-quo-navi.github.io/yutai-map/) ／ [QUOカード対応ガソリンスタンドを探す](https://yutai-quo-navi.github.io/)

店舗・優待の利用条件は変更される場合があります。ご利用前に各社公式情報をご確認ください。

## 優待の期限情報

「今月期限」は日本時間で残り日数を表示し、対応する会社の店舗検索へつなぎます。原本は `data/expiry_master.csv`、表示用は `data/expiry.json`。確認済みデータのみ公開し、前年分も保持します。同じ原本からX初稿と前年同月の調査候補を生成できます。

[期限データの列仕様・編集・反映手順](docs/expiry.md)

## 出典

[出典: OpenPOI API](https://openpoiapi.com/attribution.html)
