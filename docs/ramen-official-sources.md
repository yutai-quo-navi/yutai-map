# 山岡家・力の源（一風堂系）の公式店舗情報

確認日: 2026-10-12

## 山岡家

- 優待対象: https://maruchiyo.yamaokaya.com/ir/incentives/
- 店舗検索: https://www.yamaokaya.com/shops/
- 店舗ID・業態・全店座標は公式HTMLと `json_realtime.shops` から取得。
- 全HTML店舗IDとJSON店舗IDの一致を検証し、各店舗詳細の住所・電話・地図座標と照合。
- 株主優待対象のラーメン山岡家、味噌ラーメン山岡家、煮干しラーメン山岡家のみ。餃子業態を除外。
- WordPress RESTページAPIも確認したが403。公式HTML/JSONに必要情報があるためOpenPOIは使用しない。

## 力の源（一風堂系）

- 優待対象: https://www.chikaranomoto.com/ir/benefit/
- 国内店舗一覧: https://stores.ippudo.com/日本
- 公式Yext店舗ページの `pageProps.document` に店舗ID、住所、電話、`yextDisplayCoordinate` がある。
- 公式検索が使うYext API (`prod-cdn.us.yextapis.com/v2/accounts/me/search/vertical/query`) を優先。公開検索キー、locator/locations、Japan条件で全ページ取得。総件数・各ページ件数・重複ID・国内住所・開店日を検証。
- 国内HTMLディレクトリも調査し、ページ埋め込み座標を確認。APIの更新が早いため、完全なAPIページングを主データ源とする。
- 公式検索のクライアントAPIと店舗詳細の支払い項目も調査。株主優待の店舗別フラグは見つからず、公式優待方針が明示する国内一風堂系ブランドを対象とする。
- 今回のデータソースは一風堂・一風堂 KAY・IPPUDO RAMEN EXPRESS・RAMEN EXPRESS 博多一風堂。名島亭・因幡うどんは公式店舗サイトが別のため未掲載と明記する。
- 一風堂の公式座標が取得できるためOpenPOIは使用しない。

## 運用

`tools/issuers/ramen_official.py` と各社 `scrape.py` が収集、`scrape_yamaokaya_chikaranomoto.yml` が毎月更新。
D1の前回スナップショットを復元し、検証済み差分のみ反映。全件書き直しをしない。
初回はdevelopmentで追加し、両社D1の件数・座標を確認してからpublic/official_coordinatesへ昇格。
ガイドは成功した更新ワークフロー完了後に再生成。
