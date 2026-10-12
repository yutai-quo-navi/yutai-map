# UI quality checks

The interface retains the warm orange identity. `ui-quality.css` defines readable
secondary text, at least 44px button targets, an explicit selected check, a
responsive issuer grid, scrollable selection dialogs, consistent store actions,
tabular numeric values and deadline cards. Expired records retain the existing
expiry-search filtering behavior. No store or deadline data is changed.

`lintapple@0.1.20` is a development dependency, not a script loaded by visitors.
Its policy uses the Japanese system-font stack and viewport widths 320, 390 and
1440. Exceptions must name a selector, rule and reason in `ui-policy.json`.

```sh
npm ci --ignore-scripts
npx playwright install --with-deps chromium
npm run lint:ui
```

The runner serves this checkout locally. External endpoints are intercepted with
explicit test fixtures, so CI never reads or writes production D1 or calls
OpenPOI. It checks the initial page, issuer dialog, results, saved favorites,
expiry search and bulk-registration form. The screenshots contain sample store
names, not production search results. Functional assertions and runtime errors
fail the run; findings are reported in `ui-reports/lintapple.json` and the
workflow artifact without blocking deployment during the initial rollout.
`npm run test:ui` additionally fails on every lintapple finding.

`UI_CHROMIUM_EXECUTABLE` can select a locally installed Chromium binary when the
standard Playwright browser download is unavailable. Reports are gitignored.

Containers without Japanese system fonts can set `UI_TEST_FONT_DIRECTORY` to a
local `@fontsource/noto-sans-jp` directory for test-only font rendering. Fonts
are served from localhost under the existing CSP; visitors load no new fonts.
