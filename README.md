# 優待券使えるお店検索 α

株主優待券を使える店舗を、現在地または指定した場所から近い順に探すスマートフォン向けWebアプリです。

## 設計方針

- ログイン不要
- X/SNS連携なし
- ページ表示だけでは位置情報を取得しない
- 「現在地から探す」を押したときだけ Geolocation API を利用
- サイト運営者側では現在地を保存しない
- 現在地そのものは localStorage に保存しない
- 初期画面は地図ではなく距離順リスト中心
- 店舗カードから Google Maps へ遷移
- 優待利用可否の正本は各社の公式情報
- 店舗DB本体は Cloudflare D1 に保存し、Public GitHub には配置しない
- ブラウザには近隣検索結果だけを返し、全店舗DBを返すAPIは用意しない

## 公開中の公式店舗DB

| 発行会社 | 公式DB方式 | 現在の対象店舗 |
| --- | --- | ---: |
| すかいらーくHD | 公式店舗検索API/公式優待対象ブランド | 2,730 |
| コロワイド | 公式グルメ検索＋優待利用可表示 | 約733 |
| クリエイト・レストランツHD | 公式レストランサーチの株主優待利用可フラグ | 829 |
| 物語コーポレーション | 公式店舗検索API | 821 |

店舗数は取得時点の値で、月次更新により変動します。

## 店舗DBの保存と更新

店舗DB本体は Public repository には保存しません。

月次更新は GitHub Actions 上で次の順に実行します。

1. Cloudflare D1 から前回の店舗状態を Actions runner 内へ一時復元
2. 各社の公式サイト/APIから最新情報を取得
3. 前回状態と比較し、新店・対象外・店舗情報変更を判定
4. 最新状態を Cloudflare D1 へ同期
5. 公開用の更新履歴 `data/updates.json` だけを GitHub に反映
6. runner 内の店舗DB作業ファイルを削除

`data/issuers/*/stores/` は `.gitignore` 対象で、店舗DB本体・スナップショット・履歴DB・差分DBを Public GitHub に再度コミットしない設計です。

## 検索API

ブラウザは Cloudflare Worker の検索APIを利用します。

- D1 に公式座標がある会社は Worker が D1 から近隣店舗を検索
- コロワイドは Worker が OpenPOI で近隣候補を取得し、D1内の公式対象店舗と店名・住所・電話で照合
- 1回の検索結果は最大30件
- 検索半径は最大10km
- 全店舗を一括取得するエンドポイントは提供しない

## DB異常監視

各スクレイパーには公式データの仕様変更や異常値を検知する防御チェックがあります。

- 取得失敗
- HTML/API/埋め込みデータ形式の変更
- 店舗数の異常増減
- 必須項目の欠落
- 店舗ID重複
- 座標の欠落・異常
- 優待対象判定値の未知の変更

異常時はD1の既存データを更新せず、GitHub Issue に `[DB監視]` 警告を作成します。

さらに `Official DB health watchdog` が毎日、D1上の各社店舗数・前回状態件数・更新時刻を検査し、Workerの稼働確認も行います。

## OpenPOI

検索API: `https://api.openpoiapi.com/v1/search`

OpenPOI は認証不要です。公式座標を持たない会社の近隣候補探索と、地名・施設検索の補助に利用します。

出典・ライセンス:
https://openpoiapi.com/attribution.html

## GitHub Pages / Cloudflare

- フロントエンド: GitHub Pages
- 店舗検索API: Cloudflare Workers
- 店舗DB: Cloudflare D1
- 更新処理: GitHub Actions

Public GitHub にはアプリ本体・設定・スクレイパー・公開用更新履歴を置き、店舗DB本体は置きません。
