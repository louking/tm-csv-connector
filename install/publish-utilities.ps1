# if (-not (Test-Path $HOME\Documents\WindowsPowerShell\Modules)) { New-Item -Type Directory $HOME\Documents\WindowsPowerShell\Modules  | Out-Null }
# Copy-Item -Path TMCSVutilities.psm1 -Destination $HOME\Documents\WindowsPowerShell\Modules | Out-Null

Import-Module ./TMCSVUtilities -Force
