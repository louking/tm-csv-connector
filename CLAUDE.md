# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**tm-csv-connector** (branded as *tmtility*) is a Flask web app that bridges a [Time Machine](https://timemachine.org/) race-timing device to RaceDay Scoring software. It reads the TM's bluetooth output, stores results in a MySQL database, and writes a CSV file that RaceDay Scoring ingests. It also supports a barcode scanner for bib confirmation and a Trident RFID chip reader.

## Running the App

The app runs in Docker. For local development:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

`docker-compose.dev.yml` mounts `./app/src` into the container so Flask reloads on file changes. `COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml` is already set in `.env` (Docker Compose V2 uses `:` as the separator on all platforms, including Windows — the old `;` was V1 behavior).

**Important:** bind mounts only take effect when the container is *recreated*, not just restarted. If the `./app/src:/app` mount is missing (check `docker inspect`), run `docker compose down && docker compose up -d` to recreate. Once the mount is active, both Python and JS changes are live without rebuilding — `ASSETS_DEBUG=True` in `config/tm-csv-connector.cfg` ensures JS files are served individually (not from a compiled bundle).

For simulation mode (enables admin views, multi-user login):

```powershell
docker compose -f docker-compose.yml -f docker-compose-sim.yml up
```

**Database migrations** (run inside the app container):

```bash
flask db upgrade          # apply pending migrations
flask db migrate -m "..."  # generate a new migration
```

`app.py` (not `run.py`) is the entry point for flask CLI commands — it sets `init_for_operation=False` so migrations work before tables exist.

## Building and Releasing

### Full release pipeline (run in sequence via VS Code "Build/Push/Release" task)

1. **Build client executables** (PyInstaller, outputs to `install/`):
   ```powershell
   .venv/scripts/activate; pyinstaller --noconfirm --distpath install tm-reader-client/app.py -n tm-reader
   .venv/scripts/activate; pyinstaller --noconfirm --distpath install barcode-scanner-client/app.py -n barcode-scanner
   .venv/scripts/activate; pyinstaller --noconfirm --distpath install trident-reader-client/app.py -n trident-reader
   ```
   Requires a `.venv` in the repo root with PyInstaller and the client dependencies.

2. **Build docs** (must run before building the Docker image):
   ```powershell
   cd web/docs; ../../.venv/scripts/activate; ./make html
   ```

3. **Build and push Docker image** (includes sim compose overlay so both modes are baked in):
   ```powershell
   docker compose -f docker-compose.yml -f docker-compose-sim.yml build
   docker compose -f docker-compose.yml -f docker-compose-sim.yml push
   ```

4. **Build the normal-mode distribution zip**:
   ```powershell
   .\new-release.ps1
   ```
   Strips machine-specific env vars, forces `SIMULATION_MODE: False` and `SERVER_NAME: 'tm.localhost'`, and produces `dist/tm-csv-connector.zip`.

### Deploying

**Simulation mode (server)** — pull and restart the Docker stack on a remote server:
```bash
fab -H <host> deploy prod
```

**Normal mode (on-site laptop)** — distribute `dist/tm-csv-connector.zip`. Installation instructions for the operator are at https://tm-csv-connector.readthedocs.io/en/latest/admin-guide.html#installation

### Developing against a local loutilities checkout

Substitute `docker-compose.loutilities.yml` for `docker-compose.dev.yml` to mount a local loutilities source tree into the container instead of the installed package.

## Architecture

### Two Operating Modes

`SIMULATION_MODE` (env var or cfg key) toggles between:
- **Normal mode**: auto-logs in a default user, shows public views only, connects to real hardware
- **Simulation mode**: full multi-user login, exposes `/admin/*` routes, replays recorded events for training

### Flask App Structure

- `app/src/tm_csv_connector/__init__.py` — `create_app()` factory; conditionally registers blueprints
- `app/src/tm_csv_connector/views/public/` — normal-operation views and APIs
- `app/src/tm_csv_connector/views/admin/` — simulation-only views (gated by `SIMULATION_MODE`)
- `app/src/tm_csv_connector/views/common.py` — shared view mixins and API base classes
- `app/src/tm_csv_connector/model.py` — all SQLAlchemy models
- `app/src/tm_csv_connector/fileformat.py` — CSV output logic and the `filelock` mutex
- `app/src/tm_csv_connector/trident.py` — Trident RFID binary-format parser

### Data Model Duality

`Result` and `ScannedBib` each have two nullable foreign keys:
- `race_id` — used in normal mode, linked to a `Race`
- `simulationrun_id` — used in simulation mode, linked to a `SimulationRun`

Exactly one is non-null. All queries must filter on the appropriate one.

### Views use loutilities DbCrudApi

All table views are instances (or subclasses) of `loutilities.tables.DbCrudApi`. The pattern:

```python
dbmapping   = dict(zip(db_attrs, form_fields))   # form → db
formmapping = dict(zip(form_fields, db_attrs))   # db → form
```

Values in these dicts can be attribute name strings or callables `lambda row: ...`. Override `beforequery`, `createrow`, `updaterow`, `editor_method_postcommit`, etc. to customise behaviour.

### File Locking

`fileformat.filelock` is a `threading.Lock` that serialises any operation touching the CSV output file **or** multi-table database manipulations (place recalculation, scanned-bib queue assignment). Always acquire before any such operation:

```python
lock(filelock)
try:
    ...
    db.session.commit()
    unlock(filelock)
except:
    unlock(filelock)
    raise
```

### External Clients (Windows Services)

Three asyncio client processes run as Windows services via NSSM (`install/`):

| Client | Serial port | WebSocket URI | HTTP post endpoint |
|---|---|---|---|
| `tm-reader-client` | TM bluetooth | `ws://tm.localhost:8081/` | `/_postresult` |
| `barcode-scanner-client` | barcode scanner | `ws://tm.localhost:8082/` | `/_postbib` |
| `trident-reader-client` | Trident RFID | `ws://tm.localhost:8083/` | `/_livechipreads` |

The browser communicates with these clients over WebSocket (`results.js`). The clients also POST directly to the Flask backend.

### JavaScript / DataTables

- `beforedatatables.js` / `afterdatatables.js` — run before/after DataTables init on every page; `afterdatatables()` branches on `location.pathname` for page-specific setup
- `resultscommon.js` — shared constants (`CHECK_TABLE_UPDATE = 1000 ms`) and the `results_cookie_mutex`
- `results.js` — WebSocket management for TM reader, scanner, and Trident connections
- The results table polls for updates every 1 second (`setInterval` + `refresh_table_data`)

**Critical draw-guard pattern**: The 1-second `setInterval` redraws destroy and recreate DOM nodes. Any button rendered inside a table cell (e.g. Use/Ins/Del scan-action buttons) must carry the CSS class `scan-action-btn`. Two layers in `afterdatatables.js` prevent a race where a redraw between `mousedown` and `mouseup` destroys the button so the `click` event never fires: (1) the `setInterval` callback skips the tick entirely if `scan_mousedown` is true; (2) a `preDraw.dt` handler (camelCase — DataTables is case-sensitive) returns `false` to cancel any draw that slips through while the flag is set. A `setTimeout(..., 0)` on `mouseup` ensures the click fires before the guard clears.

### Asset Bundling

`assets.py` defines `flask-assets` bundles. All vendor JS/CSS lives under `static/js/`. Bundles are compiled to `static/gen/`. `loutilities` provides additional JS/CSS served via `/loutilities/static/<path>`.
