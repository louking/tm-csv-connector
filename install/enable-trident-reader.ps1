Import-Env
$arch = (32, 64)[[bool] ${env:ProgramFiles(x86)}]
& nssm-2.24/win$arch/nssm install TridentReader "$pwd/trident-reader/trident-reader" | Out-Null
& nssm-2.24/win$arch/nssm set TridentReader Description "Time Machine Reader" | Out-Null
& nssm-2.24/win$arch/nssm set TridentReader AppStdout "$env:LOGGING_DIR/trident-reader.log" | Out-Null
& nssm-2.24/win$arch/nssm set TridentReader AppStderr "$env:LOGGING_DIR/trident-reader.log" | Out-Null
& nssm-2.24/win$arch/nssm start TridentReader