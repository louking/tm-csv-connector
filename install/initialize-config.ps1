if (-not (Test-Path config)) { New-Item -Path config -ItemType Directory | Out-Null }
Copy-Item ./tm-csv-connector.cfg -Destination config -Force