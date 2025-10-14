# setup.ps1

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "== Stream Control Center - PowerShell Setup ==" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host

# --- Konfiguration ---
$PythonUrl = "https://www.python.org/ftp/python/3.11.5/python-3.11.5-embed-amd64.zip"
$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$PythonDir = ".\python_embed"
$FfmpegDir = ".\ffmpeg"
$PythonExe = Join-Path $PythonDir "python.exe"
$FfmpegExe = Join-Path $FfmpegDir "bin\ffmpeg.exe"

# --- Schritt 1: Python einrichten ---
if (Test-Path $PythonExe) {
    Write-Host "Python scheint bereits vorhanden zu sein. Download wird übersprungen." -ForegroundColor Yellow
} else {
    Write-Host "--- Lade portables Python herunter ---"
    Invoke-WebRequest -Uri $PythonUrl -OutFile 'python.zip'
    Write-Host "--- Entpacke Python ---"
    Expand-Archive -Path 'python.zip' -DestinationPath $PythonDir -Force
    Remove-Item 'python.zip'
    Write-Host "Python erfolgreich eingerichtet." -ForegroundColor Green
}
Write-Host

# --- Schritt 2: FFmpeg einrichten ---
if (Test-Path $FfmpegExe) {
    Write-Host "FFmpeg scheint bereits vorhanden zu sein. Download wird übersprungen." -ForegroundColor Yellow
} else {
    Write-Host "--- Lade FFmpeg herunter ---"
    Invoke-WebRequest -Uri $FfmpegUrl -OutFile 'ffmpeg.zip'
    
    Write-Host "--- Entpacke und verschiebe FFmpeg (Sichere Methode) ---"
    $tempDir = '.\temp_ffmpeg'
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    Expand-Archive -Path '.\ffmpeg.zip' -DestinationPath $tempDir -Force
    
    $extractedItems = Get-ChildItem -Path $tempDir
    if ($extractedItems.Count -eq 1 -and $extractedItems[0].PSIsContainer) {
        # Fall 1: ZIP enthält einen einzelnen Hauptordner
        $sourcePath = Join-Path $extractedItems[0].FullName '*'
    } else {
        # Fall 2: ZIP extrahiert Inhalte direkt
        $sourcePath = Join-Path $tempDir '*'
    }
    
    New-Item -ItemType Directory -Path $FfmpegDir -Force | Out-Null
    Move-Item -Path $sourcePath -Destination $FfmpegDir -Force
    
    Remove-Item -Path $tempDir -Recurse -Force
    Remove-Item -Path '.\ffmpeg.zip' -Force
    Write-Host "FFmpeg erfolgreich eingerichtet." -ForegroundColor Green
}
Write-Host

# --- Schritt 3: Pip und Pakete installieren ---
Write-Host "--- Richte pip ein und installiere Pakete ---"
$PthFile = Join-Path $PythonDir "python311._pth"

if (Test-Path (Join-Path $PythonDir "Scripts\pip.exe")) {
    Write-Host "pip ist bereits installiert." -ForegroundColor Yellow
} else {
    Write-Host "Aktiviere site-packages und installiere pip..."
    (Get-Content $PthFile) -replace '#import site', 'import site' | Set-Content $PthFile
    Invoke-WebRequest -Uri https://bootstrap.pypa.io/get-pip.py -OutFile 'get-pip.py'
    & $PythonExe get-pip.py
    Remove-Item 'get-pip.py'
    Write-Host "pip-Installation abgeschlossen." -ForegroundColor Green
}

Write-Host "Installiere notwendige Pakete aus requirements.txt..."
& $PythonExe -m pip install -r requirements.txt

Write-Host
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "== Setup erfolgreich abgeschlossen! ==" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "Du kannst die Anwendung jetzt mit der start.bat starten."
Write-Host
Read-Host "Druecke Enter zum Beenden"