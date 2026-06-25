# xyz-sdr — restaurar consola PowerShell tras salida brusca de la TUI
# Uso: .\scripts\restore_terminal.ps1
# (Si ves [555;32;8M al mover el ratón, ejecuta esto en la misma ventana.)

$esc = [char]27
$seq = "${esc}[<u${esc}[?1049l${esc}[?25h${esc}[?1004l${esc}[?2004l${esc}[?1000l${esc}[?1003l${esc}[?1015l${esc}[?1002l${esc}[?1006l${esc}[?1007l${esc}[0m"
try {
    [Console]::Write($seq)
    Write-Host ""
    Write-Host "[OK] Consola restaurada (modo ratón SGR desactivado)." -ForegroundColor Green
} catch {
    Write-Host -NoNewline $seq
    Write-Host ""
    Write-Host "[OK] Secuencias enviadas." -ForegroundColor Green
}
