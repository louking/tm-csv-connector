# Check vendor JS version and extract the JS zip if needed.
# On fresh install, tm-csv-connector-js.zip must be in the same directory as tm-csv-connector.zip.
# On upgrade, extract it only when the release includes a new JS zip (indicated by a version mismatch).
$expectedJsVersion = if (Test-Path './js-version.txt') { (Get-Content './js-version.txt').Trim() } else { '' }
$installedJsVersion = if (Test-Path './js/js-version.txt') { (Get-Content './js/js-version.txt').Trim() } else { $null }
if ($null -eq $installedJsVersion -or $installedJsVersion -ne $expectedJsVersion) {
    if (Test-Path './tm-csv-connector-js.zip') {
        Write-Host "Extracting vendor JS files..."
        Expand-Archive -Path './tm-csv-connector-js.zip' -DestinationPath '.' -Force
    } else {
        Write-Warning "Vendor JS is missing or outdated. Place tm-csv-connector-js.zip in the run directory and re-run install."
    }
}

# Remove files left in the client folders by releases built with PyInstaller 5 (before 1.9.0).
# Each client folder now holds only <client>.exe and _internal; extracting the zip doesn't delete
# the old files. The clients must be stopped first (./disable-all), or their files are locked.
foreach ($client in 'tm-reader', 'barcode-scanner', 'trident-reader') {
    if (Test-Path "./$client/_internal") {
        $stale = Get-ChildItem "./$client" | Where-Object { $_.Name -notin "$client.exe", '_internal' }
        if ($stale) {
            Write-Host "Removing $($stale.Count) old files and folders from $client..."
            $stale | Remove-Item -Recurse -Force -ErrorAction Continue
        }
    }
}

./publish-utilities
./edit-env
./set-db-passwords
./initialize-config
./enable-tm-reader
./enable-barcode-scanner
./enable-trident-reader
./enable-app
