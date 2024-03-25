Import-Env
$arch = (32, 64)[[bool] ${env:ProgramFiles(x86)}]
& nssm-2.24/win$arch/nssm install BarccodeScanner "$pwd/barcode-scanner/barcode-scanner" | Out-Null
& nssm-2.24/win$arch/nssm set BarccodeScanner Description "Barcode Scanner Reader" | Out-Null
& nssm-2.24/win$arch/nssm set BarccodeScanner AppStdout "$env:LOGGING_DIR/barcode-scanner.log" | Out-Null
& nssm-2.24/win$arch/nssm set BarccodeScanner AppStderr "$env:LOGGING_DIR/barcode-scanner.log" | Out-Null
& nssm-2.24/win$arch/nssm start BarccodeScanner