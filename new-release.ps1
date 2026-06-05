# Build dist package with clean .env and tm-csv-connector.cfg:
#   .env:
#     - COMPOSE_FILE set to docker-compose.yml only (no dev/sim files)
#     - machine-specific path variables blanked (edit-env.ps1 prompts for them on the target machine)
#   cfg:
#     - SERVER_NAME set to tm.localhost (normal install default)
#     - SIMULATION_MODE set to False

$devEnvContent = Get-Content .env
$distEnvContent = $devEnvContent | ForEach-Object {
    if ($_ -match '^COMPOSE_FILE=') { 'COMPOSE_FILE=docker-compose.yml' }
    elseif ($_ -match '^(OUTPUT_DIR|LOGGING_DIR|RSYNC_DEST_PATH|RSYNC_DEST_USER)=') { "$($matches[1])=" }
    elseif ($_ -match '^(\w+_HOST)=') { "$($matches[1])=" }
    else { $_ }
}

$devCfgContent = Get-Content config/tm-csv-connector.cfg
$distCfgContent = $devCfgContent | ForEach-Object {
    if ($_ -match '^SERVER_NAME:') { "SERVER_NAME: 'tm.localhost'" }
    elseif ($_ -match '^SIMULATION_MODE:') { 'SIMULATION_MODE: False' }
    else { $_ }
}

# Temporarily swap in dist .env
Rename-Item .env .env.bak
# Temporarily swap in dist cfg — track success so finally block only restores if backup exists
$cfgBacked = $false
Move-Item config/tm-csv-connector.cfg config/tm-csv-connector.cfg.bak
$cfgBacked = $true

try {
    $distEnvContent | Set-Content .env -Encoding ASCII
    $distCfgContent | Set-Content config/tm-csv-connector.cfg -Encoding ASCII
    Compress-Archive -Path install/* -DestinationPath dist/tm-csv-connector.zip -Force
    Compress-Archive ./.env, ./docker-compose.yml, ./docker-compose-crond.yml, config/tm-csv-connector.cfg, config/cronjobs.example -Update -DestinationPath dist/tm-csv-connector.zip
}
finally {
    Remove-Item .env -Force
    Rename-Item .env.bak .env
    if ($cfgBacked) {
        Remove-Item config/tm-csv-connector.cfg -Force -ErrorAction SilentlyContinue
        Move-Item config/tm-csv-connector.cfg.bak config/tm-csv-connector.cfg
    }
}
