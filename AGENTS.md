# Store data rules

- For a new issuer, inspect the official store locator's API, JSON and HTML for store IDs, benefit/payment eligibility, latitude and longitude before choosing a source.
- Prefer official store data and official coordinates whenever available. Use OpenPOI only when the required official data is unavailable; record what was checked and the remaining limitation in the issuer configuration.
- Resolve eligibility per store when the official source provides a benefit or payment flag. Corporate brand ownership alone does not establish benefit eligibility.
- Keep full store snapshots and generated SQL private in Cloudflare D1 and the ignored working directories. Commit source code, configurations, tests and public update metadata only.
- Restore the previous D1 snapshot, validate complete pagination and coverage, and sync only added, removed or changed stores. Never replace a working dataset with incomplete results or perform a routine full rewrite.
- Initialize and verify D1 before promoting a new issuer to `official_coordinates`. Keep the current working search available until the import succeeds.
- Add the official collector, a scheduled GitHub Actions workflow, meaningful parser tests, health thresholds and guide regeneration for each supported source.
