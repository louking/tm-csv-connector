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

./publish-utilities
./edit-env
./set-db-passwords
./initialize-config
./enable-tm-reader
./enable-barcode-scanner
./enable-trident-reader
./enable-app
