Import-Env
$arch = (32, 64)[[bool] ${env:ProgramFiles(x86)}]
& nssm-2.24/win$arch/nssm install TmReader "$pwd/tm-reader/tm-reader" | Out-Null
& nssm-2.24/win$arch/nssm set TmReader Description "Time Machine Reader" | Out-Null
& nssm-2.24/win$arch/nssm set TmReader AppStdout "$env:LOGGING_DIR/tm-reader.log" | Out-Null
& nssm-2.24/win$arch/nssm set TmReader AppStderr "$env:LOGGING_DIR/tm-reader.log" | Out-Null
& nssm-2.24/win$arch/nssm start TmReader