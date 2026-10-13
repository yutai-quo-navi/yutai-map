# Representative store logo asset audit (2026-10-13)

The issuer card shows a **recognizable store identity**, not the issuer's holding-company logo. The logo is a navigation aid, **not** an assertion that every store in that chain accepts a voucher.

## User-supplied logo files (2026-10-13)

| Issuer ID | Stockholder issuer | Representative storefront | Local asset |
|---|---|---|---|
| yamaokaya | 丸千代山岡家 | ラーメン山岡家 | `assets/brand-logo-yamaokaya.webp` |
| yossix | ヨシックスHD | や台ずし | `assets/brand-logo-yossix.webp` |
| srs | SRS HD | 和食さと | `assets/brand-logo-srs.webp` |
| arclands | アークランズ | かつや | `assets/brand-logo-arclands.webp` |
| create | クリエイト・レストランツHD | 磯丸水産 | `assets/brand-logo-create.webp` |
| chimney | チムニー | はなの舞 | `assets/brand-logo-chimney.webp` |

These local WebP assets were compressed from **the six actual logo image files the user provided**, preserving original color, artwork and proportions. Do not replace them with generated logos or made-up initials.

### Identity cross-checks

- 丸千代山岡家 / 山岡家: https://maruchiyo.yamaokaya.com/business/yamaokaya/
- ヨシックスHD / や台ずし: https://yossix-shop.com/
- SRS / 和食さと: https://srs-holdings.co.jp/ir/assets/docs/58interim.pdf
- アークランズグループ / かつや: https://www.arclandservice.co.jp/brands/
- クリエイト・レストランツ / 磯丸水産: https://www.createrestaurants.com/company/history/ and https://www.createrestaurants.com/ir/stock/shareholder/
- チムニー / はなの舞: https://www.chimney.co.jp/

## Other displayed dining identifiers

Source image references currently configured in `representative-marks.js` should be checked before declaring them verified; remote logos can change or be blocked. Do not assume that a plausible-looking image is the correct store logo.

**Store-brand name fallback still in use (no image asset configured):**
- monogatari — 焼肉きんぐ
- matsuya — 松屋
- balnibarbi — GARB
- daiichikosho — BIG ECHO
- fujio — まいどおおきに食堂
- kineya — 杵屋
- saintmarc — サンマルクカフェ
- ringerhut — リンガーハット
- hiday — 日高屋

For future additions, favor an actual local image with verified brand association. Do not substitute a corporate or guessed logo. Cropping may remove white outer margins but must not remove interior art. The selected and unselected cards keep consistent dimensions.
