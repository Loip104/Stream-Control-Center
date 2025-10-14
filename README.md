# Stream Control Center

Ein web-basiertes Kontrollzentrum zum Verwalten und Streamen einer Video-Playlist als 24/7-Kanal auf Twitch. Das Projekt ist vollständig portabel für Windows.

## Features

* **Playlist-Management:** Playlists erstellen und per Drag & Drop sortieren. Titel, Spiel/Kategorie und Aktiv-Status bearbeiten.
* **Rotationen:** Abfolgen von Playlists erstellen, die zu einer Master-Playlist kompiliert werden können.
* **Video-Bibliothek:** Globale Verwaltung aller Videodateien, inklusive Analyse-Tools und Thumbnail-Generierung.
* **Sendeplan:** Wöchentlichen Sendeplan erstellen, um automatisch zu bestimmten Zeiten Playlists zu wechseln.
* **Dynamisches Overlay:** Live konfigurierbares "Now Playing"-Text-Overlay.
* **Integrierter Twitch-Bot:**
    * Start/Stop und Überwachung über das Web-Interface.
    * Dynamisches Befehls-Management über die UI (inkl. Aktionen, Berechtigungen, Cooldowns).
    * Live-Chat-Anzeige im Web-Interface.
* **Live-API:** JSON-Endpunkt (`/api/now_playing`) mit detaillierten Live-Daten für externe Tools.
* **Voll portabel:** Benötigt keine vorinstallierte Version von Python oder FFmpeg auf dem System.

## Installation & Setup

Dieses Projekt ist für einen einfachen Start auf Windows-Systemen konzipiert.

1.  Lade das Projekt als ZIP-Datei herunter und entpacke es in einen Ordner deiner Wahl.
2.  Führe die **`setup.bat`**-Datei per Doppelklick aus.
    * Dieses Skript lädt automatisch die benötigte portable Version von Python und FFmpeg herunter.
    * Anschließend installiert es alle notwendigen Python-Pakete.
    * Dieser Schritt muss nur **ein einziges Mal** ausgeführt werden.

### Für Linux / macOS

Das Projekt enthält auch Setup- und Start-Skripte für Unix-basierte Systeme.

1.  **Skripte ausführbar machen:** Öffne ein Terminal im Projektordner und führe aus:
    ```bash
    chmod +x setup.sh
    chmod +x start.sh
    ```
2.  **Setup ausführen:** Starte das Setup-Skript. Es lädt die passenden Versionen von Python und FFmpeg herunter und installiert die Abhängigkeiten.
    ```bash
    ./setup.sh
    ```
3.  **Anwendung starten:**
    ```bash
    ./start.sh
    ```

## Benutzung

1.  **Anwendung starten:** Führe nach dem Setup die **`start.bat`**-Datei per Doppelklick aus. Dadurch wird der Web-Manager gestartet.
2.  **Web-Interface öffnen:** Öffne deinen Browser und gehe zur Adresse, die im Terminal angezeigt wird (standardmäßig `http://127.0.0.1:5000`).
3.  **Konfigurieren:** Gehe zum "Streamer-Config"-Tab und trage alle deine Daten ein (Twitch-Keys, Stream-Key, Bot-Daten etc.). Speichere die Konfiguration.
4.  **Streamer starten:** Navigiere zum "Prozess-Steuerung"-Tab und klicke auf "Streamer Starten".
5.  **Bot starten:** Navigiere zum "Bot"-Tab und klicke auf "Bot Starten".

Das System ist nun vollständig betriebsbereit.