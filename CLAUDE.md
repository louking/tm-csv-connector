# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**tm-csv-connector** (branded as *tmtility*) is a Flask web app that bridges a [Time Machine](https://timemachine.org/) race-timing device to RaceDay Scoring software. It reads the TM's bluetooth output, stores results in a MySQL database, and writes a CSV file that RaceDay Scoring ingests. It also supports a barcode scanner for bib confirmation and a Trident RFID chip reader.

## Running the App

The app runs in Docker. For local development:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

`docker-compose.dev.yml` mounts `./app/src` into the container so Flask reloads on file changes. The dev `.env` sets `COMPOSE_FILE=docker-compose.yml;docker-compose.dev.yml;docker-compose-sim.yml` (Windows uses `;` as the path separator; Linux uses `:`), so all three overlays are active during local development.

**Important:** bind mounts only take effect when the container is *recreated*, not just restarted. If the `./app/src:/app` mount is missing (check `docker inspect`), run `docker compose down && docker compose up -d` to recreate. Once the mount is active, both Python and JS changes are live without rebuilding — `ASSETS_DEBUG=True` in `config/tm-csv-connector.cfg` ensures JS files are served individually (not from a compiled bundle).

**VS Code task gotcha:** the `docker-compose` task type's `files` key overrides `COMPOSE_FILE` entirely. Tasks in `.vscode/tasks.json` that should rely on `COMPOSE_FILE` from `.env` must omit the `files` key.

**Local HTTPS via Caddy:** A separate `caddy-docker` project (`C:\Users\lking\Documents\Lou's Software\projects\caddy-docker\caddy-docker`) runs a Caddy reverse proxy that provides automatic HTTPS for `*.localhost` domains. The app's nginx container listens on port 8080; Caddy forwards `https://tm.localhost` (and `https://tmsim.localhost`) to `host.docker.internal:8080`. If `SERVER_NAME` in `config/tm-csv-connector.cfg` changes, add a matching block to that project's `config/Caddyfile` and reload Caddy.

For simulation mode on the production sim server (no dev bind-mount):

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

