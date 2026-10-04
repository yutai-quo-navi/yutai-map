# Cloudflare backend

Cloudflare Workers + D1 provide the non-public serving layer for the store search application.

## Production architecture

Official sites / APIs
→ GitHub Actions scraper
→ temporary runner-only current/diff state
→ Cloudflare D1
→ Cloudflare Worker search API
→ GitHub Pages browser client

## D1 roles

- `stores`: official stores with coordinates
- `reference_stores`: official eligible stores without coordinates, currently used for Colowide matching
- `store_raw`: private previous-store records used by the next scraper run
- `issuer_state`: private per-issuer metadata used to reconstruct the previous state
- `issuer_search_config`: aliases used by Worker-side candidate matching

The Public GitHub repository does not contain the store DB, snapshots, store history, or raw diff DB.

## Worker API

Production Worker:

`https://yutai-map-api.yutaisamurai.workers.dev`

Main search endpoint:

`/v1/stores/search`

Protections / constraints:

- maximum search radius: 10 km
- maximum response: 30 stores
- no full-database endpoint
- browser CORS restricted to the GitHub Pages origin
- Colowide OpenPOI candidate matching runs inside the Worker, not in the browser

## Update flow

Each issuer workflow:

1. reads the previous raw state from D1 in bounded pages
2. reconstructs `current.json` only inside the Actions runner
3. runs the official-source scraper and diff checks
4. updates only that issuer in D1
5. merges user-facing change events into `data/updates.json`
6. removes the temporary store DB before committing

All issuer jobs share one concurrency group so D1 imports and public update-history commits do not race.

## GitHub secret

Required repository secret:

- `CF_API_TOKEN`

The D1 database ID is configuration, not a secret.

## Health checks

`Official DB health watchdog` queries D1 directly and verifies:

- per-issuer serving row count
- per-issuer private raw-state row count
- serving/raw count parity
- freshness against each issuer's configured max age
- Worker health endpoint
