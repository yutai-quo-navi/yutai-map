# Static benefit guides

The public search application links from its menu and footer to `/guides/dining/` and `/guides/hotels/`. These hubs link to issuer/brand pages and voucher/hotel pages. Each detail page links back to its parent, official sources, and the search application with a validated selection. Following a link never requests geolocation or starts a search.

## Source of truth and cost

`tools/seo/build_guides.py` reads existing `issuer_stats`, `brand_catalog`, and `feature_snapshots` through the Cloudflare REST API, with the already-configured `CF_API_TOKEN`. It performs no scraping and never reads `stores`, `reference_stores` or `store_raw`. New scraping must continue to use the private data repository.

On an unchanged run, it reads the issuer counters once (currently 20 rows) and existing feature snapshots once (currently 13 rows). Changed issuers alone require a `brand_catalog` read. After brand refreshes it re-reads the small issuer counters to detect concurrent collection. D1 writes: zero. The exact measured `rows_read` is written to the Actions summary. Static page visits require no D1 reads. GA4 loads from the same shared analytics module as the search application.

`data/seo/brand-state.json` stores only public brand names/counts and revision numbers, never nationwide individual restaurant records. Hotel snapshots remain in D1; only the requested, derived hotel guide HTML is committed publicly. Coordinates and collection internals are not included in guide output or a public hotel JSON dump.

For a published OpenPOI-only issuer without D1 statistics, explicit reviewed `catalogBrands` from its public configuration are used. Counts remain null and the guide says they are not aggregated. Aliases are never treated as additional independent brands. Missing statistics without reviewed labels still fail closed.

## Automatic updates

`.github/workflows/build_seo_guides.yml` runs after successful existing public collection workflows, when published configuration/generator files change, manually, and daily at 07:50 JST. Private repository updates are picked up by this daily run (GitHub cron can be delayed). New public collector workflows should be added to the workflow_run list for immediate refresh; the daily fallback still covers them. Hidden/development issuers and nonpublic hotel benefits are excluded.

The generated HTML lives under `guides/`; `data/seo/pages.json` records content hashes and meaningful lastmod dates. Unchanged content preserves its lastmod and produces no unnecessary generated commit or Pages build. New entries add pages and links; removed entries remove generated HTML, hub links and sitemap entries. Old removed URLs return GitHub Pages' normal 404. Hotels are represented per voucher because different vouchers may have different conditions at the same physical property.

Missing snapshots, unverified hotels, duplicate hotel IDs, inconsistent brand counts or a concurrent catalogue update fail the workflow before replacing published guides. A failed run preserves the last successful version; it does not pretend that failed collection means every hotel closed.

The workflow commits generated HTML/aggregate state/sitemap using GITHUB_TOKEN, then explicitly requests a Pages build (token-created commits do not otherwise trigger one). The job checks out trusted main and only accepts successful same-repository/main workflow_run events. No additional credentials or hosting changes are required.

## SEO and checks

Each generated page contains a title, description, self canonical, OG/Twitter metadata, crawlable HTML links, BreadcrumbList/WebPage JSON-LD and a dateModified matching its sitemap lastmod. Hotel guides additionally use lodging structured data without invented prices, ratings or availability. CSP hashes are computed from the final JSON-LD. The sitemap includes the top and all current guide URLs. The domain-root robots.txt already declares this sitemap alongside the QUO site's sitemap.

The guide templates intentionally do not publish operational configuration notes, guess current voucher expiry from an issue year, or generate empty city/keyword combinations. Counts are this site's verified search inventory, not necessarily a company's entire store footprint. Being in a sitemap does not guarantee indexing or ranking.

Run `python -m unittest discover -s tests -p 'test_seo_guides.py'` and `node --test tests/guide-search.test.mjs tests/special-features.test.mjs` before publishing. Tests cover additions/removals, unchanged dates, crawlable hierarchy, escaped content, JSON-LD, safe links, incremental catalogue reads, verification failures and published-only search selection.

Submit `https://yutai-quo-navi.github.io/yutai-map/sitemap.xml` in the site's Google Search Console property, then inspect representative guide URLs and monitor page indexing and search performance. GA4 measures visits/use; Search Console measures Google search visibility and indexing. Search Console account setup is external to this repository.
