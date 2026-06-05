# https://www.reddit.com/r/PowerShell/comments/afztl1/comment/ee4dkws/?utm_source=share&utm_medium=web2x&context=3
Install-PackageProvider NuGet -ForceBootstrap
Set-PSRepository PSGallery -InstallationPolicy Trusted
Install-Module -Name PsIni -Force

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

# Extract a variable's current value from raw .env lines
function Get-EnvValue($lines, $key) {
    $line = $lines | Where-Object { $_ -match "^${key}=" } | Select-Object -First 1
    if ($line -match "^${key}=(.*)") { return $matches[1].Trim() }
    return $null
}

# Read current .env as raw lines — used for line-by-line update and as fallback source
$envContent = Get-Content .env

# Read .lastenv for use as fallback when .env values are blank (PsIni is fine here — .lastenv is a simple controlled file)
if (Test-Path .lastenv) {
    $lastenv = Get-IniContent .lastenv
} else {
    $lastenv = @{"_" = @{}}
}

# Priority: current .env value (manual edits win) → .lastenv (remembered from prior install) → prompt
function Get-Value($envLines, $lastenv, $key) {
    $v = Get-EnvValue $envLines $key
    if (-not $v) { $v = $lastenv["_"][$key] }
    return $v
}

$output_dir             = Get-Value $envContent $lastenv 'OUTPUT_DIR'
$logging_dir            = Get-Value $envContent $lastenv 'LOGGING_DIR'
$rsync_source_path_host = Get-Value $envContent $lastenv 'RSYNC_SOURCE_PATH_HOST'
$backup_folder_host     = Get-Value $envContent $lastenv 'BACKUP_FOLDER_HOST'
$rsync_dest_host        = Get-Value $envContent $lastenv 'RSYNC_DEST_HOST'
$rsync_dest_user        = Get-Value $envContent $lastenv 'RSYNC_DEST_USER'
$rsync_dest_path        = Get-Value $envContent $lastenv 'RSYNC_DEST_PATH'

# OUTPUT_DIR
$output_dir = Set-Path "$output_dir" "Directory for output csv?"
$output_dir = $output_dir.Replace('\', '/')
$lastenv["_"]["OUTPUT_DIR"] = $output_dir

# LOGGING_DIR
$logging_dir = Set-Path "$logging_dir" "Directory for logging?"
$logging_dir = $logging_dir.Replace('\', '/')
$lastenv["_"]["LOGGING_DIR"] = $logging_dir

# RSYNC_SOURCE_PATH_HOST
$rsync_source_path_host = Set-Path "$rsync_source_path_host" "Host path for rsync source?"
$rsync_source_path_host = $rsync_source_path_host.Replace('\', '/')
$lastenv["_"]["RSYNC_SOURCE_PATH_HOST"] = $rsync_source_path_host

# BACKUP_FOLDER_HOST
$backup_folder_host = Set-Path "$backup_folder_host" "Host path for backups?"
$backup_folder_host = $backup_folder_host.Replace('\', '/')
$lastenv["_"]["BACKUP_FOLDER_HOST"] = $backup_folder_host

# RSYNC_DEST_HOST
if (-not $rsync_dest_host) { $rsync_dest_host = Read-Host "Rsync destination host?" }
$lastenv["_"]["RSYNC_DEST_HOST"] = $rsync_dest_host

# RSYNC_DEST_USER
if (-not $rsync_dest_user) { $rsync_dest_user = Read-Host "Rsync destination user?" }
$lastenv["_"]["RSYNC_DEST_USER"] = $rsync_dest_user

# RSYNC_DEST_PATH
if (-not $rsync_dest_path) { $rsync_dest_path = Read-Host "Rsync destination path?" }
$lastenv["_"]["RSYNC_DEST_PATH"] = $rsync_dest_path

# Update .env line-by-line to preserve comments, formatting, and unmanaged variables.
# Using Out-IniFile for .env is unreliable — it drops lines with special characters (backslashes,
# quoted paths, apostrophes in paths).
$envContent = $envContent | ForEach-Object {
    if      ($_ -match '^OUTPUT_DIR=')            { "OUTPUT_DIR=$output_dir" }
    elseif  ($_ -match '^LOGGING_DIR=')           { "LOGGING_DIR=$logging_dir" }
    elseif  ($_ -match '^RSYNC_SOURCE_PATH_HOST='){ "RSYNC_SOURCE_PATH_HOST=$rsync_source_path_host" }
    elseif  ($_ -match '^BACKUP_FOLDER_HOST=')    { "BACKUP_FOLDER_HOST=$backup_folder_host" }
    elseif  ($_ -match '^RSYNC_DEST_HOST=')       { "RSYNC_DEST_HOST=$rsync_dest_host" }
    elseif  ($_ -match '^RSYNC_DEST_USER=')       { "RSYNC_DEST_USER=$rsync_dest_user" }
    elseif  ($_ -match '^RSYNC_DEST_PATH=')       { "RSYNC_DEST_PATH=$rsync_dest_path" }
    else    { $_ }
}
$envContent | Set-Content .env -Encoding ASCII

# Save .lastenv using PsIni (values here are always simple paths/hostnames)
$lastenv | Out-IniFile -FilePath .lastenv -Encoding ASCII -Force
