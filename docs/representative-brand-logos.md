# Representative store logo asset audit (2026-10-14)

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

## Current image delivery (2026-10-14)

Every actual logo rendered in the dining and hotel **selection cards** is served as a same-origin `./assets/` file from GitHub Pages. There is no runtime image fetch to Wikimedia Commons, social image hosts, blogs, or external hotel-brand servers.

A one-time image migration saved 12 previously external reference images as compressed local WebP files named `assets/logo-local-<issuer-or-feature>.webp`. Source artwork remains a recognizable store/hotel identity and retains its intrinsic aspect ratio. The one-time import workflow was removed after successful import.

### Repaint performance

- `app.js` reconciles the existing issuer card DOM nodes and moves them only if their order changes. Selection toggles only update state and classes.
- `special-features.js` likewise preserves hotel card nodes and logos when selection changes.
- Existing image nodes remain mounted, avoiding image decode/repaint flashes during selection.
- `index.html` preloads three likely first-row logos, and static issuer configuration requests use normal browser caching.

Do not add direct remote URLs to `representative-marks.js` again. For any future logo, download and optimize the authentic artwork at development time, add it to `assets/`, and reference a local path. Avoid guessed symbols or arbitrary holding-company logos.