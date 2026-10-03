# 優待近場検索 β — GitHub Pages MVP

スマートフォン向け「現在地から近い株主優待利用可能店舗」検索のベース実装です。

## 設計方針
- ログイン不要
- X/SNS連携なし
- ページ表示だけでは位置情報を取得しない
- 「現在地から探す」を押したときだけ Geolocation API を利用
- サイト運営者側では現在地を保存しない
- 検索のため現在地座標はブラウザから OpenPOI API に送信
- 現在地そのものは localStorage に保存しない
- 初期画面は地図ではなく「距離順リスト」中心
- 店舗カードからGoogle Mapsへ遷移

## 初期対象
- 3387 クリエイト・レストランツHD
- 7616 コロワイド
- 3197 すかいらーくHD

`data/companies.json` はMVP用の初期ブランド辞書です。特にクリレスの全ブランド・各社の個別除外店舗は今後、公式情報と照合して拡充してください。

## GitHub Pagesへの配置
このフォルダ内のファイルをPublic repositoryのルートへ配置し、Settings → Pages からデプロイします。

## OpenPOI
検索API: `https://api.openpoiapi.com/v1/search`

OpenPOI APIは認証不要。出典・ライセンス表示が必要です。
https://openpoiapi.com/attribution.html

## 重要
β版ではブランド名一致による候補抽出です。「β 要公式確認」表示を外すのは、公式店舗一覧と除外店舗のデータ整備後を推奨します。
