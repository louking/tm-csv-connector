$arch = (32, 64)[[bool] ${env:ProgramFiles(x86)}]
& nssm-2.24/win$arch/nssm stop TmReader confirm
& nssm-2.24/win$arch/nssm remove TmReader confirm
& nssm-2.24/win$arch/nssm install TmReader "$pwd\tm-reader\tm-reader"
& nssm-2.24/win$arch/nssm set TmReader Description "Time Machine Reader"
& nssm-2.24/win$arch/nssm set TmReader AppStdout "<logpath>\tm-reader.log"
& nssm-2.24/win$arch/nssm set TmReader AppStderr "<logpath>\tm-reader.log"
& nssm-2.24/win$arch/nssm start TmReader