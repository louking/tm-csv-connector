# generate database and other passwords (https://www.sharepointdiary.com/2020/04/powershell-generate-random-password.html)
function New-RandomPassword {
    param (
        [Parameter(Mandatory)]
        [int] $length
    )
 
    $charSet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.ToCharArray()
 
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    $bytes = New-Object byte[]($length)
  
    $rng.GetBytes($bytes)
  
    $result = New-Object char[]($length)
  
    for ($i = 0 ; $i -lt $length ; $i++) {
        $result[$i] = $charSet[$bytes[$i]%$charSet.Length]
    }
 
    return -join $result
}

# only set passwords if they haven't been set before. If they've been set before, the database has already
# been created and we don't want to take on updating the passwords in this install script

if (-not (Test-Path config/db)) { New-Item -Path config/db -ItemType Directory | Out-Null }

# root password
$rootpw_path = "config/db/root-password.txt"
if (-not (Test-Path $rootpw_path)) {
    $default = New-RandomPassword 16
    if (-not ($rootpw = Read-Host "root db password [$default]")) { $rootpw = $default } # https://stackoverflow.com/a/59771226
    $rootpw | Out-File -FilePath $rootpw_path -Encoding ASCII -Force -NoNewline
}

# tm-csv-connector password
$apppw_path = "config/db/tm-csv-connector-password.txt"
if (-not (Test-Path $apppw_path)) {
    $default = New-RandomPassword 16
    if (-not ($apppw = Read-Host "tm-csv-connector db password [$default]")) { $apppw = $default } # https://stackoverflow.com/a/59771226
    $apppw | Out-File -FilePath $apppw_path -Encoding ASCII -Force -NoNewline
}

# other passwords (not database passwords, but used in the app)
# NOTE: creation of these files will only happen in development, as this script is not run for simulation mode on a web server

# mail password (simulation mode)
$mailpw_path = "config/db/mail-password.txt"
while (-not (Test-Path $mailpw_path)) {
    if ($mailpw = Read-Host "mail password []") { $mailpw | Out-File -FilePath $mailpw_path -Encoding ASCII -Force -NoNewline } # must set
}

# security password salt (simulation mode)
$securitypwsalt_path = "config/db/security-password-salt.txt"
while (-not (Test-Path $securitypwsalt_path)) {
    if ($securitypwsalt = Read-Host "security password salt []") { $securitypwsalt | Out-File -FilePath $securitypwsalt_path -Encoding ASCII -Force -NoNewline } # must set
}

# superadmin user password (simulation mode)
$sauser_path = "config/db/super-admin-user-password.txt"
if (-not (Test-Path $sauser_path)) {
    $default = New-RandomPassword 16
    if (-not ($sauser = Read-Host "super-admin-user password [$default]")) { $sauser = $default } # https://stackoverflow.com/a/59771226
    $sauser | Out-File -FilePath $sauser_path -Encoding ASCII -Force -NoNewline
}