4. **Build the normal-mode distribution zips**:
   ```powershell
   .\new-release.ps1
   ```
   Produces two artifacts in `dist/`:
   - `tm-csv-connector.zip` — rebuilt every release; contains `install/`, docker-compose files, dist `.env`, and `config/` (via `dist-stage/`). Does **not** contain vendor JS. **Important**: `Compress-Archive -Path install/*` strips the `install\` prefix — all scripts land directly in the run directory alongside `config/`, `js-version.txt`, etc., not in an `install\` subdirectory. Paths in `install/install.ps1` must use `./` (run directory), not `../`.
   - `tm-csv-connector-js.zip` — contains `js/` (vendor JS); only rebuilt when JS content changes. A SHA256 content hash of all files in `JS_COMMON_HOST` is compared against `dist/js-content-hash.txt` (committed); if unchanged the existing zip is left untouched so git sees no modification.

   The main zip includes a `js-version.txt` at its root (the current JS hash). `install/install.ps1` compares this against `js/js-version.txt` inside the installed JS tree and auto-extracts `tm-csv-connector-js.zip` when they differ (fresh install or a release that updated vendor JS). On upgrades where JS hasn't changed, operators only need to extract the main zip.

   Temporarily swaps in a dist `.env` (blanks machine-specific vars, sets `COMPOSE_FILE=docker-compose.yml`, sets `JS_COMMON_HOST=./js`). The cfg is **not** patched on disk — instead a dist version (with `SERVER_NAME: 'tm.localhost'`, `SIMULATION_MODE: False`, `SEND_FILE_MAX_AGE_DEFAULT` removed) is written to `dist-stage/config/` and included in the main zip as `config/tm-csv-connector.cfg.example`. `install/initialize-config.ps1` copies the example config files to their live names only on a fresh install (skipped on upgrade to protect user customizations).

### Deploying

**Simulation mode (server)** — pull and restart the Docker stack on a remote server:
```bash
fab -H <host> deploy prod
```

**Normal mode (on-site laptop)** — distribute `dist/tm-csv-connector.zip` and (on first install or when JS changed) `dist/tm-csv-connector-js.zip`. Installation instructions for the operator are at https://tm-csv-connector.readthedocs.io/en/latest/admin-guide.html#installation

### Developing against a local loutilities checkout

Substitute `docker-compose.loutilities.yml` for `docker-compose.dev.yml` to mount a local loutilities source tree into the container instead of the installed package.

## Architecture

### Two Operating Modes

`SIMULATION_MODE` toggles between:
- **Normal mode**: auto-logs in a default user, shows public views only, connects to real hardware
- **Simulation mode**: full multi-user login, exposes `/admin/*` routes, replays recorded events for training

`SIMULATION_MODE` can be set in `config/tm-csv-connector.cfg` (`SIMULATION_MODE: True`) **or** as a Docker environment variable. `docker-compose-sim.yml` sets `SIMULATION_MODE=True` on the app service, which the app reads via `os.environ` in both `settings.py` (for loading sim-specific secrets) and `__init__.py` (where it overrides the cfg value). The env var takes precedence. Sim-specific Docker secrets (`mail-password`, `security-password-salt`, `super-admin-user-password`) are defined only in `docker-compose-sim.yml` — `docker-compose.yml` does not reference them.

### Flask App Structure

- `app/src/tm_csv_connector/__init__.py` — `create_app()` factory; conditionally registers blueprints
- `app/src/tm_csv_connector/views/public/` — normal-operation views and APIs
- `app/src/tm_csv_connector/views/admin/` — simulation-only views (gated by `SIMULATION_MODE`)
- `app/src/tm_csv_connector/views/common.py` — shared view mixins and API base classes
- `app/src/tm_csv_connector/model.py` — all SQLAlchemy models; SQLAlchemy types and constructs (`Column`, `Index`, `ForeignKey`, etc.) are aliased from `db.*` at the top of the file — do not add redundant `from sqlalchemy import ...` imports for names already aliased there
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

**Why clients run on Windows (not in the container):** The clients need direct access to USB serial devices (barcode scanner) and the laptop's internal Bluetooth (Time Machine, paired via Windows and exposed as a virtual COM port). Internal laptop Bluetooth is typically CNVi/PCIe-based and cannot be passed through to a Docker container via USB/IP, so `tm-reader-client` must run on Windows. The NSSM service approach has been stable and is deliberately kept.

**Port discovery flow (Windows):** The DB stores `BluetoothDevice` rows with MAC addresses (`hwaddr`). On page load, the browser fetches these from `/_getbluetoothdevices`, sends them to `tm-reader-client` via the `get_comports` WebSocket opcode, and the client uses `serial.tools.list_ports.comports()` to match Windows HWID strings (format: `BTHENUM\..._LOCALMFR&..&<MACADDR>\...`) to COM port names. This HWID-parsing logic in `tm-reader-client/app.py` is Windows-specific and would need to be replaced if the clients ever move to Linux (e.g. fixed udev symlinks instead).

### JavaScript / DataTables

- `beforedatatables.js` / `afterdatatables.js` — run before/after DataTables init on every page; `afterdatatables()` branches on `location.pathname` for page-specific setup
- `resultscommon.js` — shared constants (`CHECK_TABLE_UPDATE = 1000 ms`) and the `results_cookie_mutex`
- `results.js` — WebSocket management for TM reader, scanner, and Trident connections. `StableWebSocket` auto-reconnects on close and detects zombie connections (socket `readyState === OPEN` yet messages not flowing) via ping: if nothing is received between two successive pings, it force-closes to trigger the normal reconnect cycle. The connect/disconnect button state (`connected`, `scanner_connected`, `trident_connected`) is only updated when `is_connected` responses arrive; stale state during a reconnect window can cause button clicks to silently fail — each click handler wraps `send()` in a try/catch and alerts the user if the client is unreachable.
- The results table polls for updates every 1 second (`setInterval` + `refresh_table_data`)

**Poll returns full dataset every tick**: The JS sends `?since={last_draw}` on every poll, but `loutilities.DbCrudApi._retrieverows()` never reads that arg — it always returns every row for the race. `refresh_table_data` then does a full client-side diff. For large races this creates noticeable lag. The `Result` model has composite indexes on `(race_id, place)` and `(simulationrun_id, place)` to keep the per-race query fast. DataTables server-side mode is **not** a fit here — the view shows all finishers in a scrollable list and needs to detect row deletions, both of which break the server-side pagination model.

**Race selection and session state**: The race dropdown (`#race`) drives the entire results view. `setParams()` in `results.js` is called on WebSocket open (initial page load) and on dropdown change. It POSTs to `/_setparams`, which saves any `_results_*`-prefixed form field into the Flask session (e.g. `session['_results_raceid']`). If the race changed, it also rewrites the CSV file. On the server side, `get_results_filters()` reads `session['_results_raceid']` to pre-select the dropdown — so the last-used race is restored across page loads. First visit (no session) falls back to the latest race by date. **Type gotcha**: Flask session stores all form POST values as strings; database IDs are integers. Any server-side code that compares a `_results_*` session value to a model `.id` must cast to `int` first (catch `TypeError`/`ValueError` for the `None` case).

**Critical draw-guard pattern**: The 1-second `setInterval` redraws destroy and recreate DOM nodes. Any button rendered inside a table cell (e.g. Use/Ins/Del scan-action buttons) must carry the CSS class `scan-action-btn`. Two layers in `afterdatatables.js` prevent a race where a redraw between `mousedown` and `mouseup` destroys the button so the `click` event never fires: (1) the `setInterval` callback skips the tick entirely if `scan_mousedown` is true; (2) a `preDraw.dt` handler (camelCase — DataTables is case-sensitive) returns `false` to cancel any draw that slips through while the flag is set. A `setTimeout(..., 0)` on `mouseup` ensures the click fires before the guard clears.

### Asset Bundling

`assets.py` defines `flask-assets` bundles. All vendor JS/CSS lives under `static/js/`. Bundles are compiled to `static/gen/`. `loutilities` provides additional JS/CSS served via `/loutilities/static/<path>`.

**Vendor JS via `JS_COMMON_HOST`**: `docker-compose.yml` mounts `${JS_COMMON_HOST}` from the host into `/app/tm_csv_connector/static/js:ro`. In dev, the `./app/src:/app` bind mount (from `docker-compose.dev.yml`) shadows this, so JS changes in the source tree are live. The `app/src/tm_csv_connector/static/js/` directory in the repo is transitional — it will be removed once `JS_COMMON_HOST` is confirmed to contain all needed files. For normal-mode installs the zip includes a `js/` directory (sourced from `JS_COMMON_HOST` during release) and the dist `.env` sets `JS_COMMON_HOST=./js`.
