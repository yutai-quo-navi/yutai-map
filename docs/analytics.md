# GA4 access analytics

Measurement ID: `G-1KH2LCX7HT`. The shared `analytics.js` module loads the Google tag only on `yutai-quo-navi.github.io` and when the browser has not opted out. Import the same versioned module on generated static pages, using the correct relative path. It initializes once per document.

## Required Google property setting

In Admin → Data streams → this website, turn **Enhanced measurement OFF**. Manual page views and the events below are sent by the site. Automatic form, site-search and outbound-link measurement can duplicate events and send extra URL/form metadata. This setting is managed in Google Analytics, not this repository.

Advertising consent is denied, Google signals and advertising personalization are disabled. Keep them disabled in property settings too. No Cloudflare API calls or D1 reads are introduced by analytics.

## Events

| Event | Parameters |
| --- | --- |
| `page_view` | page title; page URL and referrer without query/fragment |
| `benefit_tab` | `section`: dining, hotel, expiry |
| `benefit_select` | section, fixed benefit_id, selected boolean |
| `benefit_search` | section, mode current/place, result_count |
| `outbound_action` | section, destination map/official; no destination URL |

Create event-scoped custom dimensions for `section`, `benefit_id`, `mode`, `destination`, and `selected` if breakdowns are needed in GA reports. `result_count` can be an event-scoped custom metric. Do not send input text, coordinates, search addresses, result rows, favorites, or user IDs. The parameter allowlist in `track` enforces this for site-authored events; Enhanced measurement must be disabled separately.

The privacy policy explains analytics and provides a browser-local opt-out. Disabling analytics prevents tag loading on subsequent pages; enabling reloads the page. No historical traffic is recovered, and blocked analytics is not counted. Use GA Realtime to verify the production site; management-screen collection notices can lag.

Search and selection events are aggregate usage, not complete transaction accounting. Empty search results are recorded with zero. Map/official links inside result cards are tracked. The global company picker and free-text brand input are not individually tracked.
