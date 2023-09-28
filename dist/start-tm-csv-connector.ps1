$arch = (32, 64)[[bool] ${env:ProgramFiles(x86)}]
& nssm-2.24/win$arch/nssm install TmCsvConnector "$pwd\tm-csv-connector\tm-csv-connector"
& nssm-2.24/win$arch/nssm set TmCsvConnector Description "Time Machine CSV Connector"
& nssm-2.24/win$arch/nssm set TmCsvConnector AppStdout "<logpath>\tm-csv-connector.log"
& nssm-2.24/win$arch/nssm set TmCsvConnector AppStderr "<logpath>\tm-csv-connector.log"
& nssm-2.24/win$arch/nssm start TmCsvConnector