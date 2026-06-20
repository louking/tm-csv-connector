$ErrorActionPreference = 'Stop'

# Build dist package with clean .env and tm-csv-connector.cfg:
#   .env:
#     - COMPOSE_FILE set to docker-compose.yml only (no dev/sim files)
#     - machine-specific path variables blanked (edit-env.ps1 prompts for them on the target machine)
#   cfg (written as tm-csv-connector.cfg.example under config/ in the zip):
#     - SERVER_NAME set to tm.localhost (normal install default)
#     - SIMULATION_MODE set to False
#     - SEND_FILE_MAX_AGE_DEFAULT removed (dev-only setting)

$devEnvContent = Get-Content .env
$distEnvContent = $devEnvContent | ForEach-Object {
    if ($_ -match '^COMPOSE_FILE=') { 'COMPOSE_FILE=docker-compose.yml' }
    elseif ($_ -match '^(OUTPUT_DIR|LOGGING_DIR|RSYNC_DEST_PATH|RSYNC_DEST_USER)=') { "$($matches[1])=" }
    elseif ($_ -match '^JS_COMMON_HOST=') { 'JS_COMMON_HOST=./js' }
    elseif ($_ -match '^(\w+_HOST)=') { "$($matches[1])=" }
    else { $_ }
}

$devCfgContent = Get-Content config/tm-csv-connector.cfg
$distCfgContent = $devCfgContent | ForEach-Object {
    if ($_ -match '^SERVER_NAME:') { "SERVER_NAME: 'tm.localhost'" }
    elseif ($_ -match '^SIMULATION_MODE:') { 'SIMULATION_MODE: False' }
    elseif ($_ -match '^SEND_FILE_MAX_AGE_DEFAULT:') { }
    else { $_ }
}

# Stage dist config files so they land under config/ when the zip is extracted.
# Using a staging directory avoids touching the live config files on disk.
New-Item -ItemType Directory -Path dist-stage/config -Force | Out-Null
$distCfgContent | Set-Content dist-stage/config/tm-csv-connector.cfg.example -Encoding ASCII
Copy-Item config/cronjobs.example dist-stage/config/cronjobs.example

# Compute a content hash over all JS source files to detect changes between releases.
# Only rebuild tm-csv-connector-js.zip when the hash changes; otherwise leave it untouched
# so git does not see a spurious modification on every release run.
$jsCommonHost = ($devEnvContent | Where-Object { $_ -match '^JS_COMMON_HOST=' } | Select-Object -First 1) -replace '^JS_COMMON_HOST="?(.*?)"?\s*$', '$1'
$jsRootPath = (Resolve-Path $jsCommonHost).Path
$jsFiles = Get-ChildItem $jsCommonHost -Recurse -File | Sort-Object FullName
$manifestLines = $jsFiles | ForEach-Object {
    "$($_.FullName -replace [regex]::Escape($jsRootPath), ''):$(($_ | Get-FileHash -Algorithm SHA256).Hash)"
}
$manifestBytes = [System.Text.Encoding]::UTF8.GetBytes(($manifestLines -join "`n"))
$manifestStream = [System.IO.MemoryStream]::new($manifestBytes)
$newJsHash = (Get-FileHash -Algorithm SHA256 -InputStream $manifestStream).Hash
$manifestStream.Dispose()

$jsHashFile = 'dist/js-content-hash.txt'
$oldJsHash = if (Test-Path $jsHashFile) { (Get-Content $jsHashFile).Trim() } else { '' }

# Stage js-version.txt so the installer can verify the JS zip is at the right version
$newJsHash | Set-Content dist-stage/js-version.txt -Encoding ASCII

if ($newJsHash -ne $oldJsHash) {
    Write-Host "JS content changed -- rebuilding tm-csv-connector-js.zip"
    $jsZipDest = Join-Path (Resolve-Path '.').Path 'dist\tm-csv-connector-js.zip'
    New-Item -ItemType Directory -Path dist-stage-js/js -Force | Out-Null
    Copy-Item "$jsCommonHost/*" dist-stage-js/js/ -Recurse -Force
    $newJsHash | Set-Content dist-stage-js/js/js-version.txt -Encoding ASCII
    if (Test-Path $jsZipDest) { Remove-Item $jsZipDest }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        (Resolve-Path 'dist-stage-js').Path,
        $jsZipDest
    )
    Remove-Item -Recurse -Force dist-stage-js
    $newJsHash | Set-Content $jsHashFile -Encoding ASCII
    Write-Host "tm-csv-connector-js.zip updated."
} else {
    Write-Host "JS content unchanged -- tm-csv-connector-js.zip not rebuilt."
}

# Temporarily swap in dist .env
Rename-Item .env .env.bak

try {
    $distEnvContent | Set-Content .env -Encoding ASCII
    Compress-Archive -Path install/* -DestinationPath dist/tm-csv-connector.zip -Force
    Compress-Archive -Path dist-stage/* -Update -DestinationPath dist/tm-csv-connector.zip
    Compress-Archive -Path ./.env, ./docker-compose.yml, ./docker-compose-crond.yml -Update -DestinationPath dist/tm-csv-connector.zip
}
finally {
    Remove-Item .env -Force
    Rename-Item .env.bak .env
    Remove-Item -Recurse -Force dist-stage
}
