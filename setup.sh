#!/bin/bash

echo "=========================================================="
echo "== Stream Control Center - Vollautomatisches Setup (Unix) =="
echo "=========================================================="
echo ""

# --- Konfiguration ---
# Hinweis: Diese URLs sind für x86_64 Linux.
PYTHON_URL="https://github.com/indygreg/python-build-standalone/releases/download/20240107/cpython-3.11.7+20240107-x86_64-unknown-linux-gnu-install_only.tar.gz"
FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
PYTHON_DIR="./python_embed"
FFMPEG_DIR="./ffmpeg"
PYTHON_EXE="$PYTHON_DIR/bin/python3"

# --- NEU: Werkzeuge prüfen ---
command -v curl >/dev/null 2>&1 || { echo >&2 "FEHLER: 'curl' wird benötigt, ist aber nicht installiert. Abbruch."; exit 1; }
command -v tar >/dev/null 2>&1 || { echo >&2 "FEHLER: 'tar' wird benötigt, ist aber nicht installiert. Abbruch."; exit 1; }

# --- Schritt 1: Python einrichten ---
if [ -f "$PYTHON_EXE" ]; then
    echo "Python scheint bereits vorhanden zu sein. Download wird übersprungen."
else
    echo "--- Lade portables Python herunter ---"
    curl -L "$PYTHON_URL" -o python.tar.gz || { echo "FEHLER: Download von Python fehlgeschlagen."; exit 1; }
    echo "--- Entpacke Python ---"
    mkdir -p "$PYTHON_DIR"
    tar -xzf python.tar.gz -C "$PYTHON_DIR" --strip-components=1 || { echo "FEHLER: Entpacken von Python fehlgeschlagen."; exit 1; }
    rm python.tar.gz
    echo "Python erfolgreich eingerichtet."
    echo ""
fi

# --- Schritt 2: FFmpeg einrichten ---
if [ -f "$FFMPEG_DIR/ffmpeg" ]; then
    echo "FFmpeg scheint bereits vorhanden zu sein. Download wird übersprungen."
else
    echo "--- Lade FFmpeg herunter ---"
    curl -L "$FFMPEG_URL" -o ffmpeg.tar.xz || { echo "FEHLER: Download von FFmpeg fehlgeschlagen."; exit 1; }
    echo "--- Entpacke FFmpeg ---"
    mkdir -p "$FFMPEG_DIR"
    tar -xf ffmpeg.tar.xz -C "$FFMPEG_DIR" --strip-components=1 || { echo "FEHLER: Entpacken von FFmpeg fehlgeschlagen."; exit 1; }
    rm ffmpeg.tar.xz
    echo "FFmpeg erfolgreich eingerichtet."
    echo ""
fi

# --- Schritt 3: Pip und Pakete installieren ---
echo "--- Installiere Pakete aus requirements.txt ---"
"$PYTHON_EXE" -m pip install -r requirements.txt || { echo "FEHLER: Paketinstallation fehlgeschlagen."; exit 1; }

echo ""
echo "=========================================================="
echo "== Setup erfolgreich abgeschlossen! =="
echo "=========================================================="
echo "Du kannst die Anwendung jetzt mit der start.sh starten."
echo "Stelle sicher, dass die Datei ausführbar ist: chmod +x start.sh"
echo ""