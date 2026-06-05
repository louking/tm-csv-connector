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

# https://stackoverflow.com/a/22804178/799921
$env = Get-IniContent .env

# check if we've installed before
if (Test-Path .lastenv) {
    $lastenv = Get-IniContent .lastenv
    $output_dir = $lastenv["_"]["OUTPUT_DIR"]
    $logging_dir = $lastenv["_"]["LOGGING_DIR"]
    $rsync_source_path_host = $lastenv["_"]["RSYNC_SOURCE_PATH_HOST"]
    $backup_folder_host = $lastenv["_"]["BACKUP_FOLDER_HOST"]
    $rsync_dest_host = $lastenv["_"]["RSYNC_DEST_HOST"]
    $rsync_dest_user = $lastenv["_"]["RSYNC_DEST_USER"]
    $rsync_dest_path = $lastenv["_"]["RSYNC_DEST_PATH"]
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

# RSYNC_SOURCE_PATH_HOST
$rsync_source_path_host = Set-Path "$rsync_source_path_host" "Host path for rsync source?"
$rsync_source_path_host = $rsync_source_path_host.Replace('\', '/')
$env["_"]["RSYNC_SOURCE_PATH_HOST"] = $rsync_source_path_host
$lastenv["_"]["RSYNC_SOURCE_PATH_HOST"] = $rsync_source_path_host

# BACKUP_FOLDER_HOST
$backup_folder_host = Set-Path "$backup_folder_host" "Host path for backups?"
$backup_folder_host = $backup_folder_host.Replace('\', '/')
$env["_"]["BACKUP_FOLDER_HOST"] = $backup_folder_host
$lastenv["_"]["BACKUP_FOLDER_HOST"] = $backup_folder_host

# RSYNC_DEST_HOST
if (-not $rsync_dest_host) { $rsync_dest_host = Read-Host "Rsync destination host?" }
$env["_"]["RSYNC_DEST_HOST"] = $rsync_dest_host
$lastenv["_"]["RSYNC_DEST_HOST"] = $rsync_dest_host

# RSYNC_DEST_USER
if (-not $rsync_dest_user) { $rsync_dest_user = Read-Host "Rsync destination user?" }
$env["_"]["RSYNC_DEST_USER"] = $rsync_dest_user
$lastenv["_"]["RSYNC_DEST_USER"] = $rsync_dest_user

# RSYNC_DEST_PATH
if (-not $rsync_dest_path) { $rsync_dest_path = Read-Host "Rsync destination path?" }
$env["_"]["RSYNC_DEST_PATH"] = $rsync_dest_path
$lastenv["_"]["RSYNC_DEST_PATH"] = $rsync_dest_path

# save new .env, .lastenv
$env | Out-IniFile -FilePath .env -Encoding ASCII -Force
$lastenv | Out-IniFile -FilePath .lastenv -Encoding ASCII -Force
