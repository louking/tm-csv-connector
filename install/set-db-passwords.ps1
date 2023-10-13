# generate database passwords (https://www.sharepointdiary.com/2020/04/powershell-generate-random-password.html)
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

# root password
$rootpw_path = "config/db/root-password.txt"
if (-not (Test-Path $rootpw_path)) {
    $default = New-RandomPassword 16
    if (-not ($rootpw = Read-Host "root db password [$default]")) { $rootpw = $default } # https://stackoverflow.com/a/59771226
    $rootpw | Out-IniFile -FilePath $rootpw_path -Encoding ASCII -Force
}

# tm-csv-connector password
$apppw_path = "config/db/tm-csv-connector-password.txt"
if (-not (Test-Path $apppw_path)) {
    $default = New-RandomPassword 16
    if (-not ($apppw = Read-Host "tm-csv-connector db password [$default]")) { $apppw = $default } # https://stackoverflow.com/a/59771226
    $apppw | Out-IniFile -FilePath $apppw_path -Encoding ASCII -Force    
}
