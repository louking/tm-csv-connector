# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**tm-csv-connector** (branded as *tmtility*) is a Flask web app that bridges a [Time Machine](https://timemachine.org/) race-timing device to RaceDay Scoring software. It reads the TM's bluetooth output, stores results in a MySQL database, and writes a CSV file that RaceDay Scoring ingests. It also supports a barcode scanner for bib confirmation and a Trident RFID chip reader.

**Cross-repo documentation:** `louking/fsrc-tech` (local checkout: `C:\Users\lking\Documents\Lou's Software\projects\fsrc-tech\fsrc-tech`) is an LLM-oriented wiki summarizing the whole FSRC tech ecosystem; `applications/tmtility.md` there is a curated summary of *this* repo that links back to this file as the authoritative source (per fsrc-tech's own `CLAUDE.md`, it deliberately doesn't duplicate detail in full — just enough to orient someone reading fsrc-tech first). When a change here adds meaningful new architecture detail, a gotcha, or a notable release-process change to this file, also pull a high-value summary into that page and add an entry to fsrc-tech's `CHANGELOG.md`. Leave those fsrc-tech edits uncommitted — they're reviewed, committed, and pushed separately from the fsrc-tech repo.

## Running the App

The app runs in Docker. For local development:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

`docker-compose.dev.yml` mounts `./app/src` into the container so Flask reloads on file changes. The dev `.env` sets `COMPOSE_FILE=docker-compose.yml;docker-compose.dev.yml;docker-compose-sim.yml` (Windows uses `;` as the path separator; Linux uses `:`), so all three overlays are active during local development.

**Important:** bind mounts only take effect when the container is *recreated*, not just restarted. If the `./app/src:/app` mount is missing (check `docker inspect`), run `docker compose down && docker compose up -d` to recreate. Once the mount is active, both Python and JS changes are live without rebuilding — `ASSETS_DEBUG=True` in `config/tm-csv-connector.cfg` ensures JS files are served individually (not from a compiled bundle).

**VS Code task gotcha:** the `docker-compose` task type's `files` key overrides `COMPOSE_FILE` entirely. Tasks in `.vscode/tasks.json` that should rely on `COMPOSE_FILE` from `.env` must omit the `files` key.

**Debugging the clients locally:** the client configs in `.vscode/launch.json` pin both `python` and `debugLauncherPython` to `${workspaceFolder}/.venv/Scripts/python.exe`. `python` is the interpreter the client actually runs under; without `debugLauncherPython`, debugpy's launcher process runs under the editor's default interpreter (`python.defaultInterpreterPath`), so the terminal command line shows the global interpreter even though the client itself runs in `.venv`. Without `python`, the client runs under whatever interpreter the Python extension has selected, which isn't reliably `.venv` (→ `ModuleNotFoundError: requests`). The editor's "Property debugLauncherPython is not allowed" schema warning is harmless — the debugpy extension honors the key. A client run from VS Code and the installed NSSM service of the same client both listen on the same WebSocket port (8081/8082/8083), so stop one before starting the other. When switching back to the installed build, restart its service (see NSSM service names below) and reload the results page.

**Local HTTPS via Caddy:** A separate `caddy-docker` project (`C:\Users\lking\Documents\Lou's Software\projects\caddy-docker\caddy-docker`) runs a Caddy reverse proxy that provides automatic HTTPS for `*.localhost` domains. The app's nginx container listens on port 8080; Caddy forwards `https://tm.localhost` (and `https://tmsim.localhost`) to `host.docker.internal:8080`. If `SERVER_NAME` in `config/tm-csv-connector.cfg` changes, add a matching block to that project's `config/Caddyfile` and reload Caddy.

**Compose project name collision:** Compose names a stack after its directory, so a test install unpacked into another directory also named `tm-csv-connector` is the *same* project as this repo. It shares the same containers (`tm-csv-connector-app-1`, …) and the same `db-data` volume. `docker compose up` from here then shows "Recreating": it replaces the install's containers with the dev config and source mount, against the same database. To keep a test install separate, set `COMPOSE_PROJECT_NAME` in that directory's `.env` or use `docker compose -p <name>`.

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

