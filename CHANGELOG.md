# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)
## [0.6.1] - 2025-11-17

### Behoben
- **Kritischer Fehler (Neustart-Logik):** Ein Fehler wurde behoben, bei dem die 120-Sekunden-Offline-Pause (für den 48h-Reset) fälschlicherweise von allen "sofortigen" UI-Aktionen ausgelöst wurde (z.B. "Nächster Titel", "Playlist aktivieren (Sofort)"). Die Signale wurden in `scheduled_restart` (für den Timer, mit Pause) und `force_restart` (für die UI, sofort) getrennt.
- **Kritischer Fehler (Auto-Restart Timer):** Ein Logikfehler im `auto_restart_monitor` wurde behoben, der verhinderte, dass der Neustart zu einer festen Uhrzeit (z.B. "17:31") zuverlässig ausgelöst wurde. Die Zeitprüfung wurde von einer exakten (`==`) auf eine relative (`>=`) Prüfung umgestellt und das Status-Handling korrigiert.
- **Kritischer Fehler (Bot-Start):** Eine Reihe von Python-Fehlern (`SyntaxError`, `UnboundLocalError`, `TypeError`) in `twitch_bot.py` wurden behoben, die den Start des Bots komplett verhinderten. Der Bot ist nun wieder funktionsfähig.
- **Kritischer Fehler (Streamer-Stabilität):** Ein Fehler wurde behoben, durch den der Streamer (`stream_v3.py`) abstürzte, wenn ein Videodateiname ein Apostroph (`'`) enthielt (z.B. `A Juggler's Tale.mp4`). Die Dateipfade werden nun beim Erstellen der `ffmpeg_playlist.txt` korrekt escaped.

---
## [0.6.0] - 2025-10-28

### Hinzugefügt
- **Automatischer Stream-Neustart:** Implementiert eine Funktion, um den Stream automatisch neu zu starten und so den 48-Stunden-Disconnect von Twitch zu umgehen.
    - **Konfigurierbar:** Im "Streamer-Config"-Tab können Nutzer wählen zwischen einem Neustart nach einem festen Intervall (z.B. alle 24 Stunden) oder zu einer festen täglichen Uhrzeit (z.B. 04:00 Uhr). Beide Optionen können kombiniert werden.
    - **Erzwungene Offline-Zeit:** Um sicherzustellen, dass Twitch die alte Sitzung beendet, legt der Streamer nach dem Signal eine Zwangspause von 2 Minuten ein, bevor der Stream neu gestartet wird.
- **Live Twitch Spiel/Kategorie-Suche:** Im "Playlist"-Tab wurde eine Autovervollständigungsfunktion für das Feld "Spiel / Kategorie" hinzugefügt.
    - Während der Eingabe wird die Twitch-API live abgefragt (`/helix/search/categories`).
    - Eine Vorschlagsliste mit passenden, offiziellen Twitch-Kategorien wird unter dem Feld angezeigt, um Fehleingaben zu vermeiden und den "Just Chatting"-Fallback-Bug zu beheben.
- **Lokalisierung:** Neue Texte für die Auto-Restart-Funktion und die Spielsuche wurden hinzugefügt und übersetzbar gemacht (DE/EN).

### Behoben
- **Rotationen (Metadaten-Verlust):** Ein kritischer Fehler wurde behoben, bei dem das Kompilieren einer Rotation die manuell gesetzten Titel und Spiele aus den Quell-Playlists mit Standardwerten überschrieben hat. Alle Metadaten (Titel, Spiel, Aktiv-Status) werden nun korrekt 1:1 in die Rotations-Playlist kopiert.
- **UI (Playlist-Titel):** Ein Anzeigefehler im "Playlist"-Tab wurde behoben, bei dem lange Titel trotz vorhandenem Scrollbalken weiterhin mit "..." abgeschnitten wurden. Der volle Titel ist nun beim Hovern und Scrollen lesbar.
- **UI (Log-Anzeige):** Probleme wurden behoben, die verhinderten, dass die Live-Logs (`streamer.log`, `ffmpeg.log`) im "Prozess-Steuerung"-Tab korrekt angezeigt wurden. Dies wurde durch korrektes Schließen von Datei-Handles im Manager und das Verhindern von Browser-Caching gelöst.
- **Übersetzungssystem (`pybabel`):** Diverse Probleme mit `pybabel` (falsche Konfiguration, Encoding-Fehler, nicht aktualisierte `.po`-Dateien) wurden behoben. Die Extraktion und Aktualisierung der Sprachdateien funktioniert nun zuverlässig.
- **Stabilität (`stream_v3.py`):** Ein `IndentationError` wurde behoben, der den Start des Streamers verhinderte. Die Logik zum Setzen/Zurücksetzen von Neustart-Signalen und Zeitstempeln in `session.json` wurde robuster gestaltet, um Konflikte zwischen `web_manager.py` und `stream_v3.py` zu vermeiden.

