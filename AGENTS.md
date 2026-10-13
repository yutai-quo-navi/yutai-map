# Brand addition privacy policy (user instruction, 2026-10-13)

- In every chat, new brand/issuer scraping, collection, source validation, D1 sync and scheduled update programs must be added to and operated in the private `yutai-quo-navi/yutai-data-private` repository by default. Confirm that repository remains private before starting.
- This public repository may receive the application, issuer configurations and public update metadata. Do not add new scraping/sync programs or their Actions workflows here.
- Existing public programs remain unchanged unless the user explicitly requests migration. The current authorized migration covers only Ohsho and Joyfull added on 2026-10-13; earlier public pipelines are not part of it.
- Start and verify the private pipeline before removing an authorized public counterpart. Preserve working D1 data and public search. Do not rewrite public Git history without a separate explicit instruction.

# Store data rules

- For a new issuer, inspect the official store locator's API, JSON and HTML for store IDs, benefit/payment eligibility, latitude and longitude before choosing a source.
- Prefer official store data and official coordinates whenever available. Use OpenPOI only when the required official data is unavailable; record what was checked and the remaining limitation in the issuer configuration.
- Resolve eligibility per store when the official source provides a benefit or payment flag. Corporate brand ownership alone does not establish benefit eligibility.
- Keep full store snapshots and generated SQL private in Cloudflare D1 and the ignored working directories. Commit only issuer configurations, frontend code/tests and public update metadata here; new collection code and its tests belong in the private repository.
- Restore the previous D1 snapshot, validate complete pagination and coverage, and sync only added, removed or changed stores. Never replace a working dataset with incomplete results or perform a routine full rewrite.
- Initialize and verify D1 before promoting a new issuer to `official_coordinates`. Keep the current working search available until the import succeeds.
- Add each new official collector, scheduled scraping/sync workflow and parser tests in the private repository. Keep public health thresholds and the existing D1-based guide generation in this repository.