**Ad hoc SQL against the local DB:** put the SQL in a file and pipe it in. `docker exec -i tm-csv-connector-db-1 sh -c 'mysql -uroot -p"$(cat /run/secrets/db-password)" tm-csv-connector' < query.sql`. The database name has hyphens, so quote it with backticks inside SQL. `scannedbib.order` is a reserved word and also needs backticks.

## Building and Releasing

**Version:** the app version is `APP_VER` in `.env` (e.g., `1.8.0.dev1`), which is gitignored. So a version bump never shows in `git status`. By convention, a release commit holds the rebuilt artifacts (`dist/` zip, `install/` exes) with the bare version as its message (e.g., `1.7.1.dev2`), separate from the source commits. Use a minor bump for new operator-visible behavior, a patch bump for fixes only. While a release build is running, `git add`/`git commit` can fail with `fatal: unable to write new index file`, with no `index.lock` present (seen twice, 2026-10-07 and 2026-10-09). Retrying a moment later works; files already staged stay staged.

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
   - `tm-csv-connector-js.zip` — contains `js/` (vendor JS); only rebuilt when JS content changes. A SHA256 content hash of all files in `JS_COMMON_HOST` is compared against `dist/js-content-hash.txt` (committed); if unchanged the existing zip is left untouched so git sees no modification. `JS_COMMON_HOST` typically points outside this repo (e.g. a shared, non-git vendor-JS folder), so there's no source history to diff directly — to see *what* changed between releases (not just *that* something changed), diff `dist/js-content-manifest.txt` (also committed, one `relpath:sha256` line per file, rewritten every run regardless of whether the zip was rebuilt) between two release commits.

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

