# https://www.reddit.com/r/PowerShell/comments/afztl1/comment/ee4dkws/?utm_source=share&utm_medium=web2x&context=3
Install-PackageProvider NuGet -ForceBootstrap
Set-PSRepository PSGallery -InstallationPolicy Trusted
Install-Module -Name PsIni

# https://stackoverflow.com/a/22804178/799921
$env = Get-IniContent .env

# https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/read-host?view=powershell-7.3
# https://lazyadmin.nl/powershell/powershell-replace/

# OUTPUT_DIR
$output_dir = Read-Host "Directory for output csv?"
if (-not (Test-Path $output_dir)) {
    New-Item -Path $output_dir -ItemType Directory | Out-Null
    Write-Host "'$output_dir' created"
}
$output_dir = $output_dir.Replace('\', '/')
$env["_"]["OUTPUT_DIR"] = $output_dir

# LOGGING_DIR
$logging_dir = Read-Host "Directory for logging?"
if (-not (Test-Path $logging_dir)) {
    New-Item -Path $logging_dir -ItemType Directory | Out-Null
    Write-Host "'$logging_dir' created"
}
$logging_dir = $logging_dir.Replace('\', '/')
$env["_"]["LOGGING_DIR"] = $logging_dir

# save new .env
$env | Out-IniFile -FilePath .env -Encoding ASCII -Force

