if (-not (Test-Path config/tm-csv-connector.cfg)) {
    Copy-Item config/tm-csv-connector.cfg.example config/tm-csv-connector.cfg
}
if (-not (Test-Path config/cronjobs)) {
    Copy-Item config/cronjobs.example config/cronjobs
}
