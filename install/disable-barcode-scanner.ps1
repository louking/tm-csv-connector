$arch = (32, 64)[[bool] ${env:ProgramFiles(x86)}]
& nssm-2.24/win$arch/nssm stop BarccodeScanner confirm 2>&1 3>&1 | Out-Null
& nssm-2.24/win$arch/nssm remove BarccodeScanner confirm 2>&1 3>&1 | Out-Null
