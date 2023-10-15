$arch = (32, 64)[[bool] ${env:ProgramFiles(x86)}]
& nssm-2.24/win$arch/nssm stop TmReader confirm 2>&1 3>&1 | Out-Null
& nssm-2.24/win$arch/nssm remove TmReader confirm 2>&1 3>&1 | Out-Null
