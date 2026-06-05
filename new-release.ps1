# Build dist package with a clean .env:
#   - COMPOSE_FILE set to docker-compose.yml only (no dev/sim files)
#   - machine-specific path variables blanked (edit-env.ps1 prompts for them on the target machine)
$devEnvContent = Get-Content .env
$distEnvContent = $devEnvContent | ForEach-Object {
    if ($_ -match '^COMPOSE_FILE=') { 'COMPOSE_FILE=docker-compose.yml' }
    elseif ($_ -match '^(OUTPUT_DIR|LOGGING_DIR|RSYNC_DEST_PATH|RSYNC_DEST_USER)=') { "$($matches[1])=" }
    elseif ($_ -match '^(\w+_HOST)=') { "$($matches[1])=" }
    else { $_ }
}

# Temporarily swap in the dist .env
Rename-Item .env .env.bak
try {
    $distEnvContent | Set-Content .env -Encoding ASCII
    Compress-Archive -Path install/* -DestinationPath dist/tm-csv-connector.zip -Force
    Compress-Archive ./.env, ./docker-compose.yml, ./docker-compose-crond.yml, config/tm-csv-connector.cfg, config/cronjobs.example -Update -DestinationPath dist/tm-csv-connector.zip
}
finally {
    Remove-Item .env -Force
    Rename-Item .env.bak .env
}
