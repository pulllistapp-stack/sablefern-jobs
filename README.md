# sablefern-jobs

Scheduled database jobs for a Pokémon TCG collection tracker.

Cron workflows only. Every job checks out the private application
repository through a read-only deploy key and runs its scripts
directly — this repository carries nothing but the workflow files.
(Until 2026-09-19 three of them ran a copy of the scripts kept here,
frozen months behind the application; that copy is gone.)

Order matters for the morning chain: card prices land first, then
sealed prices, then valuations computed against the day's fresh
numbers.

The application these serve — API, web frontend, image pipeline,
everything user-facing — lives elsewhere and is not part of this
repository. Nothing here serves traffic or handles authentication,
and nothing here performs DDL: creating and altering tables stays
with the application.

## Not open source

Published so these jobs can run on public-repository Actions minutes,
not as an invitation to reuse. All rights reserved; see `LICENSE`.

## Configuration

Secrets (database URL, storage and marketplace API credentials, and
the read-only deploy key) are set at the repository level. Every
workflow runs on `schedule` and `workflow_dispatch` only — never
`pull_request_target` — so a fork cannot reach them.

`POKEMONTCG_API_KEY` is optional; it raises the rate limit on the
Cardmarket top-up.

## Adding a workflow

Copy the checkout block from `daily-ebay-snapshot.yml`: the
`repository` + `ssh-key` checkout, `defaults.run.working-directory:
backend`, and `cache-dependency-path: backend/requirements.txt`. A
workflow without that block has no code to run.
