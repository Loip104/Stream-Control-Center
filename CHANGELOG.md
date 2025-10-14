# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---
## [0.5.01] - 2025-10-14

### Hinzugefügt
- Eine Info-Leiste ("App Bar") wurde am oberen Rand der Anwendung hinzugefügt. Sie zeigt die aktuelle Version, einen Link zur Fehler-Meldung und einen Link zum GitHub-Projekt.

---
## [0.5.0] - 2025-10-14

### Hinzugefügt
- **Update-Prüfung:** Die Anwendung prüft beim Start auf neue Versionen und zeigt einen Hinweis an, wenn ein Update verfügbar ist.
- **Installations-Anleitung:** Eine dedizierte `anleitung.html`-Seite wurde hinzugefügt, die eine detaillierte Schritt-für-Schritt-Anleitung inklusive Warnhinweisen enthält.
- **GitHub Integration:** Das Projekt wurde auf GitHub hochgeladen. Links zur Fehler-Meldung (`Issues`) wurden in die Anwendung und auf der Webseite integriert.
- **Setup-Verbesserungen:** Die `setup.bat` wurde durch ein robustes PowerShell-Skript (`setup.ps1`) und einen neuen Starter ersetzt, um Installationsprobleme unter Windows zu beheben. Analoge Skripte für Linux/macOS (`setup.sh`, `start.sh`) wurden optimiert.


### Behoben
- **Playlist-Tab:** Zahlreiche kritische Bugs im Playlist-Tab wurden behoben, darunter:
    - Nicht funktionierende Buttons für "Duplizieren" und "Entfernen".
    - Der "Änderungen speichern"-Button ist jetzt voll funktionsfähig und speichert den Aktiv-Status von Checkboxen korrekt.
    - Drag & Drop zum Sortieren von Einträgen funktioniert nun zuverlässig.
- **Thumbnail-Generierung:** Der Fehler bei der Thumbnail-Generierung (`[WinError 2]`) wurde durch die Verwendung des korrekten Pfades zur `ffmpeg.exe` behoben.

---
## [Unreleased] - Vorherige Versionen

### Hinzugefügt
- **Streaming-Kern:** Stabiler `stream_v3.py` Kern mit Signalverarbeitung für Neustarts.
- **Web-Manager:** Eine Flask-basierte Weboberfläche zur Steuerung des gesamten Programms.
- **ID-System:** Einheitliche Verwendung von IDs für Videos und Playlisten im gesamten Backend.
- **Bibliothek & Import:** Funktionen zur Synchronisierung von Video-Ordnern, zum Importieren neuer Videos und zur Thumbnail-Generierung.
- **Playlist- & Rotations-Management:** Voll funktionsfähige Tabs zur Erstellung, Speicherung und Kompilierung von Playlisten und Rotationen.
- **Twitch-Bot:** Ein integrierter Twitch-Bot, der über die Weboberfläche gestartet, gestoppt und konfiguriert werden kann. Bot-Befehle sind über die UI vollständig anpassbar.
- **Portabilität:** Das Projekt ist durch Setup-Skripte vollständig portabel und benötigt keine vorinstallierte Software.
- **API-Endpunkt:** Ein `/api/now_playing`-Endpunkt liefert Live-Daten über den Stream.