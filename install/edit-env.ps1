# https://www.reddit.com/r/PowerShell/comments/afztl1/comment/ee4dkws/?utm_source=share&utm_medium=web2x&context=3
Install-PackageProvider NuGet -ForceBootstrap
Set-PSRepository PSGallery -InstallationPolicy Trusted
Install-Module -Name PsIni

function Set-Path ($path, $prompt) {
    if (-not $path) {
        do {
            $path = Read-Host $prompt
        }
        while ((-not $path) -or (-not (Test-Path $path -IsValid)))
    }
    if (-not (Test-Path $path)) {
        New-Item -Path $path -ItemType Directory | Out-Null
        Write-Host "'$path' created"
    }
    
    return $path
}

# https://stackoverflow.com/a/22804178/799921
$env = Get-IniContent .env

# check if we've installed before
if (Test-Path .lastenv) {
    $lastenv = Get-IniContent .lastenv
    $output_dir = $lastenv["_"]["OUTPUT_DIR"]
    $logging_dir = $lastenv["_"]["LOGGING_DIR"]
} else {
    $lastenv = @{"_" = @{}}
}

# https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/read-host?view=powershell-7.3
# https://lazyadmin.nl/powershell/powershell-replace/

# OUTPUT_DIR
$output_dir = Set-Path "$output_dir" "Directory for output csv?"
$output_dir = $output_dir.Replace('\', '/')
$env["_"]["OUTPUT_DIR"] = $output_dir
$lastenv["_"]["OUTPUT_DIR"] = $output_dir

# LOGGING_DIR
$logging_dir = Set-Path "$logging_dir" "Directory for logging?"
$logging_dir = $logging_dir.Replace('\', '/')
$env["_"]["LOGGING_DIR"] = $logging_dir
$lastenv["_"]["LOGGING_DIR"] = $logging_dir

# save new .env, .lastenv
$env | Out-IniFile -FilePath .env -Encoding ASCII -Force
$lastenv | Out-IniFile -FilePath .lastenv -Encoding ASCII -Force
