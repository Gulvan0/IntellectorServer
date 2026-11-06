<img width="1277" alt="image" src="https://github.com/user-attachments/assets/74f8cf58-1227-48bb-929e-fed3e123717d">

This project is a game server for Intellector, an exciting board game for 2 players.

<br />

Live version - https://intellector.info/game/?p=home

Join us on Discord - https://discord.gg/5ycEqRS8Es

Frontend repo - https://github.com/Gulvan0/Intellector

# Technologies

This project is written in `Python 3.14`. It works with a `MySQL 8` database.

## Used libraries

See `requirements.txt` for the authoritative list (`requirements-dev.txt` for dev/test stage).

**Major frameworks:**

- [FastAPI](https://github.com/fastapi/fastapi) running over [uvicorn](https://github.com/Kludex/uvicorn)
- [SQLModel](https://github.com/fastapi/sqlmodel) with [Alembic](https://github.com/sqlalchemy/alembic)

# Contributing

This repo doesn't have any custom style conventions. Adhere to the commonly accepted Python code style standards, respect PEP8, keep flake8 and mypy happy and stay idiomatic.

## Project structure

### Source code (`src`)

Domain packages share a common layout; each part exists only where needed:

- `routes.py` (or `routes/`) - the FastAPI router
- `methods.py` (or `methods/`) - the logic the routes call
- `models.py` (or `models/`) - SQLModel tables and the REST/WS payloads derived from them
- `datatypes.py` - the domain's enums and plain models
- `dependencies.py` - the domain's FastAPI dependencies
- `samples.py` - generators of example payloads, attached to the WS events (`payload_examples`)

Domains:

- `auth` - guest tokens, sign-in, registration, `whoami`
- `challenge` - challenges: validation, creation, merging a matching pair into a game, cancellation
- `game` - games
    - `routes` - `common` (search, reading a game, chat, adding time, ...), `internal` (games between two connected players: plies, offers, resignation), `external` (games computed on a client, such as bot games, and uploaded ply by ply)
    - `methods` - creation, plies, offers, rollbacks, timeouts, presence, ending
    - `models` - games, plies, chat, offers, rollbacks, time controls, presence, suspensions, outcomes; `models/rest` holds the game endpoints' payloads
- `player` - profiles, search, game stats and Elo history, follows, roles and restrictions, online statuses (`status.py`)
- `study` - studies (saved ply trees) and their validation
- `notification` - announcements of new public challenges and started games to VK and Discord, Telegram messages to the admin, the VK antispam limit
- `other` - endpoints outside any domain: API version (`api_version.py`), health, client error reports, admin shutdown and state inspection

Core:

- `main.py` - the entry point: assembles the app from the routers and the WS handlers, adds the middlewares and runs uvicorn (prod: one server on the loopback behind Caddy; test: TLS on `8443` plus plain HTTP on `8080`)
- `net` - the app itself: `App` (the FastAPI subclass holding the configs, the DB engine and the state), `MutableState` (in-memory tokens, WS subscribers, game action locks), WS connection handling, routes that log and rate-limit requests, the middlewares
- `pubsub` - WebSocket PubSub: channels, the handlers of incoming messages (`session`, `sub`, `unsub`), outgoing events (`refresh` - a channel's full state, `update` - a change)
- `log` - logs of the REST/WS traffic and of client errors, kept in the `intellector_logs` database
- `jobs` - jobs run by systemd timers outside the server process: `log_archive` moves old log days to the backup storage
- `config` - `STAGE` selection, loading `resources/config/*.yaml` (the `common` section merged with the stage's one), the config models
- `board` - game rules: positions, plies and their validation, SIP (position string) serialization, notation, openings
- `common` - shared across domains: user references (players, guests, bots), FastAPI dependencies, DB field types, time controls, the bot registry
- `utils` - generic helpers, not specific to Intellector

Standalone scripts:

- `api_lock.py` - guards against forgetting to bump the API version (`check` / `confirm`)
- `migrator.py` (with the `migration` package) - the one-time import of the previous iteration's data
- `drawer.py` - a debug tool drawing a board with Pillow

### Other folders

- `alembic` (plus `alembic.ini`) - DB schema migrations. The server never creates tables itself
- `resources`
    - `config` - `main.yaml` (tunables: keep-alive, Elo, rules, limits, rate limits, VK antispam) and `secret.yaml` (credentials; untracked, template in `secret.example.yaml`)
    - `sql` - raw SQL queries
    - `pieces` - piece images for `drawer.py`
    - `cert` - the local TLS certificate (untracked)
- `infra` - the production VPS
    - `deploy.py` - one-command deploy from the developer's PC: publishes the client to the static hosting and a new server release to the VPS
    - `bootstrap.sh` - one-time setup of a fresh VPS: packages, users, folders, MySQL, Python
    - `apply.sh` - installs the configs below
    - `ictl` - the operator CLI on the VPS
    - `caddy`, `mysql`, `journald`, `systemd` - service configs; the systemd units and timers run the server, backups, restore tests, log archiving and the watchdog
    - `scripts` - backup, restore, health check, alerts
- `api.lock` - the API version and the OpenAPI schema hash it was last confirmed for

## Quick Start

Note: Frontend repo has its own Quick Start in [its own README](https://github.com/Gulvan0/Intellector/blob/main/README.md). If you wish to work on the frontend, make sure to follow it as well.

### 1. Install the tools

- `Python 3.14`
- `MySQL 8`
- `mkcert` (for the local TLS ceritificate)

### 2. Clone this repo

https://github.com/Gulvan0/IntellectorServer

### 3. Set up the server

Run everything from the repo root, with `STAGE=test` environment variable set.

1. Python environment

    - `python -m venv .venv`
    - Activate the venv
    - `pip install -r requirements-dev.txt`

2. MySQL

    - Create `main` and `intellector_logs` databases
    - Give one user full rights on both

3. Certificate

    - `mkcert -install`
    - `mkcert localhost 127.0.0.1` inside `resources/cert/`. `cert/` is gitignored, so each developer makes their own

4. Secrets

    Write `resources/config/secret.yaml` (you can just copy `resources/config/secret.example.yaml` and fill in the values).

5. Schema

    `python -m alembic upgrade head`

6. Running the server

    `python src/main.py` (will listen on `https://localhost:8443` and `http://localhost:8080`)
