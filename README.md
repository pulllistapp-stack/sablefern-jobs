# sablefern-jobs

Scheduled database jobs for a Pokémon TCG collection tracker.

Three cron workflows, nothing else:

| Job | Schedule (UTC) | What it does |
|---|---|---|
| `daily-tcgplayer-sync` | 08:00 | Pulls the day's [TCGCSV](https://tcgcsv.com) archive, refreshes card market prices, tops up Cardmarket figures |
| `daily-products-sync` | 08:15 | Snapshots sealed-product prices from the same archive |
| `daily-portfolio-snapshot` | 09:00 | Rolls up each user's collection value for the growth charts |

Order matters: card prices land first, then sealed prices, then
valuations computed against the day's fresh numbers.

The application these serve — API, web frontend, image pipeline,
everything user-facing — lives elsewhere and is not part of this
repository. Nothing here serves traffic or handles authentication.

## Not open source

Published so these jobs can run on public-repository Actions minutes,
not as an invitation to reuse. All rights reserved; see `LICENSE`.

## Schema ownership

The models under `app/models/` mirror tables owned by the application.
**This repository performs no DDL** — `app/database.py:init_db()` only
checks connectivity. Creating and altering tables stays with the
application, so a model that drifts behind here fails at query time
rather than corrupting a schema.

When a column is added upstream, mirror it here too.

## Configuration

One secret, `DATABASE_URL`, set at the repository level. Every workflow
runs on `schedule` and `workflow_dispatch` only — never
`pull_request_target` — so a fork cannot reach it.

`POKEMONTCG_API_KEY` is optional; it raises the rate limit on the
Cardmarket top-up.

## Running locally

```bash
pip install -r requirements.txt
export DATABASE_URL='postgresql+asyncpg://...'

python -m scripts.sync_tcgcsv_daily --tier daily
python -m scripts.sync_products_daily
python -m scripts.snapshot_portfolios
```