---
## [0.5.04] - 2025-10-18

### Hinzugefügt
- **Twitch OAuth 2.0 Integration:** Implementierung des vollständigen "Authorization Code Flow" für eine automatische und sichere Authentifizierung.
    - Ein neuer "Mit Twitch verbinden"-Button im "Streamer-Config"-Tab leitet den Benutzer zur Twitch-Autorisierungsseite weiter.
    - Eine neue `/twitch/callback`-Route verarbeitet die Rückkehr von Twitch, tauscht den Autorisierungscode gegen einen Access- und einen Refresh-Token ein und speichert diese sicher in der `config.json`.
    - Eine automatische Token-Erneuerung wurde implementiert. Der Access-Token wird nun bei Bedarf selbstständig erneuert, ohne dass ein manuelles Eingreifen erforderlich ist.
- **HTTPS für die lokale Entwicklung:** Der Webserver läuft nun standardmäßig über HTTPS (`ssl_context='adhoc'`), um die neuen Anforderungen der Twitch-API für Redirect-URIs zu erfüllen. `pyOpenSSL` wurde als neue Abhängigkeit hinzugefügt.

### Geändert
- **Zentrales Token-Management:** Die gesamte Logik zur Handhabung von Twitch-Tokens wurde in ein neues, dediziertes Skript `token_manager.py` ausgelagert. `stream_v3.py` nutzt nun ausschließlich dieses Modul, um einen gültigen Token zu erhalten.
- **Dynamische Port-Verwaltung:** Die Anwendung liest den Port nun konsistent aus der `manager_config.json`, um Port-Konflikte zu vermeiden und die Konfiguration zu vereinfachen. Der hartcodierte Fallback-Port wurde entfernt.

### Behoben
- **Twitch API Authentifizierung (`401 Unauthorized`):** Der kritische Fehler, bei dem API-Anfragen nach kurzer Zeit fehlschlugen, wurde durch die Implementierung der automatischen Token-Erneuerung behoben. Alle API-Aufrufe nutzen nun garantiert einen gültigen Token.
- **Falsche Zeitanzeige im Header:** Ein Fehler in der JavaScript-Funktion `formatTime` wurde korrigiert, der dazu führte, dass die Stunden in der Video-Laufzeitanzeige abgeschnitten wurden.
- **Fehlende `flash`-Nachrichten:** Das Problem, dass Erfolgs- oder Fehlermeldungen nicht angezeigt wurden, wurde durch das Hinzufügen des fehlenden `flash`-Message-Containers in der `index.html` behoben.
- **Defektes Layout und leere Tabs:** Diverse HTML-Strukturfehler (falsch platzierte `</form>`- und `<div>`-Tags) wurden in der `index.html` korrigiert. Das Layout wird nun wieder korrekt dargestellt und alle Tabs funktionieren wie erwartet.
- **`ModuleNotFoundError` für `token_manager`:** Ein Fehler wurde behoben, der verhinderte, dass die als separate Prozesse gestarteten Skripte (`stream_v3.py`, `twitch_bot.py`) das neue `token_manager.py`-Modul finden konnten.
- **`TypeError` in `token_manager.py`:** Ein Syntaxfehler in den `print`-Anweisungen wurde korrigiert, der zum Absturz des Skripts nach erfolgreicher Token-Speicherung führte und so die Erfolgsmeldung im UI verhinderte.

---
## [0.5.03] - 2025-10-17

### Geändert
- **Internationalisierung (i18n):** Das gesamte Projekt wurde für Mehrsprachigkeit vorbereitet.
    - **Backend:** Alle für den Benutzer sichtbaren Log-Ausgaben in `stream_v3.py` und `twitch_bot.py` wurden mittels `gettext` übersetzbar gemacht.
    - **Frontend:** Die gesamte `web_manager.py` und `index.html` wurden mittels `Flask-Babel` für die Übersetzung vorbereitet. Alle Texte, einschließlich `flash`-Nachrichten, `alert`-Boxen, `confirm`-Dialoge, `title`-Attribute und `placeholder`, sind nun übersetzbar.
    - **Sprachauswahl:** Im "Manager-Config"-Tab wurde eine Option hinzugefügt, um die Sprache der Benutzeroberfläche dynamisch umzuschalten.

### Behoben
- Ein Jinja2 `TemplateSyntaxError` wurde behoben, der durch inkorrektes Escaping in einem `confirm()`-Dialog im "Rotations"-Tab verursacht wurde.
- Diverse HTML-Strukturfehler in der `index.html` wurden korrigiert, die zum fehlerhaften Rendern von Tabs führten.

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