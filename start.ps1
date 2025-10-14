# start.ps1

Write-Host "Starte Stream Control Center..."
try {
    & ".\python_embed\python.exe" "web_manager.py"
} catch {
    Write-Host "Fehler beim Starten der Anwendung:" -ForegroundColor Red
    Write-Host $_
}

Write-Host
Read-Host "Anwendung beendet. Druecke Enter zum Schliessen des Fensters."