Exactly one is non-null. All queries must filter on the appropriate one. **Never filter with a `None` source**: `filter_by(race_id=None)` (or `race=None`) becomes `race_id IS NULL`, which matches every simulation-run row, not zero rows. Seen live 2026-10-07 in a results page left open across a dev-stack restart. A switch from a test install's containers to dev was suspected, but that install had been disabled, so the trigger is unknown. The session had no `_results_raceid`, so `beforequery()` listed every simulation result. Reloading and changing races didn't fix it: `/_setparams` did store the race (the CSV was rewritten), but later requests still arrived without it. The browser had only one `session` cookie, and it wasn't `Secure`, so a leftover cookie wasn't the cause. With a fresh cookie jar, curl got the correct 4 rows after `/_setparams`, so the server was fine. The stuck window was a browser launched from VS Code. Clearing its cookies and all site data didn't help, but restarting that browser did. The cause wasn't found. A private window showed the underlying, general case. On a **first visit**, the initial render has no session race, so it briefly lists all simulation results. The next poll corrects it, after `setParams()` runs when the client WebSockets open. On a race-day laptop (no simulation runs) this shows only orphan results with no race. The scan buttons still work during that window. A scan-action Del on one of those rows (`NormalScanActionApi.get_source()` returns `result.race`, i.e., `None`) then shuffled scanned bibs across all simulation runs; it was stopped only by a `result.scannedbib_id` foreign-key error, which rolled the change back. Guard against a missing race/simulation run before building the filter (fix tracked in #152).

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

**NSSM service names** (from `install/enable-*.ps1`): `TmReader`, `BarccodeScanner` (sic — the doubled "c" is the real registered name; `disable-barcode-scanner.ps1` uses the same spelling, so don't "fix" one without the other and existing installs), and `TridentReader`. Run `nssm` commands from the install directory in an elevated shell (`& nssm-2.24/win64/nssm <command> <name>`). `nssm` isn't on PATH, so a bare `nssm ...` fails with "not recognized". Bare `nssm` in these notes is shorthand for that full form. `Stop-Service`/`Start-Service <name>` also work. Logs go to `$env:LOGGING_DIR/<client>.log`.

**Gotcha: `nssm restart` doesn't work on these services (#153).** It prints `Unexpected status SERVICE_STOP_PENDING in response to STOP control` and leaves the service **stopped**. Run `nssm start <name>` afterwards. The clients get NSSM's Ctrl-C (`server closing` is logged within milliseconds), but they never exit on their own. NSSM's event log shows every stop of every client taking ~3.4s and ending in `Killing process tree ... exit code 0`, which matches NSSM's full escalation: Ctrl-C, wait 1.5s, WM_CLOSE, wait 1.5s, then terminate. This happens even for idle clients, and there was no successful restart in two weeks of event log. It was first blamed on the non-daemon reader thread. `daemon=True` (in 50c69f9) didn't fix it. A daemon reader thread also keeps running, and can keep logging (e.g., `retrying in 5s`), until NSSM kills the process about 3.4s after `server closing`. nssm 2.24's `restart` doesn't wait for a slow stop: it sees `STOP_PENDING` and skips the start. **To restart a client, use `Restart-Service <name>`.** It prints "Waiting for service ... to stop", waits out the ~3.4s, then starts the service (bench-confirmed 2026-10-09, #153 test 10: STOP 14:48:27.5, killed 30.9, START 31.2, running 32.8). Setting `AppStopMethodSkip 7` in `enable-*.ps1`, so NSSM terminates the process immediately, was the alternative; it isn't needed. `nssm stop` still works: the service ends up stopped ~3.4s later, even if the command prints the same message, since there's no start step to skip. This affects only an operator stopping or restarting a service. A client **crash** is a different path: NSSM sees the process exit and starts it again by itself (the default `AppExit Restart`, which `enable-*.ps1` doesn't change), with no STOP control. To simulate a crash, kill the process in an elevated shell, e.g. `Stop-Process -Name trident-reader -Force` (also `barcode-scanner`, `tm-reader`). Don't use `nssm restart` for this. In a bench test on 2026-10-09 (chip reader, #153 test 2), the client was back about 2s after the kill. The results page showed "client is not running" until its next socket retry, 3–5s after the kill. The client then came back disconnected, since it doesn't reopen its device (#150 item 2). On 1.8.0.dev2 the page then showed a plain **Connect** with no banner, the same as a deliberate disconnect, and the scanner and TM reader behaved the same way (#153 tests 3–4). So `results.js` now tracks `tm_device_lost`/`scanner_device_lost`/`trident_device_lost`. Each is set in the `close_callback` if the device was connected or connecting when the socket closed, and cleared when the client reports any status but disconnected. While one is set, `client_restarted_alert()` keeps a "<client> restarted -- click Connect ..." banner up, so a crash mid-race can't go unnoticed. To read NSSM's events from Git Bash: `MSYS_NO_PATHCONV=1 wevtutil qe Application "/q:*[System[Provider[@Name='nssm']]]" /f:text /rd:true /c:20 | tr -d '\r\000'`.

When a client's process stops, the results page shows "client is not running" for it (see client status below). Before 50c69f9 the page kept showing the client's last status, e.g. **Stop Reconnecting** with the banner.

**`tm-reader-client` lacks the #146/#151 hardening the other two clients have.** It has no `reader_thread_running` guard, no open timeout, and no connecting/reconnecting status. If the Time Machine's Bluetooth side is unresponsive, the serial open on its COM port hangs silently: `async reader started with port COMn` is logged, then nothing, with no error and no timeout. Meanwhile the button stays **Connect** with no banner, and every further click starts another reader thread on the same port. Seen 2026-10-09 during #153 testing: three hung opens, then power-cycling the Time Machine let the next **Connect** succeed within 5s. The cause of the hang is unknown. It isn't simply a client kill: in a crash test right afterwards (`Stop-Process -Name tm-reader -Force` while connected), **Connect** worked first time with no power cycle. Tracked in #154. A successful TM connect is marked in the log by `need to set logging path in logger`, logged a couple of seconds after the open.

**Client `raceid` is in-memory state (#147):** each client holds the current race in a module-level `raceid = 0`, stamped onto everything it posts. It's set by the `raceid` opcode **and** by the `raceid` field of the `open` opcode — the latter matters because after a client restart (crash, service restart, dev relaunch) the browser's WebSocket reconnect doesn't reliably resend `raceid`, and a client left at `0` gets every post rejected with a `race_id` foreign-key `IntegrityError`. Any new client, or new browser→client `open` message, must carry and honor `raceid` the same way.

**Why clients run on Windows (not in the container):** The clients need direct access to USB serial devices (barcode scanner) and the laptop's internal Bluetooth (Time Machine, paired via Windows and exposed as a virtual COM port). Internal laptop Bluetooth is typically CNVi/PCIe-based and cannot be passed through to a Docker container via USB/IP, so `tm-reader-client` must run on Windows. The NSSM service approach has been stable and is deliberately kept.

**Port discovery flow (Windows):** The DB stores `BluetoothDevice` rows with MAC addresses (`hwaddr`). On page load, the browser fetches these from `/_getbluetoothdevices`, sends them to `tm-reader-client` via the `get_comports` WebSocket opcode, and the client uses `serial.tools.list_ports.comports()` to match Windows HWID strings (format: `BTHENUM\..._LOCALMFR&..&<MACADDR>\...`) to COM port names. This HWID-parsing logic in `tm-reader-client/app.py` is Windows-specific and would need to be replaced if the clients ever move to Linux (e.g. fixed udev symlinks instead).

**`trident-reader-client` connectivity status detection:** `shell()` in `trident-reader-client/app.py` polls the Trident telnet connection on a ~1s cadence (`sleep(max(1-pingtime, 0))` before each `reader.read()`). On a read timeout it pings the reader's IP via `ping3.ping()` and classifies the result as `connected`/`network-unreachable`/`no-response`. After any failed ping it sets `pingtime = 1`, which collapses the next sleep to 0 — an intentional busy-loop (bounded by the 0.1s read timeout + ping's own timeout) so it reconnects quickly once the reader comes back. `check_update_status()` reports a status to `/_chipreaderstatus` (and thus `AppLog`) only after it's been observed `STATUS_DEBOUNCE_COUNT` (3) consecutive times — added because the busy-loop's rapid re-pinging otherwise turns a single transient network blip into repeated flapping "network unreachable"/"connected" log lines. The one exception is the terminal `disconnected` event fired when the reader connection actually closes (end of `shell()`) — that's a one-shot event with no further loop iterations to confirm it, so it's posted via `check_update_status('disconnected', immediate=True)`, bypassing debounce.

**`trident-reader-client` auto-reconnect:** ping-success-implies-`connected` was a real trap: a bare ICMP reply proves the reader's network stack is up, not that the specific already-open telnet `reader`/`writer` socket is still live. If the reader power-cycled without the OS ever observing a FIN/RST on that socket (`reader.at_eof()` / `writer.connection_closed` never flip), `shell()`'s loop would keep polling the same stale socket forever — reads kept timing out, but as soon as ping succeeded again it reported `connected` even though no real Trident data (e.g. a `GUNTIME` marker) could ever arrive on that dead connection, and nothing tore the loop down to trigger a reconnect. Two changes close this gap:
- `enable_keepalive()` turns on short-interval TCP keepalive (`KEEPALIVE_IDLE_SEC`=10 / `KEEPALIVE_INTERVAL_SEC`=5 / `KEEPALIVE_COUNT`=3) on the socket right after `open_connection()` succeeds, via `setsockopt(TCP_KEEPIDLE/INTVL/CNT)` where available, falling back to the Windows-only `SIO_KEEPALIVE_VALS` ioctl (no per-count control, ms-based) on older Python/Windows combos where those constants don't exist. This makes the OS itself detect a half-dead peer within seconds and correctly flip `at_eof()`/`connection_closed`, instead of relying on ping.
- `reader_thread()` now retries `open_connection()` in a loop with a `RECONNECT_WAIT` (5s) backoff whenever the connection is lost or can't be established, distinguishing an unexpected drop from an explicit user disconnect via the `user_closed` flag (set only in `shell()`'s `if stop_reader:` branch — the finally-block's "discovered connection closed" path leaves it `False`, so that case auto-retries). `controller()`'s `open` opcode handler is idempotent (`reader_thread_running` guard) since the client now keeps itself connected on its own after the first `open`; the browser no longer needs to click Connect again after a drop.
- When the network drops (cable unplugged), keepalive kills the socket after about 20s, and `reader.read()` raises `OSError` `[WinError 121] The semaphore timeout period has expired`, not `ConnectionAbortedError`. `shell()` therefore catches all `OSError`. Before #151 it caught only `ConnectionAbortedError`, so this case skipped the cleanup, left an "exception never retrieved" traceback, and left `connected` `True` while retrying, which made the page show **Disconnect** instead of reconnecting. `reader_thread()` also resets `connected = False` before each retry as a backstop. A bench test on 2026-10-07 confirmed the fix: the drop was logged cleanly and the page went to reconnecting. While the reader is off the network, each `open_connection()` attempt blocks about 21s for Windows' TCP connect timeout before failing with the same `WinError 121`. Retries therefore run about every 26s, not every `RECONNECT_WAIT` (5s), and a `close` during an attempt takes effect only when that attempt fails.
- **Operational gotcha: the reader may refuse reconnects after a network outage.** Bench-observed 2026-10-07. After an outage long enough to kill the TCP connection (cable unplugged for a few minutes), every reconnect got `Connected` and then `EOF from server` within ~100ms. The client logged `discovered connection closed` and retried every ~6s, while the page correctly stayed on reconnecting. This went on for 6+ minutes, until a reader power-cycle; the next attempt then connected and stayed up. The likely cause is the reader's network interface (port 10001) allowing one TCP session and still holding the pre-outage one. Our close never reached it, and it hadn't timed out. Not confirmed. Shorter outages (~1–1.5 min, seen twice) reconnected without intervention. On race day: if the chip reader keeps reconnecting while the network is up, power-cycle it. The `SO_KEEPALIVE` `WinError 10038` warning in this loop is harmless: the socket is already closed when keepalive is set.

#82 in code comments still tracks the broader chip-reader connect/disconnect UX as incomplete (single hardcoded reader "A", etc.) — that's a separate, larger scope than the reconnect/keepalive fix above.

**Client status and connectivity alerting (#151):** `barcode-scanner-client` and `trident-reader-client` answer `is_connected` with a four-way `status` from `client_status()` alongside the legacy `connected` bool: `connected`; `connecting` (thread running, first attempt in progress); `reconnecting` (thread running, `retrying` set after any failed attempt or drop); `disconnected` (thread not running, i.e. never connected or user disconnected). The scanner also reports the `port` it's connected to/retrying. `client_status()` in `results.js` derives `connected`/`disconnected` from the `connected` bool for older clients that don't send `status`. While connecting/reconnecting the button reads **Stop Connecting**/**Stop Reconnecting** and sends `close`. A successful connect usually takes under 1s, shorter than the 3s `is_connected` poll, so **Stop Connecting** normally shows only when the first open is slow or failing. `close` which now cancels the retry loop promptly (`wait_for_retry()` polls `stop_reader` instead of a blind 5s sleep, and the loop checks `stop_reader` before each attempt). A `close` during the wait stops the loop almost at once (9ms measured). A `close` during a blocking open can't interrupt it: the loop stops only when that open fails, up to ~5s (1.6s measured), both from the 2026-10-07 #151 bench tests; for the scanner, if a *different* port is selected the button reads **Connect** instead and sends `open` to switch ports. `close` is ignored when no reader thread is running, and starting a thread clears `stop_reader`, so a stale close can't kill the next connect. A stop takes effect only when the current attempt ends, which can be up to ~21s for the chip reader. So clicking Stop while connecting/reconnecting sets `scanner_stopping`/`trident_stopping` in `results.js`: the button then shows a disabled **Stopping...** until the client reports a status other than connecting/reconnecting. Without this, the button looked unresponsive and operators clicked it twice (harmless, but confusing). Setting `disabled` on a jQuery UI button blocks clicks but doesn't make it look disabled, and `.client-reconnecting`'s orange overrides the browser default anyway. So `style.css` has a `button.ui-button:disabled` rule (50% opacity) that makes it look disabled.

Alerting: the small `#chipreader-alert-A` status dot (colored via `trident_status` in `results.js`) is easy to miss during a live race. On a transition *into* an alert state (not on every poll while degraded), `results.js` shows an orange banner and plays a short Web Audio beep (`client_alert_beep()`); both clear on recovery. Two banner divs share `.client-alert-banner` in `style.css` (rendered hidden by default in `get_results_filters()` in `home.py`): `#chipreader-alert-banner` for `network-unreachable`/`no-response`/`reconnecting` (texts in `CHIPREADER_ALERTS`; `trident_status` is forced to `reconnecting` while the client retries, since `detailedstatus` just sits at `disconnected` then), and `#scanner-alert-banner` for scanner `reconnecting`. A third, `#tm-alert-banner`, exists for the client-not-running case only. When a client's WebSocket closes (its process stopped or crashed), the `close_callback` resets that client's button to **Connect** and calls `client_not_running()`, which shows a "client is not running" message in that client's banner (#153). It shows the message only if the socket had opened earlier on this page, so a client that's already down when the page loads doesn't alert. That case is accepted (#153 test 9): the client services run even when their device isn't used, so a socket that never opens means the client really is down, and **Connect** reports "client not reachable". It beeps only when the banner text changes, since the callback runs again on every failed 5s reopen attempt. The button itself also gets the orange `client-reconnecting` class while reconnecting. Deliberately not alerting on `disconnected`, since that's usually an intentional user action. The chip reader button follows `connected` (the socket), but the dot follows `detailedstatus`, which is debounced over 3 readings. So a normal connect shows grey dot + **Stop Connecting**, then about 2s of grey dot + **Disconnect**, then green. That's expected. Note a scanner that's off when Connect is first clicked goes `connecting` → `reconnecting` (and alerts) after its ~5s open timeout.

**`barcode-scanner-client` Bluetooth link check and auto-reopen (#146):** when a Bluetooth SPP scanner powers off, Windows keeps the virtual COM port open and pyserial raises nothing — no `connection_lost`, no read error, just silence. And when the scanner powers back on it does **not** reconnect to the still-open port; the PC side initiates the link when the port is *opened*, so the port must be closed and reopened (bench-confirmed 2026-10-05; this is what caused the silent race-day dropout in #146). The client handles this in two parts:
- **Detect:** `reader()` resolves the port's remote MAC from its Windows HWID (`port_bt_address()`, same parsing as `tm-reader-client`'s `get_comports`) and polls `BluetoothGetDeviceInfo()` from `BluetoothApis.dll` via ctypes every `LINK_CHECK_INTERVAL` (2s). `fConnected` reads a nonzero value like `32` when connected, not `1` — test `!= 0`. After `LINK_DOWN_COUNT` (3) consecutive "down" readings it closes the port and raises `LinkLost`. Expect about 25s from switching the scanner off until the results view shows reconnecting. About 20s of that is Windows: `fConnected` stays true until its own Bluetooth timeout for a silent device expires, so polling faster won't help. The client adds about 4s, and the browser's 3s status poll the rest (bench-observed 2026-10-07; the switch-off time was a counted estimate). Non-Bluetooth ports (e.g., a USB scanner) skip the check.
- **Recover:** `reader_thread()` retries opening `reader_port` every `RECONNECT_WAIT` (5s), same `user_closed`/`reader_thread_running` pattern as `trident-reader-client`. While the scanner is off, each open blocks ~5s and fails with `SerialException ... semaphore timeout period has expired` — expected, and the likely source of the same error logged at earlier races. An `open` opcode received while retrying with a *different* port switches the loop to that port, starting with its next attempt; that can take up to ~10s if a wait or blocking open is in progress (otherwise switching scanners mid-retry would be silently ignored); same-port `open` is ignored.

Operational gotchas: the Inateck `BCST-72` scanner (physical power switch) isn't reachable after power-on until its trigger is pulled once, so the reopen loop won't succeed until then. The Tera HW0002 has no such step — a trigger pull is what powers it on, and the reopen loop reconnects to it without anything further. A scanner that isn't in Bluetooth **SPP** mode (e.g., the Tera HW0002, which also supports Bluetooth HID, BLE, and 2.4 GHz dongle modes, all set by scanning config barcodes from *its* manual) fails the open with the same `semaphore timeout` as one that's switched off — check the scanner's mode before suspecting the client. Verified working as the installed PyInstaller build under the NSSM service account (LocalSystem). During retries the results view shows the scanner as reconnecting, with a banner and beep (see client status above).

### Race Start Time / GUNTIME auto-detection

`Race.start_time` (seconds since midnight) is the time-of-day offset added to each TM elapsed-time result when writing to the CSV (`fileformat.db2file`). It's editable via the Races view, and also surfaced directly on the results view filter bar (`#start-time` input + Set button, POSTs to `/_setracestarttime`) so the operator doesn't have to leave the page mid-race.

`trident.trident2db()` auto-populates `race.start_time` from the first live Trident `GUNTIME` marker received for a race (detected by checking whether any `ChipRead` with `types == 'GUNTIME'` already exists for that `race_id` before inserting) — this always overwrites any pre-configured estimate, but only once; later markers (e.g. a second reader, or a restart) are ignored. No CSV rewrite is triggered when this happens, on the assumption that nothing has been confirmed yet at gun time — manual edits via `/_setracestarttime` behave the same way (no rewrite), matching the existing Races-view edit path. The results page polls `/_getracestarttime` every 3s (`CHECK_CONNECTED_WAIT`) to pick up the auto-set value without a page reload, skipping the poll while the operator has the field focused so it doesn't clobber an in-progress edit.

**Testing GUNTIME without the Trident box:** POST directly to `/_livechipreads` (no auth — same as `/_postresult`/`/_postbib`, meant for unattended client processes), e.g. `{"raceid": 1, "data": "abA000002607060010300000\r\n"}`. `tridentmarker2obj()` in `trident.py` reads a marker line by fixed offset: `[2]`=reader_id, `[8:14]`=date (`yymmdd`), `[16:18]`/`[18:20]`/`[20:22]`=HH/MM/SS, `[22:24]`=hundredths as **hex**; `[3:8]` and `[14:16]` are unused filler, and the line must be ≥24 chars or the hex-hundredths slice raises. The `/chipreads` page's "Import" button (upload a `.log` file with such lines) exercises the same `trident2db()` call with `source='file'` instead of `'live'`. Gotcha: the first-marker-only detection means re-triggering the auto-set on the same race requires either a fresh race or manually deleting that race's `GUNTIME` row from `chipread` — the `/chipreads` table view has no delete button.

### JavaScript / DataTables

- `beforedatatables.js` / `afterdatatables.js` — run before/after DataTables init on every page; `afterdatatables()` branches on `location.pathname` for page-specific setup
- `resultscommon.js` — shared constants (`CHECK_TABLE_UPDATE = 1000 ms`) and the `results_cookie_mutex`
- `results.js` — WebSocket management for TM reader, scanner, and Trident connections. `StableWebSocket` auto-reconnects on close and detects zombie connections (socket `readyState === OPEN` yet messages not flowing) via ping: if nothing is received between two successive pings, it force-closes to trigger the normal reconnect cycle. The connect/disconnect button state (`connected`, `scanner_connected`, `trident_connected`) is updated when `is_connected` responses arrive, and reset to disconnected when a client's WebSocket closes (#153); stale state during a reconnect window can cause button clicks to silently fail — each click handler wraps `send()` in a try/catch and alerts the user if the client is unreachable.
- The results table polls for updates every 1 second (`setInterval` + `refresh_table_data`)

**Poll returns full dataset every tick**: The JS sends `?since={last_draw}` on every poll, but `loutilities.DbCrudApi._retrieverows()` never reads that arg — it always returns every row for the race. `refresh_table_data` then does a full client-side diff. For large races this creates noticeable lag. The `Result` model has composite indexes on `(race_id, place)` and `(simulationrun_id, place)` to keep the per-race query fast. DataTables server-side mode is **not** a fit here — the view shows all finishers in a scrollable list and needs to detect row deletions, both of which break the server-side pagination model.

**Port select "select port" value is the string `'null'`:** the placeholder option is created with `new Option('select port', null)`, so its value is `'null'`, not `null`. That string also gets saved to the session via `/_setparams`. Test for a real selection with `port_selected()` in `results.js`, not `!= null`. The old check let **Connect** send `open` with port `'null'`, which killed the client's reader thread with `could not open port 'null'` (#153).

**Race selection and session state**: The race dropdown (`#race`) drives the entire results view. `setParams()` in `results.js` is called on WebSocket open (initial page load) and on dropdown change. It POSTs to `/_setparams`, which saves any `_results_*`-prefixed form field into the Flask session (e.g. `session['_results_raceid']`). If the race changed, it also rewrites the CSV file. On the server side, `get_results_filters()` reads `session['_results_raceid']` to pre-select the dropdown — so the last-used race is restored across page loads. First visit (no session) falls back to the latest race by date. **Type gotcha**: Flask session stores all form POST values as strings; database IDs are integers. Any server-side code that compares a `_results_*` session value to a model `.id` must cast to `int` first (catch `TypeError`/`ValueError` for the `None` case).

**Race change must not depend on every client being up (#148):** `setParams()` also pushes the new `raceid` to all three client WebSockets *before* POSTing `/_setparams`, and `StableWebSocket.send()` throws if a socket isn't open. Unguarded, one client being down/reconnecting aborted the whole race change — server session, table, and CSV stayed on the old race (so new TM results "vanished" and Clear All appeared not to clear, since it acts on the page's `raceid` while the table showed the session's), and clients after the failing one in send order stayed on the old race too. `send_raceid()` now wraps each send, and each WebSocket's `open_callback` resends the current `raceid` so a client that missed a change catches up on reconnect. Caveat: the resend uses the *page's* `raceid`, not the server session's, so a results page whose `raceid` has drifted from the server's (a second tab, or a page left over from before a failed race change) pushes its stale race to the clients whenever they reconnect (e.g., after a client service restart). Also, a restarted client gets the race back but not its device connection — it stays disconnected until Connect is clicked again.

**Clear All / Undo Clear and data recovery:** `/_clearresults` snapshots the race's `Result` and `ScannedBib` rows as JSON into `resultssnapshot` (one row per race; a second Clear All of the *same* race replaces it — with an empty snapshot if the race was already cleared) before deleting them. The Undo Clear button only appears right after a clear in the same page session, but the API needs no auth and takes an explicit race, so a snapshot can be restored any time with e.g. `Invoke-RestMethod -Method Post -Uri http://tm.localhost:8080/_undoclearresults -ContentType 'application/json' -Body '{"raceid": N}'` — check the race has no rows first (restore adds, it doesn't replace), and note it deletes the snapshot and rewrites the CSV for that race. Backstop if there's no usable snapshot: the `db` service keeps MySQL binlogs for 3 days (`--binlog_expire_logs_seconds=259200`), and row-based binlog `DELETE` events contain full row images (`mysqlbinlog --base64-output=DECODE-ROWS -v`) — copy them out promptly.

**Critical draw-guard pattern**: The 1-second `setInterval` redraws destroy and recreate DOM nodes. Any button rendered inside a table cell (e.g. Use/Ins/Del scan-action buttons) must carry the CSS class `scan-action-btn`. Two layers in `afterdatatables.js` prevent a race where a redraw between `mousedown` and `mouseup` destroys the button so the `click` event never fires: (1) the `setInterval` callback skips the tick entirely if `scan_mousedown` is true; (2) a `preDraw.dt` handler (camelCase — DataTables is case-sensitive) returns `false` to cancel any draw that slips through while the flag is set. A `setTimeout(..., 0)` on `mouseup` ensures the click fires before the guard clears.

**Styling a plain input to match select2:** `style.css` defines `.like-select2-sizing` (white background, 1px `#aaa` border, 4px radius, `box-sizing: border-box`, 32px min-height) specifically so a plain `<input>` or `<div>` can visually match the select2 dropdowns used elsewhere on a page (e.g. Race/port selects), without pulling in a full select2 instance. Apply it directly as a class and override `height`/`padding` inline as needed (e.g. `#start-time` on the results view filter bar) — don't hand-roll ad hoc border/radius styles for this.

### Asset Bundling

`assets.py` defines `flask-assets` bundles. All vendor JS/CSS lives under `static/js/`. Bundles are compiled to `static/gen/`. `loutilities` provides additional JS/CSS served via `/loutilities/static/<path>`.

**Vendor JS via `JS_COMMON_HOST`**: `docker-compose.yml` mounts `${JS_COMMON_HOST}` from the host into `/app/tm_csv_connector/static/js:ro`. In dev, the `./app/src:/app` bind mount (from `docker-compose.dev.yml`) shadows this, so JS changes in the source tree are live. The `app/src/tm_csv_connector/static/js/` directory in the repo is transitional — it will be removed once `JS_COMMON_HOST` is confirmed to contain all needed files. For normal-mode installs the zip includes a `js/` directory (sourced from `JS_COMMON_HOST` during release) and the dist `.env` sets `JS_COMMON_HOST=./js`.
