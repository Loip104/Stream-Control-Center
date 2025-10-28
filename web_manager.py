import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uuid
import csv
import json
import shutil
import random
import time
import subprocess
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session
from werkzeug.utils import secure_filename
import glob
import platform
import signal
import psutil
from collections import deque
from datetime import datetime, timedelta
import requests
from flask_babel import Babel, _
from flask import g
from token_manager import exchange_code_for_token, save_tokens_to_config
import threading
from datetime import datetime, timedelta
from colorama import Fore, init
from token_manager import get_valid_token

init(autoreset=True)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_EXE = os.path.join(BASE_DIR, 'ffmpeg', 'bin', 'ffmpeg.exe')
FFPROBE_EXE = os.path.join(BASE_DIR, 'ffmpeg', 'bin', 'ffprobe.exe')
PYTHON_EXE = os.path.join(BASE_DIR, 'python_embed', 'python.exe')

# --- Configuration ---
WATCH_DIR = '_neu_'
THUMBNAIL_DIR = 'thumbnails'
FONTS_DIR = 'fonts'
PLAYLIST_CSV = 'playlist.csv' # Wird als Fallback genutzt
MANAGER_CONFIG_JSON = 'manager_config.json'
CONFIG_JSON = 'config.json'
STATUS_JSON = 'status.json'
METADATA_CACHE_JSON = 'metadata_cache.json'
VALID_EXTENSIONS = ('.mp4', '.mkv', '.mov', '.avi', '.flv')
VALID_FONT_EXTENSIONS = ('.ttf', '.otf')

# --- App and i18n Initialization ---
app = Flask(__name__)
app.secret_key = 'your_very_secret_key_for_flash_messages'

# This is a regular function now, without the "@babel" decorator
def get_locale():
    """Ermittelt die aktive Sprache aus der Konfigurationsdatei."""
    try:
        if not hasattr(g, 'manager_config'):
            with open('manager_config.json', 'r', encoding='utf-8') as f:
                g.manager_config = json.load(f)
        return g.manager_config.get('language', 'de')
    except (FileNotFoundError, json.JSONDecodeError):
        return 'de'

# Initialize Babel and pass the function directly
babel = Babel(app, locale_selector=get_locale)
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

# In-memory cache for API data
api_cache = {'last_played': None, 'current_path': None}

def auto_restart_monitor():
    """Überwacht die Stream-Laufzeit und löst einen Neustart aus (Intervall ODER feste Zeit)."""
    print(f"{Fore.CYAN}" + _("Auto-Restart Monitor Thread gestartet."))
    
    while True:
        time.sleep(60) # Prüfe jede Minute
        
        try:
            config = {}
            session = {}
            try:
                with open(CONFIG_JSON, 'r', encoding='utf-8') as f: config = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                continue # Config fehlt, nächste Minute erneut versuchen
            
            try:
                # Lade BEIDE Dateien für einen vollständigen Status
                with open(STATUS_JSON, 'r', encoding='utf-8') as f_stat: 
                    session = json.load(f_stat)
                with open('session.json', 'r', encoding='utf-8') as f_sess: 
                    session.update(json.load(f_sess))
            except (FileNotFoundError, json.JSONDecodeError):
                continue # Session-Dateien fehlen, nächste Minute erneut versuchen

            # --- Lade alle Einstellungen ---
            ffmpeg_config = config.get('ffmpeg', {})
            interval_hours = ffmpeg_config.get('auto_restart_interval_hours', 0)
            restart_time_str = ffmpeg_config.get('auto_restart_time', '') # z.B. "04:00"
            
            # Lese die korrekten Zeitstempel
            proc_start_time_str = session.get('process_start_time') # Für Intervall
            streamer_status = session.get('status', 'Offline')
            
            if streamer_status != 'Online':
                continue # Nichts zu tun, wenn Stream offline ist
                
            if session.get('force_restart', False):
                continue # Signal wird bereits verarbeitet

            now = datetime.now()
            trigger_restart = False
            
            # --- LOGIK 1: Intervall-Prüfung (nutzt process_start_time) ---
            if interval_hours > 0 and proc_start_time_str:
                start_time = datetime.fromisoformat(proc_start_time_str)
                target_restart_time = start_time + timedelta(hours=interval_hours)
                if now >= target_restart_time:
                    print(f"{Fore.YELLOW}" + _("Auto-Restart (Intervall): Zeitlimit (%(hours)sh) erreicht.", hours=interval_hours))
                    trigger_restart = True
                    # WICHTIG: Setze die Prozess-Startzeit zurück, damit Intervall neu beginnt
                    session['process_start_time'] = now.isoformat()

            # --- LOGIK 2: Feste Uhrzeit-Prüfung ---
            if not trigger_restart and restart_time_str:
                current_time_str = now.strftime("%H:%M")
                last_trigger_str = session.get('last_daily_restart_trigger')
                last_trigger_date = None
                if last_trigger_str:
                    try:
                        last_trigger_date = datetime.fromisoformat(last_trigger_str).date()
                    except ValueError:
                        pass # Ignoriere ungültiges Datum

                if current_time_str == restart_time_str and now.date() != last_trigger_date:
                    print(f"{Fore.YELLOW}" + _("Auto-Restart (Uhrzeit): Fester Zeitpunkt (%(time)s) erreicht.", time=restart_time_str))
                    trigger_restart = True
                    session['last_daily_restart_trigger'] = now.isoformat()

            # --- Signal senden ---
            if trigger_restart:
                print(f"{Fore.YELLOW}" + _("Sende 'force_restart' Signal an Streamer..."))
                
                # Lade ALLE keys aus session.json, um nichts zu verlieren
                full_session_data = {}
                try:
                    with open('session.json', 'r', encoding='utf-8') as f_sess:
                        full_session_data = json.load(f_sess)
                except (FileNotFoundError, json.JSONDecodeError):
                    pass # wird überschrieben
                
                # Aktualisiere die Keys, die wir geändert haben
                full_session_data['force_restart'] = True
                if 'process_start_time' in session: # (falls Intervall ausgelöst hat)
                    full_session_data['process_start_time'] = session['process_start_time']
                if 'last_daily_restart_trigger' in session: # (falls Uhrzeit ausgelöst hat)
                    full_session_data['last_daily_restart_trigger'] = session['last_daily_restart_trigger']
                
                with open('session.json', 'w', encoding='utf-8') as f_sess:
                    json.dump(full_session_data, f_sess, indent=2)

        except Exception as e:
            print(f"{Fore.RED}" + _("Fehler im Auto-Restart-Thread: %(error)s", error=e))
            import traceback
            traceback.print_exc()
            time.sleep(300) # Bei schwerem Fehler länger warten


@app.route('/connect_twitch')
def connect_twitch():
    """Leitet den Benutzer zur Twitch-Autorisierungsseite weiter."""
    try:
        with open(CONFIG_JSON, 'r', encoding='utf-8') as f:
            config = json.load(f)
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            manager_config = json.load(f)

        client_id = config.get('twitch_api', {}).get('client_id')
        port = manager_config.get('port', 5000) # Port aus der manager_config lesen

        if not client_id:
            flash(_("Fehler: Zuerst muss eine Client-ID in der Streamer-Config gespeichert werden."), "error")
            return redirect(url_for('index', active_tab='settings'))
    except (FileNotFoundError, json.JSONDecodeError):
        flash(_("Fehler: Konnte Konfigurationsdateien nicht laden."), "error")
        return redirect(url_for('index', active_tab='settings'))

    # URL dynamisch zusammenbauen
    redirect_uri = f"https://127.0.0.1:{port}/twitch/callback"
    scopes = 'channel:manage:broadcast'

    auth_url = (f'https://id.twitch.tv/oauth2/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope={scopes}')
    return redirect(auth_url)

@app.route('/twitch/callback')
def twitch_callback():
    """Verarbeitet die Rückkehr von der Twitch-Autorisierung."""
    code = request.args.get('code')
    if not code:
        flash(_("Autorisierung fehlgeschlagen oder vom Benutzer abgelehnt."), "error")
        return redirect(url_for('index', active_tab='settings'))

    try:
        with open(CONFIG_JSON, 'r', encoding='utf-8') as f:
            config = json.load(f)
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            manager_config = json.load(f)

        client_id = config.get('twitch_api', {}).get('client_id')
        client_secret = config.get('twitch_api', {}).get('client_secret')
        port = manager_config.get('port', 5000)

        if not client_id or not client_secret:
            flash(_("Fehler: Client-ID und Client Secret müssen zuerst in der Config gespeichert werden."), "error")
            return redirect(url_for('index', active_tab='settings'))

    except (FileNotFoundError, json.JSONDecodeError):
        flash(_("Fehler: Konnte Konfigurationsdateien nicht laden."), "error")
        return redirect(url_for('index', active_tab='settings'))

    # URL dynamisch zusammenbauen
    redirect_uri = f"https://127.0.0.1:{port}/twitch/callback"

    # URL an die Funktion übergeben
    token_data = exchange_code_for_token(code, client_id, client_secret, redirect_uri)

    if token_data and 'access_token' in token_data:
        if save_tokens_to_config(token_data):
            flash(_("Erfolgreich mit Twitch verbunden! Die Tokens wurden gespeichert."), "success")
        else:
            flash(_("Fehler beim Speichern der Tokens."), "error")
    else:
        flash(_("Fehler: Konnte die Tokens nicht von Twitch erhalten. Überprüfe die Konsolenausgabe."), "error")

    return redirect(url_for('index', active_tab='settings'))



#Import Videos
@app.route('/sync_library', methods=['POST'])
def sync_library():
    """Scannt alle Video-Verzeichnisse und fügt neue Videos zur videos.json hinzu."""
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            manager_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        flash(_("Manager-Konfiguration nicht gefunden."), "error")
        return redirect(url_for('index', active_tab='library'))

    video_dirs = manager_config.get('video_directories', [])
    if not video_dirs:
        flash(_("Keine Video-Verzeichnisse in der Manager-Konfiguration festgelegt."), "warning")
        return redirect(url_for('index', active_tab='library'))

    videos_db = load_videos_db()
    # Erstelle ein Set von bereits bekannten Pfaden für eine schnelle Überprüfung
    known_paths = {info['path'] for info in videos_db.values()}
    
    new_videos_found = 0
    for video_dir in video_dirs:
        print(f"Scanne Verzeichnis: {video_dir}")
        for ext in VALID_EXTENSIONS:
            pattern = os.path.join(video_dir, '**', f'*{ext}')
            # Finde alle Videodateien im Verzeichnis und seinen Unterordnern
            for video_path in glob.glob(pattern, recursive=True):
                # Prüfe, ob wir dieses Video schon kennen
                if video_path not in known_paths:
                    new_id = f"vid_{uuid.uuid4().hex[:8]}"
                    videos_db[new_id] = {
                        "path": video_path,
                        "basename": os.path.basename(video_path)
                    }
                    known_paths.add(video_path)
                    new_videos_found += 1
                    print(f"Neues Video gefunden: {video_path}")

    if new_videos_found > 0:
        with open('videos.json', 'w', encoding='utf-8') as f:
            json.dump(videos_db, f, indent=4)
        flash(_("%(count)s neue(s) Video(s) wurde(n) zur Bibliothek hinzugefügt.", count=new_videos_found), "success")
    else:
        flash(_("Keine neuen Videos in den konfigurierten Verzeichnissen gefunden."), "info")

    return redirect(url_for('index', active_tab='library'))


# --- Helper Functions ---
def load_videos_db():
    """Lädt die videos.json Datenbank."""
    try:
        with open('videos.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def load_playlists_db():
    """Lädt die playlists.json Datenbank."""
    try:
        with open('playlists.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
        
def load_rotations_db():
    """Lädt die rotations.json Datenbank."""
    try:
        with open('rotations.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
        
def format_bytes(size_bytes):
    if size_bytes is None: return "N/A"
    power = 1024; n = 0
    power_labels = {0: 'Bytes', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size_bytes >= power and n < len(power_labels) - 1:
        size_bytes /= power; n += 1
    return f"{size_bytes:.2f} {power_labels[n]}"

def get_video_duration(video_path):
    command = [FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout)
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError):
        return 0.0

def get_metadata_with_cache(video_path, cache):
    try:
        last_modified = os.path.getmtime(video_path)
        if video_path in cache and cache[video_path].get('mtime') == last_modified:
            return cache[video_path]

        duration = get_video_duration(video_path)
        size_bytes = os.path.getsize(video_path)
        
        cache[video_path] = {
            'duration': duration, 'duration_str': time.strftime('%H:%M:%S', time.gmtime(duration)),
            'size_bytes': size_bytes, 'size_str': format_bytes(size_bytes), 'mtime': last_modified
        }
        return cache[video_path]
    except FileNotFoundError:
        return {'duration_str': "ERROR", 'size_str': "File not found", 'duration': 0}

def check_watch_folder():
    # Lade die Konfiguration, um die Ziel-Verzeichnisse zu finden
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            manager_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        manager_config = {}
    
    video_dirs = manager_config.get('video_directories', [])
    
    # Prüfen, ob überhaupt ein Ziel-Ordner konfiguriert ist
    if not video_dirs:
        flash(_("Fehler: Kein Video-Ordner in der Manager-Konfiguration festgelegt. Import nicht möglich."), "error")
        return False

    # Wir nehmen den ERSTEN Ordner aus der Liste als Ziel für neue Videos
    destination_dir = video_dirs[0]
    os.makedirs(destination_dir, exist_ok=True)
    os.makedirs(WATCH_DIR, exist_ok=True)
    
    moved_files = False
    for filename in os.listdir(WATCH_DIR):
        if filename.lower().endswith(VALID_EXTENSIONS):
            source_path = os.path.join(WATCH_DIR, filename)
            dest_path = os.path.join(destination_dir, filename) # Benutzt jetzt das korrekte Ziel
            if not os.path.exists(dest_path):
                shutil.move(source_path, dest_path)
                moved_files = True
                print(f"Video '{filename}' wurde nach '{destination_dir}' verschoben.")
    return moved_files

def get_videos_from_playlist(playlist_path, videos_db):
    """Liest eine Playlist-CSV und gibt eine Liste von Video-Objekten zurück."""
    videos = []
    try:
        with open(playlist_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                # Prüft, ob die Zeile nicht leer ist UND mindestens 3 Spalten enthält
                if row and len(row) >= 3:
                    video_id = row[0].strip()
                    if not video_id:  # Überspringe Zeilen ohne Video-ID
                        continue

                    video_info = videos_db.get(video_id)
                    if video_info:
                        videos.append({
                            'id': video_id,
                            'filename': video_info.get('path'),
                            'basename': video_info.get('basename'),
                            'title': row[1],
                            'game': row[2],
                            'status': row[3] if len(row) >= 4 else '1'
                        })
    except FileNotFoundError:
        pass
    return videos
    
@app.route('/create_playlist_from_selection', methods=['POST'])
def create_playlist_from_selection():
    """Erstellt eine neue Playlist aus ausgewählten Video-IDs."""
    video_ids_to_add = request.form.getlist('selected_videos')
    new_name_base = request.form.get('new_playlist_name')

    if not video_ids_to_add:
        flash(_("Keine Videos zum Erstellen der Playlist ausgewählt."), "warning")
        return redirect(url_for('index', active_tab='library'))
    if not new_name_base:
        flash(_("Bitte gib einen Namen für die neue Playlist an."), "error")
        return redirect(url_for('index', active_tab='library'))

    new_filename = "".join(c for c in new_name_base if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
    if not new_filename.lower().endswith('.csv'):
        new_filename += '.csv'
    new_playlist_path = os.path.join('playlists', new_filename)

    if os.path.exists(new_playlist_path):
        flash(_("Eine Playlist mit dem Namen '%(filename)s' existiert bereits.", filename=new_filename), "error")
        return redirect(url_for('index', active_tab='library'))

    videos_db = load_videos_db()

    try:
        with open(new_playlist_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            for video_id in video_ids_to_add:
                video_info = videos_db.get(video_id)
                if video_info:
                    title, _ext = os.path.splitext(video_info.get('basename', ''))
                    # KORREKTUR: Schreibe immer alle 4 Spalten
                    writer.writerow([video_id, title, 'Just Chatting', '1'])

        playlists_db = load_playlists_db()
        new_playlist_id = f"pl_{uuid.uuid4().hex[:8]}"
        playlists_db[new_playlist_id] = {
            "name": new_name_base,
            "filename": new_filename
        }
        with open('playlists.json', 'w', encoding='utf-8') as f:
            json.dump(playlists_db, f, indent=4)

        # Optional: Setze die neue Playlist als aktiv im Editor
        # This part seems to have been removed or changed, we can leave it out for now.

        flash(_("Playlist '%(filename)s' wurde mit %(count)s Videos erfolgreich erstellt!", filename=new_filename, count=len(video_ids_to_add)), "success")

    except Exception as e:
        flash(_("Fehler beim Erstellen der Playlist: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='playlist', edit_playlist=new_playlist_id))
 
@app.route('/add_to_playlist', methods=['POST'])
def add_to_playlist():
    """Fügt ausgewählte Video-IDs aus der Bibliothek zur Ziel-Playlist hinzu."""
    video_ids_to_add = request.form.getlist('selected_videos')
    target_playlist = request.form.get('playlist_select_target')

    if not video_ids_to_add:
        flash(_("Keine Videos zum Hinzufügen ausgewählt."), "warning")
        return redirect(url_for('index', active_tab='library'))
    if not target_playlist:
        flash(_("Keine Ziel-Playlist ausgewählt."), "error")
        return redirect(url_for('index', active_tab='library'))

    target_playlist_path = os.path.join('playlists', target_playlist)
    videos_db = load_videos_db()

    existing_video_ids = set()
    try:
        with open(target_playlist_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if row: existing_video_ids.add(row[0].strip())
    except FileNotFoundError:
        pass

    added_count = 0
    with open(target_playlist_path, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for video_id in video_ids_to_add:
            if video_id not in existing_video_ids:
                video_info = videos_db.get(video_id)
                if video_info:
                    title, _ext = os.path.splitext(video_info.get('basename', ''))
                    writer.writerow([video_id, title, 'Just Chatting', '1'])
                    added_count += 1

    if added_count > 0:
        flash(_("%(count)s Video(s) wurden zur Playlist '%(playlist)s' hinzugefügt.", count=added_count, playlist=target_playlist), "success")
    else:
        flash(_("Die ausgewählten Videos sind bereits in der Playlist vorhanden."), "info")

    return redirect(url_for('index', active_tab='library'))
    
    
@app.route('/skip_video', methods=['POST'])
def skip_video():
    """Signals the streamer to skip to the next video by forcing a restart."""
    try:
        session_data = {}
        with open('session.json', 'r', encoding='utf-8') as f: session_data = json.load(f)
        session_data['force_restart'] = True
        with open('session.json', 'w', encoding='utf-8') as f: json.dump(session_data, f, indent=2)
        flash(_("Signal 'Nächster Titel' gesendet."), "info")
    except Exception as e:
        flash(_("Fehler beim Senden des Signals: %(error)s", error=e), "error")
    return redirect(url_for('index', active_tab='playlist'))



@app.route('/restart_playlist', methods=['POST'])
def restart_playlist():
    """Signals the streamer to restart the current playlist from the beginning."""
    try:
        # Lade die Session-Daten
        session_data = {}
        with open('session.json', 'r', encoding='utf-8') as f: session_data = json.load(f)

        # Finde den Dateinamen der aktiven Playlist, um ihren Index zurückzusetzen
        active_playlist_id = session_data.get('active_playlist_id')
        if active_playlist_id:
            playlists_db = load_playlists_db()
            active_playlist_info = playlists_db.get(active_playlist_id)
            if active_playlist_info:
                filename = active_playlist_info['filename']
                # Setze den Index für DIESE Playlist auf 0 zurück
                if 'playlist_states' in session_data and filename in session_data['playlist_states']:
                    session_data['playlist_states'][filename]['resume_index'] = 0
                    print(f"Resume-Index für '{filename}' auf 0 zurückgesetzt.")

        # Sende das Signal für einen sofortigen Neustart
        session_data['force_restart'] = True
        with open('session.json', 'w', encoding='utf-8') as f: json.dump(session_data, f, indent=2)
        flash(_("Signal 'Playlist Neustart' gesendet."), "info")
    except Exception as e:
        flash(_("Fehler beim Senden des Signals: %(error)s", error=e), "error")
    return redirect(url_for('index', active_tab='playlist'))
    
    
    
@app.route('/rename_video', methods=['POST'])
def rename_video():
    """Benennt eine Videodatei, das zugehörige Thumbnail und den DB-Eintrag um."""
    video_id = request.form.get('video_id')
    new_basename_without_ext = request.form.get('new_name')

    if not video_id or not new_basename_without_ext:
        flash(_("Fehlende Informationen für die Umbenennung."), "error")
        return redirect(url_for('index', active_tab='library'))

    videos_db = load_videos_db()
    video_info = videos_db.get(video_id)

    if not video_info:
        flash(_("Video nicht in der Datenbank gefunden."), "error")
        return redirect(url_for('index', active_tab='library'))

    try:
        old_path = video_info['path']
        # Extrahiere den Ordnerpfad und die alte Dateiendung
        directory = os.path.dirname(old_path)
        _basename, extension = os.path.splitext(old_path)
        
        # Bereinige den neuen Namen und füge die alte Endung wieder an
        new_basename = "".join(c for c in new_basename_without_ext if c.isalnum() or c in (' ', '.', '_', '-')).rstrip() + extension
        new_path = os.path.join(directory, new_basename)

        if old_path == new_path:
            flash(_("Der neue Name ist identisch mit dem alten."), "info")
            return redirect(url_for('index', active_tab='library'))

        if os.path.exists(new_path):
            flash(_("Eine Datei mit dem Namen '%(filename)s' existiert bereits.", filename=new_basename), "error")
            return redirect(url_for('index', active_tab='library'))

        # 1. Videodatei umbenennen
        os.rename(old_path, new_path)

        # 2. Thumbnail umbenennen
        old_thumb_name = os.path.basename(old_path) + '.jpg'
        new_thumb_name = os.path.basename(new_path) + '.jpg'
        old_thumb_path = os.path.join(THUMBNAIL_DIR, old_thumb_name)
        new_thumb_path = os.path.join(THUMBNAIL_DIR, new_thumb_name)
        if os.path.exists(old_thumb_path):
            os.rename(old_thumb_path, new_thumb_path)

        # 3. Datenbank (videos.json) aktualisieren
        videos_db[video_id]['path'] = new_path
        videos_db[video_id]['basename'] = new_basename
        with open('videos.json', 'w', encoding='utf-8') as f:
            json.dump(videos_db, f, indent=4)

        flash(_("Video erfolgreich in '%(filename)s' umbenannt.", filename=new_basename), "success")

    except Exception as e:
        flash(_("Fehler beim Umbenennen: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='library'))


def is_bot_running():
    """Prüft, ob der Bot-Prozess läuft, basierend auf der PID-Datei."""
    try:
        with open('bot.pid', 'r') as f:
            pid = int(f.read().strip())
        return psutil.pid_exists(pid)
    except (FileNotFoundError, ValueError):
        return False


def is_streamer_running():
    """Prüft, ob der Streamer-Prozess läuft, basierend auf der PID-Datei."""
    try:
        with open('streamer.pid', 'r') as f:
            pid = int(f.read().strip())
        return psutil.pid_exists(pid)
    except (FileNotFoundError, ValueError):
        return False

@app.route('/start_streamer', methods=['POST'])
def start_streamer():
    """Startet das stream_v3.py Skript und trennt dessen Logs von den FFmpeg-Logs."""
    if is_streamer_running():
        flash(_("Der Streamer-Prozess läuft bereits!"), "warning")
        return redirect(url_for('index', active_tab='process'))

    print("Starte Streamer-Skript (stream_v3.py) mit getrennten Logs...")
    try:
        python_executable = sys.executable
        env = os.environ.copy()
        env['PYTHONUTF8'] = '1'

        creation_flags = 0
        if platform.system() == "Windows":
            creation_flags = subprocess.CREATE_NO_WINDOW

        # Öffne ZWEI getrennte Log-Dateien
        script_log_file = open('streamer.log', 'w', encoding='utf-8')
        ffmpeg_log_file = open('ffmpeg.log', 'w', encoding='utf-8')

        # Starte den Prozess und leite stdout und stderr getrennt um
        # stdout (print-Befehle aus Python) -> streamer.log
        # stderr (technische Ausgaben von FFmpeg) -> ffmpeg.log
        process = subprocess.Popen(
            [PYTHON_EXE, '-u', 'stream_v3.py'],
            creationflags=creation_flags,
            stdout=script_log_file,
            stderr=ffmpeg_log_file,
            env=env
        )
        
        with open('streamer.pid', 'w') as f:
            f.write(str(process.pid))
        
        script_log_file.close()
        ffmpeg_log_file.close()
        
        
        flash(_("Streamer-Skript wurde erfolgreich gestartet!"), "success")
        time.sleep(2)
    except Exception as e:
        flash(_("Fehler beim Starten des Streamer-Skripts: %(error)s", error=e), "error")
        
    return redirect(url_for('index', active_tab='process'))

@app.route('/get_ffmpeg_log_content')
def get_ffmpeg_log_content():
    """Liest die letzten 300 Zeilen der FFmpeg-Log-Datei."""
    log_content = _("Log-Datei (ffmpeg.log) nicht gefunden.")
    try:
        with open('ffmpeg.log', 'r', encoding='utf-8', errors='replace') as f:
            # Nutze deque, um effizient nur die letzten 300 Zeilen zu lesen
            last_lines = deque(f, maxlen=600)
            log_content = "".join(last_lines)
    except FileNotFoundError:
        pass 
    return jsonify({'log_content': log_content})

@app.route('/stop_streamer', methods=['POST'])
def stop_streamer():
    """Stoppt den laufenden Streamer-Prozess und seine Kinder plattformunabhängig."""
    pid_file = 'streamer.pid'
    status_file = 'status.json'

    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        flash(_("PID-Datei nicht gefunden. Der Streamer lief vermutlich bereits nicht mehr."), "warning")
        # Setze Status auf Offline, falls die Datei noch "Online" anzeigt
        with open(status_file, 'w', encoding='utf-8') as f: json.dump({"status": "Offline"}, f)
        return redirect(url_for('index'))

    try:
        parent = psutil.Process(pid)
        # Beende zuerst alle Kindprozesse (z.B. ffmpeg) und dann den Hauptprozess
        for child in parent.children(recursive=True):
            child.terminate()
        parent.terminate()
        # Warte, bis die Prozesse beendet sind (mit einem Timeout)
        gone, alive = psutil.wait_procs([parent], timeout=3)
        
        if not alive:
            flash(_("Streamer-Skript wurde erfolgreich gestoppt."), "success")
        else:
            # Falls terminate() nicht reicht, erzwinge den Stopp
            for p in alive: p.kill()
            flash(_("Streamer-Prozess reagierte nicht und wurde erzwungen beendet."), "warning")

    except psutil.NoSuchProcess:
        flash(_("Prozess nicht gefunden, war bereits beendet."), "info")
    except Exception as e:
        flash(_("Fehler beim Stoppen des Streamer-Skripts: %(error)s", error=e), "error")
    finally:
        if os.path.exists(pid_file): os.remove(pid_file)
        # Schreibe in jedem Fall den "Offline"-Status nach dem Stoppen
        with open(status_file, 'w', encoding='utf-8') as f: json.dump({"status": "Offline"}, f)
            
    return redirect(url_for('index', active_tab='process'))

from flask import session # Stelle sicher, dass 'session' am Anfang der Datei importiert wird

@app.route('/delete_files_from_library', methods=['POST'])
def delete_files_from_library():
    """Löscht ausgewählte Videodateien und deren Thumbnails permanent von der Festplatte."""
    files_to_delete = request.form.getlist('selected_videos')
    if not files_to_delete:
        flash(_("Keine Videos zum Löschen ausgewählt."), "warning")
        return redirect(url_for('index', active_tab='library'))

    # Wichtiger Sicherheitsschritt: Lade die erlaubten Verzeichnisse, um zu verhindern,
    # dass Dateien außerhalb dieser Ordner gelöscht werden können.
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            manager_config = json.load(f)
        allowed_dirs = [os.path.abspath(d) for d in manager_config.get('video_directories', [])]
    except (FileNotFoundError, json.JSONDecodeError):
        allowed_dirs = []

    if not allowed_dirs:
        flash(_("Fehler: Keine Video-Verzeichnisse konfiguriert. Löschen nicht möglich."), "error")
        return redirect(url_for('index', active_tab='library'))

    deleted_count = 0
    error_count = 0
    for file_path in files_to_delete:
        abs_file_path = os.path.abspath(file_path)
        
        # Prüfe, ob die zu löschende Datei in einem der erlaubten Ordner liegt
        is_safe_to_delete = any(abs_file_path.startswith(d) for d in allowed_dirs)

        if not is_safe_to_delete:
            print(f"SICHERHEITSWARNUNG: Versuch, Datei außerhalb der erlaubten Verzeichnisse zu löschen: {file_path}")
            error_count += 1
            continue

        try:
            # Lösche die Videodatei
            if os.path.exists(file_path):
                os.remove(file_path)
                
                # Lösche das zugehörige Thumbnail
                thumb_filename = os.path.basename(file_path) + '.jpg'
                thumb_path = os.path.join(THUMBNAIL_DIR, thumb_filename)
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                
                deleted_count += 1
        except Exception as e:
            print(f"Fehler beim Löschen von {file_path}: {e}")
            error_count += 1
    
    if deleted_count > 0:
        flash(_("%(count)s Video(s) wurden permanent gelöscht.", count=deleted_count), "success")
    if error_count > 0:
        flash(_("%(count)s Video(s) konnten nicht gelöscht werden. Siehe Log für Details.", count=error_count), "error")

    return redirect(url_for('index', active_tab='library'))


@app.route('/find_orphaned_videos', methods=['POST'])
def find_orphaned_videos():
    """Analysiert alle Playlists und findet Videos, die nirgends verwendet werden."""

    # 1. Alle Videodateien auf der Festplatte sammeln
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            manager_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        manager_config = {}

    video_dirs = manager_config.get('video_directories', ['videos'])
    disk_videos_set = set()
    for video_dir in video_dirs:
        for ext in VALID_EXTENSIONS:
            pattern = os.path.join(video_dir, '**', f'*{ext}')
            # Wichtig: Pfade normalisieren, um Vergleichsfehler zu vermeiden
            disk_videos_set.update(os.path.normpath(p) for p in glob.glob(pattern, recursive=True))

    # 2. Alle Videos aus allen Playlists sammeln
    playlist_files = glob.glob(os.path.join('playlists', '*.csv'))
    playlist_videos_set = set()
    for playlist_path in playlist_files:
        try:
            with open(playlist_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row: # Nur wenn die Zeile nicht leer ist
                        playlist_videos_set.add(os.path.normpath(row[0].strip()))
        except Exception as e:
            flash(_("Fehler beim Lesen der Playlist '%(playlist)s': %(error)s", playlist=os.path.basename(playlist_path), error=e), "warning")

    # 3. Die Differenz finden (Videos, die auf der Platte, aber in keiner Playlist sind)
    orphaned_videos = sorted(list(disk_videos_set - playlist_videos_set))

    # 4. Das Ergebnis in der Session speichern, um es nach der Weiterleitung anzuzeigen
    session['orphaned_videos_result'] = orphaned_videos

    flash(_("Analyse abgeschlossen. %(count)s ungenutzte Video(s) gefunden.", count=len(orphaned_videos)))
    return redirect(url_for('index', active_tab='library'))

# Ersetzen Sie die gesamte remove_from_playlist-Funktion mit dieser.
@app.route('/remove_from_playlist', methods=['POST'])
def remove_from_playlist():
    # Wir empfangen jetzt den Index des Eintrags
    entry_index_str = request.form.get('entry_index')
    editing_playlist_id = request.form.get('editing_playlist_id')

    if entry_index_str is None or not editing_playlist_id:
        flash(_("Fehlende Daten zum Entfernen des Eintrags."), "error")
        return redirect(url_for('index', active_tab='playlist'))

    try:
        entry_index = int(entry_index_str)
        playlists_db = load_playlists_db()
        playlist_info = playlists_db.get(editing_playlist_id)
        
        if not playlist_info:
            flash(_("Die zu bearbeitende Playlist wurde nicht gefunden."), "error")
            return redirect(url_for('index', active_tab='playlist'))

        playlist_path = os.path.join('playlists', playlist_info['filename'])
        
        # Lese alle Zeilen in eine Liste
        rows = []
        with open(playlist_path, 'r', encoding='utf-8', newline='') as f:
            rows = list(csv.reader(f))
        
        # Entferne den Eintrag am spezifischen Index, falls dieser gültig ist
        if 0 <= entry_index < len(rows):
            rows.pop(entry_index)
        
        # Schreibe die modifizierte Liste zurück in die Datei
        with open(playlist_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)

        flash(_("Video-Eintrag wurde aus der Playlist entfernt."), "success")

    except (ValueError, TypeError):
        flash(_("Ungültiger Index zum Entfernen des Eintrags."), "error")
    except Exception as e:
        flash(_("Fehler beim Entfernen des Eintrags: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='playlist', edit_playlist=editing_playlist_id))

# Ersetze die check_for_updates-Funktion

def check_for_updates():
    """Prüft auf eine neue Version und gibt IMMER die lokale Version zurück."""
    REMOTE_VERSION_URL = "https://hub.zeibig.me/version.json" 
    local_version = '0.0.0' # Fallback-Wert
    
    try:
        # Lese lokale Version
        with open('version.json', 'r', encoding='utf-8') as f:
            local_version = json.load(f).get('version', '0.0.0')

        # Standard-Rückgabewert, falls die Prüfung fehlschlägt
        update_info = {"update_available": False, "current_version": local_version}

        # Frage Remote-Version ab
        response = requests.get(REMOTE_VERSION_URL, timeout=5)
        response.raise_for_status()
        remote_version_data = response.json()
        remote_version = remote_version_data.get('version', '0.0.0')

        # Vergleiche die Versionen
        if remote_version > local_version:
            update_info = {
                "update_available": True,
                "current_version": local_version,
                "new_version": remote_version
            }
        
        return update_info

    except Exception as e:
        print(f"Fehler bei der Update-Prüfung: {e}")
        # Gib auch im Fehlerfall die lokale Version zurück
        return {"update_available": False, "current_version": local_version}


# In V_5-05-web_manager.py

@app.route('/save_rotation', methods=['POST'])
def save_rotation():
    """Speichert eine Rotation in rotations.json UND kompiliert sie zu einer Master-Playlist."""
    rotation_name = request.form.get('rotation_name')
    playlist_ids_json = request.form.get('playlist_ids')

    if not rotation_name or not playlist_ids_json:
        flash(_("Fehlende Daten zum Speichern der Rotation."), "error")
        return redirect(url_for('index', active_tab='rotations'))

    try:
        # --- Teil 1: Rotation in rotations.json speichern ---
        playlist_ids = json.loads(playlist_ids_json)
        rotations_db = load_rotations_db()
        new_rotation_id = f"rot_{uuid.uuid4().hex[:8]}"
        rotations_db[new_rotation_id] = {
            "name": rotation_name,
            "playlist_ids": playlist_ids
        }
        with open('rotations.json', 'w', encoding='utf-8') as f:
            json.dump(rotations_db, f, indent=4)

        # --- Teil 2: Rotation zu einer Master-Playlist kompilieren (KORRIGIERT) ---
        playlists_db = load_playlists_db()
        # videos_db wird nicht mehr für Metadaten benötigt

        master_video_rows = [] # Speichert die kompletten Zeilen
        for playlist_id in playlist_ids:
            playlist_info = playlists_db.get(playlist_id)
            if playlist_info:
                playlist_path = os.path.join('playlists', playlist_info['filename'])
                with open(playlist_path, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        # Füge die komplette Zeile (ID, Titel, Spiel, Status) hinzu
                        if row: 
                            master_video_rows.append(row)

        MASTER_PLAYLIST_NAME = f"_rotation_{rotation_name}".replace(' ', '_')
        MASTER_PLAYLIST_FILENAME = MASTER_PLAYLIST_NAME + ".csv"
        master_playlist_path = os.path.join('playlists', MASTER_PLAYLIST_FILENAME)

        with open(master_playlist_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            # Schreibe die gesammelten, vollständigen Zeilen
            writer.writerows(master_video_rows)

        master_playlist_id = None
        for pl_id, pl_info in playlists_db.items():
            if pl_info['filename'] == MASTER_PLAYLIST_FILENAME:
                master_playlist_id = pl_id
                pl_info['name'] = MASTER_PLAYLIST_NAME # Update Name, falls schon vorhanden
                break

        if not master_playlist_id:
            master_playlist_id = f"pl_{uuid.uuid4().hex[:8]}"
            playlists_db[master_playlist_id] = { "name": MASTER_PLAYLIST_NAME, "filename": MASTER_PLAYLIST_FILENAME }

        with open('playlists.json', 'w', encoding='utf-8') as f:
            json.dump(playlists_db, f, indent=4)

        flash(_("Rotation '%(rotation_name)s' gespeichert und als Playlist kompiliert.", rotation_name=rotation_name), "success")

    except Exception as e:
        flash(_("Ein unerwarteter Fehler ist aufgetreten: %(error)s", error=e), "error")
        return redirect(url_for('index', active_tab='rotations'))

    # Leite den Benutzer direkt zur neuen Playlist im Editor weiter
    return redirect(url_for('index', active_tab='playlist', edit_playlist=master_playlist_id))

@app.route('/delete_rotation', methods=['POST'])
def delete_rotation():
    """Löscht eine gespeicherte Rotation aus der rotations.json."""
    rotation_id_to_delete = request.form.get('rotation_id')
    
    if not rotation_id_to_delete:
        flash(_("Keine Rotation zum Löschen ausgewählt."), "error")
        return redirect(url_for('index', active_tab='rotations'))

    try:
        rotations_db = load_rotations_db()
        if rotation_id_to_delete in rotations_db:
            deleted_name = rotations_db.pop(rotation_id_to_delete)['name']
            with open('rotations.json', 'w', encoding='utf-8') as f:
                json.dump(rotations_db, f, indent=4)
            flash(_("Rotation '%(rotation_name)s' wurde gelöscht.", rotation_name=deleted_name), "success")
        else:
            flash(_("Zu löschende Rotation nicht gefunden."), "warning")
    except Exception as e:
        flash(_("Fehler beim Löschen der Rotation: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='rotations'))

@app.route('/duplicate_entry', methods=['POST'])
def duplicate_entry():
    editing_playlist_id = request.form.get('editing_playlist_id')
    entry_index_str = request.form.get('entry_index')

    # KORREKTUR: Wir prüfen explizit auf 'None', damit der Index 0 als gültig erkannt wird.
    if not editing_playlist_id or entry_index_str is None:
        flash(_("Fehlende Informationen zum Duplizieren."), "error")
        return redirect(url_for('index', active_tab='playlist'))

    try:
        entry_index = int(entry_index_str)
        playlists_db = load_playlists_db()
        playlist_info = playlists_db.get(editing_playlist_id)
        if not playlist_info:
            flash(_("Playlist nicht gefunden."), "error")
            return redirect(url_for('index', active_tab='playlist'))

        playlist_path = os.path.join('playlists', playlist_info['filename'])
        
        rows = []
        with open(playlist_path, 'r', encoding='utf-8', newline='') as f:
            rows = list(csv.reader(f))
        
        if 0 <= entry_index < len(rows):
            row_to_duplicate = rows[entry_index]
            rows.insert(entry_index + 1, row_to_duplicate)
        
        with open(playlist_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)

        flash(_("Eintrag erfolgreich dupliziert."), "success")

    except Exception as e:
        flash(_("Fehler beim Duplizieren des Eintrags: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='playlist', edit_playlist=editing_playlist_id))


# --- Routes ---

@app.route('/')
def index():
    update_info = check_for_updates()
    active_tab = request.args.get('active_tab', 'playlist')
    orphaned_videos_result = session.pop('orphaned_videos_result', None)

    # --- DATENBANKEN & KONFIGURATIONEN LADEN ---
    videos_db = load_videos_db()
    playlists_db = load_playlists_db()
    rotations_db = load_rotations_db()
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f: manager_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): manager_config = {}
    try:
        with open(CONFIG_JSON, 'r', encoding='utf-8') as f: streamer_config = json.load(f)
        client_secret_exists = bool(streamer_config.get('twitch_api', {}).get('client_secret'))
    except (FileNotFoundError, json.JSONDecodeError): streamer_config = {}
    if 'twitch_api' not in streamer_config: streamer_config['twitch_api'] = {}
    if 'stream_settings' not in streamer_config: streamer_config['stream_settings'] = {}
    if 'ffmpeg' not in streamer_config: streamer_config['ffmpeg'] = {}
    if 'twitch_bot' not in streamer_config: streamer_config['twitch_bot'] = {}
    try:
        with open('schedule.json', 'r', encoding='utf-8') as f: schedule_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): schedule_data = {}
    try:
        with open('config_presets.json', 'r', encoding='utf-8') as f: config_presets = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): config_presets = {}
    bot_commands = {}
    try:
        with open('commands.json', 'r', encoding='utf-8') as f: bot_commands = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): pass

    # --- NEUE LOGIK FÜR PLAYLIST-AUSWAHL ---
    # 1. Priorität: Eine explizit in der URL angeforderte Playlist (?edit_playlist=...)
    playlist_to_edit_id = request.args.get('edit_playlist')
    
    # 2. Priorität: Die zuletzt bearbeitete Playlist aus der Konfiguration laden
    if not playlist_to_edit_id:
        playlist_to_edit_id = manager_config.get('last_edited_playlist_id')

    # 3. Priorität (Fallback): Die aktuell für den Stream aktive Playlist
    if not playlist_to_edit_id:
        playlist_to_edit_id = manager_config.get('active_playlist_id')

    # Fallback, wenn gar nichts ausgewählt/gültig ist oder keine Playlists existieren
    if not playlists_db:
        active_playlist_id, playlist_to_edit_id = None, None
        active_playlist_info, playlist_to_edit_info = None, None
    elif playlist_to_edit_id not in playlists_db:
        # Wenn eine ungültige ID ermittelt wurde, nimm die erste verfügbare Playlist
        playlist_to_edit_id = list(playlists_db.keys())[0]

    # --- SPEICHERN DER AUSWAHL ---
    # Wenn sich die zur Bearbeitung ausgewählte Playlist geändert hat, speichere sie für den nächsten Aufruf.
    if playlist_to_edit_id and manager_config.get('last_edited_playlist_id') != playlist_to_edit_id:
        manager_config['last_edited_playlist_id'] = playlist_to_edit_id
        try:
            with open(MANAGER_CONFIG_JSON, 'w', encoding='utf-8') as f:
                json.dump(manager_config, f, indent=4)
        except Exception as e:
            print(f"Fehler beim Speichern der letzten Playlist-ID: {e}")

    active_playlist_id = manager_config.get('active_playlist_id')
    active_playlist_info = playlists_db.get(active_playlist_id)
    playlist_to_edit_info = playlists_db.get(playlist_to_edit_id)
    
    playlist_videos = []
    if playlist_to_edit_info:
        playlist_path = os.path.join('playlists', playlist_to_edit_info['filename'])
        playlist_videos = get_videos_from_playlist(playlist_path, videos_db)

    manager_config['active_playlist_id'] = active_playlist_id
    manager_config['editing_playlist_id'] = playlist_to_edit_id
    
    # --- LOGIK FÜR ROTATIONS-EDITOR ---
    rotation_to_edit = []
    rotation_name_to_edit = ""
    load_rotation_id = request.args.get('load_rotation')
    if load_rotation_id and load_rotation_id in rotations_db:
        rotation_data = rotations_db[load_rotation_id]
        rotation_name_to_edit = rotation_data.get('name', '')
        for pl_id in rotation_data.get('playlist_ids', []):
            pl_info = playlists_db.get(pl_id)
            if pl_info:
                rotation_to_edit.append({'id': pl_id, 'name': pl_info.get('name')})

    # --- DATEN ANREICHERN & VORBEREITEN ---
    all_disk_videos = []
    for video_id, video_info in videos_db.items():
        details = {'id': video_id}; details.update(video_info); all_disk_videos.append(details)

    metadata_cache = {}
    try:
        with open(METADATA_CACHE_JSON, 'r', encoding='utf-8') as f: metadata_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): pass
    
    for video_list in [playlist_videos, all_disk_videos]:
        for video in video_list:
            video_path = video.get('path') or video.get('filename')
            if video_path and os.path.exists(video_path):
                metadata = get_metadata_with_cache(video_path, metadata_cache)
                video.update(metadata)
    
    with open(METADATA_CACHE_JSON, 'w', encoding='utf-8') as f: json.dump(metadata_cache, f, indent=2)

    video_playlist_map = {}
    for pl_id, pl_info in playlists_db.items():
        pl_path = os.path.join('playlists', pl_info['filename'])
        try:
            with open(pl_path, 'r', encoding='utf-8') as f:
                for row in csv.reader(f):
                    if row: video_playlist_map.setdefault(row[0].strip(), []).append(pl_info['filename'])
        except Exception: pass

    total_duration = sum(v.get('duration', 0) for v in playlist_videos if v.get('status', '1') == '1')
    duration_formatted = time.strftime('%H:%M:%S', time.gmtime(total_duration))

    os.makedirs(FONTS_DIR, exist_ok=True)
    available_fonts = [f for f in os.listdir(FONTS_DIR) if f.lower().endswith(VALID_FONT_EXTENSIONS)]
    
    # --- SEITE RENDERN ---
    return render_template('index.html',
                           videos=playlist_videos, all_disk_videos=all_disk_videos,
                           manager_config=manager_config, streamer_config=streamer_config,
                           total_duration=duration_formatted, fonts=available_fonts,
                           active_tab=active_tab, streamer_is_running=is_streamer_running(),
                           bot_is_running=is_bot_running(), orphaned_videos_result=orphaned_videos_result,
                           video_playlist_map=video_playlist_map, playlists_db=playlists_db,
                           active_playlist_info=active_playlist_info, rotations_db=rotations_db,
                           rotation_to_edit=rotation_to_edit, rotation_name_to_edit=rotation_name_to_edit,
                           bot_commands=bot_commands, schedule=schedule_data,update_info=update_info,
                           config_presets=config_presets,client_secret_exists=client_secret_exists)
    
@app.route('/status')
def get_status():
    raw_data = {"status": "Unknown", "bot_status": "Unknown"}
    try:
        with open(STATUS_JSON, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw_data = {"status": "Offline"}

    bot_status_raw = "Online" if is_bot_running() else "Offline"
    raw_data['bot_status'] = bot_status_raw
    
    # Erstelle das übersetzte JSON, das an den Browser gesendet wird
    translated_data = {
        # Füge die rohen, englischen Werte für die JS-Logik hinzu
        "status_raw": raw_data.get('status'),
        "bot_status_raw": raw_data.get('bot_status'),

        # Übersetze die Werte für die Anzeige
        "status": _(raw_data.get('status')),
        "bot_status": _(raw_data.get('bot_status')),
        
        # Behalte alle anderen Daten (now_playing, etc.) bei
        "now_playing": raw_data.get('now_playing'),
        "title": raw_data.get('title'),
        "game": raw_data.get('game'),
        "video_duration": raw_data.get('video_duration'),
        "video_elapsed": raw_data.get('video_elapsed')
    }

    return jsonify(translated_data)
    
@app.route('/get_log_content')
def get_log_content():
    """Liest den Inhalt der streamer.log-Datei und gibt ihn als JSON zurück."""
    log_content = _("Log-Datei (streamer.log) nicht gefunden.")
    try:
        with open('streamer.log', 'r', encoding='utf-8', errors='replace') as f:
            # Read only the last few lines to avoid performance issues with large logs
            last_lines = deque(f, maxlen=300)
            log_content = "".join(last_lines)
    except FileNotFoundError:
        pass 
    return jsonify({'log_content': log_content})

@app.route('/start_bot', methods=['POST'])
def start_bot():
    if is_bot_running():
        flash(_("Der Bot-Prozess läuft bereits!"), "warning")
        return redirect(url_for('index', active_tab='bot'))

    print(_("Starte Bot-Skript (twitch_bot.py)..."))
    try:
        python_executable = sys.executable
        env = os.environ.copy()
        
        creation_flags = 0
        if platform.system() == "Windows":
            creation_flags = subprocess.CREATE_NO_WINDOW

        # -u sorgt für ungepufferte Ausgabe, wichtig für Live-Logs
        bot_log_file = open('bot.log', 'w', encoding='utf-8')
        process = subprocess.Popen(
            [PYTHON_EXE, '-X', 'utf8', '-u', 'twitch_bot.py'],
            creationflags=creation_flags,
            stdout=bot_log_file,
            stderr=bot_log_file,
            env=env
        )
        
        with open('bot.pid', 'w') as f:
            f.write(str(process.pid))
            
        flash(_("Bot-Skript wurde erfolgreich gestartet!"), "success")
        time.sleep(2)
    except Exception as e:
        flash(_("Fehler beim Starten des Bot-Skripts: %(error)s", error=e), "error")
        
    return redirect(url_for('index', active_tab='bot'))

@app.route('/get_chat_log_content')
def get_chat_log_content():
    log_content = _("Chat-Log (chat.log) nicht gefunden.")
    try:
        with open('chat.log', 'r', encoding='utf-8', errors='replace') as f:
            last_lines = deque(f, maxlen=100) # Wir zeigen die letzten 100 Zeilen an
            log_content = "".join(last_lines)
    except FileNotFoundError:
        pass 
    return jsonify({'log_content': log_content})

@app.route('/stop_bot', methods=['POST'])
def stop_bot():
    pid_file = 'bot.pid'
    if not is_bot_running():
        flash(_("Der Bot-Prozess lief bereits nicht mehr."), "warning")
        if os.path.exists(pid_file): os.remove(pid_file)
        return redirect(url_for('index', active_tab='bot'))

    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
        parent = psutil.Process(pid)
        parent.terminate()
        parent.wait(timeout=3)
        flash(_("Bot-Skript wurde erfolgreich gestoppt."), "success")
    except psutil.NoSuchProcess:
        flash(_("Prozess nicht gefunden, war bereits beendet."), "info")
    except Exception as e:
        flash(_("Fehler beim Stoppen des Bot-Skripts: %(error)s", error=e), "error")
    finally:
        if os.path.exists(pid_file): os.remove(pid_file)
            
    return redirect(url_for('index', active_tab='bot'))

@app.route('/get_bot_log_content')
def get_bot_log_content():
    log_content = _("Log-Datei (bot.log) nicht gefunden.")
    try:
        with open('bot.log', 'r', encoding='utf-8', errors='replace') as f:
            last_lines = deque(f, maxlen=300)
            log_content = "".join(last_lines)
    except FileNotFoundError:
        pass 
    return jsonify({'log_content': log_content})

@app.route('/thumbnail/<video_id>')
def get_thumbnail(video_id):
    # Diese Route erwartet eine Video-ID und sucht nach 'vid_... .jpg'
    # Dies ist die robusteste Methode, da IDs immer eindeutig sind.
    thumbnail_filename = f"{video_id}.jpg"
    return send_from_directory(THUMBNAIL_DIR, thumbnail_filename, as_attachment=False)

@app.route('/import_new_videos', methods=['POST'])
def import_new_videos():
    if check_watch_folder():
        flash(_("Neue Videos wurden erfolgreich importiert!"), "success")
    else:
        flash(_("Keine neuen Videos im '_neu_'-Ordner gefunden."), "info")
    return redirect(url_for('index', active_tab='playlist'))

@app.route('/generate_thumbnails', methods=['POST'])
def generate_thumbnails():
    videos_db = load_videos_db()
    manager_config = {}
    # 1. Lade die Konfiguration, um die Video-Ordner und die Skalierung zu finden
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            manager_config = json.load(f)
        scale = manager_config.get('thumbnail_scale', '320:-1')
    except (FileNotFoundError, json.JSONDecodeError):
        scale = '320:-1'  # Fallback
    
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)

    # 2. Finde ALLE Videos in ALLEN konfigurierten Ordnern (inkl. Unterordnern)
    video_dirs = manager_config.get('video_directories', ['videos'])
    all_video_paths = []
    for video_dir in video_dirs:
        try:
            os.makedirs(video_dir, exist_ok=True)
            for ext in VALID_EXTENSIONS:
                pattern = os.path.join(video_dir, '**', f'*{ext}')
                all_video_paths.extend(glob.glob(pattern, recursive=True))
        except OSError as e:
            flash(_("Warnung: Video-Verzeichnis '%(dir)s' konnte nicht gelesen werden: %(error)s", dir=video_dir, error=e), "warning")
            continue

    # 3. Iteriere durch die gefundene Liste und generiere Thumbnails
    generated_count = 0
    for video_path in all_video_paths:
        # Der Dateiname des Thumbnails basiert auf dem Dateinamen des Videos
        # Finde die ID des Videos anhand seines Pfades
        video_id = next((vid for vid, info in videos_db.items() if info.get('path') == video_path), None)
        if not video_id:
            continue # Überspringe, wenn das Video nicht in der DB ist
        thumb_filename = f"{video_id}.jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, thumb_filename)
        
        if not os.path.exists(thumb_path):
            try:
                # Der FFmpeg-Befehl ist korrekt
                command = [FFMPEG_EXE, '-i', video_path, '-ss', '00:00:05', '-vframes', '1', '-vf', f'scale={scale}', thumb_path]
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                generated_count += 1
            except Exception as e:
                print(f"Konnte Thumbnail für {video_path} nicht erstellen: {e}")
                
    flash(_("%(count)s neue(s) Thumbnail(s) wurde(n) mit der Skalierung %(scale)s erstellt!", count=generated_count, scale=scale), "success")
    return redirect(url_for('index', active_tab='playlist'))

@app.route('/shuffle', methods=['POST'])
def shuffle_playlist():
    """Shuffles the active playlist randomly, now using video IDs."""
    try:
        # Finde die aktive Playlist
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            config = json.load(f)
        active_playlist_path = os.path.join('playlists', config.get('active_playlist', 'default.csv'))
        
        # Lade die Video-Datenbank, um die Videos zu lesen
        videos_db = load_videos_db()
        videos = get_videos_from_playlist(active_playlist_path, videos_db)
        random.shuffle(videos)
        
        # Schreibe die gemischte Playlist zurück
        with open(active_playlist_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            for v in videos:
                # Stelle sicher, dass das Status-Feld existiert und schreibe die ID zurück
                status = v.get('status', '1')
                writer.writerow([v['id'], v['title'], v['game'], status])
        flash(_("Playlist wurde erfolgreich gemischt!"), "success")
    except Exception as e:
        flash(_("Fehler beim Mischen der Playlist: %(error)s", error=e), "error")
    return redirect(url_for('index', active_tab='playlist'))

@app.route('/bulk_enable', methods=['POST'])
def bulk_enable():
    """Aktiviert alle Videos in der aktiven Playlist."""
    try:
        # Finde die aktive Playlist
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            config = json.load(f)
        active_playlist_path = os.path.join('playlists', config.get('active_playlist', 'default.csv'))

        # Lese alle Zeilen und setze den Status auf 1
        playlist_data = []
        with open(active_playlist_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    while len(row) < 4: row.append('')
                    row[3] = '1'
                    playlist_data.append(row)
        
        # Schreibe die Daten zurück
        with open(active_playlist_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(playlist_data)
        flash(_("Alle Videos wurden aktiviert!"), "success")
    except Exception as e:
        flash(_("Fehler beim Aktivieren aller Videos: %(error)s", error=e), "error")
    return redirect(url_for('index', active_tab='playlist'))

@app.route('/bulk_disable', methods=['POST'])
def bulk_disable():
    """Deaktiviert alle Videos in der aktiven Playlist."""
    try:
        # Finde die aktive Playlist
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            config = json.load(f)
        active_playlist_path = os.path.join('playlists', config.get('active_playlist', 'default.csv'))

        # Lese alle Zeilen und setze den Status auf 0
        playlist_data = []
        with open(active_playlist_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    while len(row) < 4: row.append('')
                    row[3] = '0'
                    playlist_data.append(row)
        
        # Schreibe die Daten zurück
        with open(active_playlist_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(playlist_data)
        flash(_("Alle Videos wurden deaktiviert!"), "success")
    except Exception as e:
        flash(_("Fehler beim Deaktivieren aller Videos: %(error)s", error=e), "error")
    return redirect(url_for('index', active_tab='playlist'))


@app.route('/save_and_restart_deferred', methods=['POST'])
def save_and_restart_deferred():
    """Speichert die Playlist und signalisiert einen verzögerten Neustart mit der korrekten ID."""
    save_metadata() # Ruft die bereits korrigierte Speicherfunktion auf
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f: config = json.load(f)
        session_data = {}
        try:
            with open('session.json', 'r', encoding='utf-8') as f: session_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): pass
        
        session_data['active_playlist_id'] = config.get('active_playlist_id') # ID HINZUGEFÜGT
        session_data['restart_pending'] = True
        
        with open('session.json', 'w', encoding='utf-8') as f: json.dump(session_data, f, indent=2)
        flash(_('Playlist gespeichert! Der Stream wird nach dem aktuellen Video neu gestartet.'), "info")
    except Exception as e:
        flash(_('Fehler beim Speichern: %(error)s', error=e), "error")
    return redirect(url_for('index', active_tab='playlist'))


@app.route('/save_playlist_as', methods=['POST'])
def save_playlist_as():
    new_name = request.form.get('new_playlist_name')
    if not new_name:
        flash(_("Bitte gib einen Namen für die neue Playlist an."), "error")
        return redirect(url_for('index', active_tab='playlist'))
    if not new_name.lower().endswith('.csv'): new_name += '.csv'
    new_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
    new_playlist_path = os.path.join('playlists', new_name)
    if os.path.exists(new_playlist_path):
        flash(_("Eine Playlist mit dem Namen '%(name)s' existiert bereits.", name=new_name), "error")
        return redirect(url_for('index', active_tab='playlist'))
    filenames = request.form.getlist('filename')
    titles = request.form.getlist('title')
    games = request.form.getlist('game')
    try:
        with open(new_playlist_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            for i in range(len(filenames)):
                status = '1' if f'status_{i}' in request.form else '0'
                writer.writerow([filenames[i], titles[i], games[i], status])
        flash(_("Playlist erfolgreich als '%(name)s' gespeichert!", name=new_name), "success")
    except Exception as e:
        flash(_("Fehler beim Speichern der neuen Playlist: %(error)s", error=e), "error")
    return redirect(url_for('index', active_tab='playlist'))

@app.route('/switch_playlist', methods=['POST'])
def switch_playlist():
    """Switches the active playlist and signals the streamer with the selected restart mode."""
    selected_filename = request.form.get('playlist_to_activate')
    restart_mode = request.form.get('restart_mode') # 'soft' or 'hard'
    
    playlists_db = load_playlists_db()
    target_playlist_id = None
    for pl_id, pl_info in playlists_db.items():
        if pl_info['filename'] == selected_filename:
            target_playlist_id = pl_id
            break
    
    if not target_playlist_id:
        flash(_("Fehler: Playlist '%(filename)s' konnte nicht gefunden werden.", filename=selected_filename), "error")
        return redirect(url_for('index', active_tab='playlist'))

    try:
        # 1. Manager-Konfiguration für die UI aktualisieren
        with open(MANAGER_CONFIG_JSON, 'r+') as f:
            config = json.load(f)
            config['active_playlist_id'] = target_playlist_id
            f.seek(0)
            json.dump(config, f, indent=2)
            f.truncate()

        # 2. Befehl an den Streamer senden via session.json
        session_data = {}
        try:
            with open('session.json', 'r', encoding='utf-8') as f:
                session_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        session_data['active_playlist_id'] = target_playlist_id
        if restart_mode == 'soft':
            session_data['restart_pending'] = True
            flash_message = _("'%s' wird nach dem aktuellen Video aktiviert.") % selected_filename
        elif restart_mode == 'hard':
            session_data['force_restart'] = True
            flash_message = _("'%s' wird jetzt aktiviert. Stream startet neu.") % selected_filename
        else: # Fallback, falls kein Modus übergeben wird
            session_data['force_restart'] = True
            flash_message = _("'%s' aktiviert.") % selected_filename

        with open('session.json', 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)

        flash(flash_message, "success")
    except Exception as e:
        flash(_("Fehler beim Aktivieren der Playlist: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='playlist'))

@app.route('/delete_playlist', methods=['POST'])
def delete_playlist():
    """Löscht eine Playlist-Datei UND den zugehörigen Eintrag in playlists.json."""
    playlist_to_delete_filename = request.form.get('playlist_to_delete')

    # Finde die ID der zu löschenden Playlist
    playlists_db = load_playlists_db()
    target_playlist_id = None
    for pl_id, pl_info in playlists_db.items():
        if pl_info['filename'] == playlist_to_delete_filename:
            target_playlist_id = pl_id
            break
            
    # Sicherheitsprüfung: Lösche nicht die aktive Playlist
    config = {}
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f: config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): pass

    if config.get('active_playlist_id') == target_playlist_id:
        flash(_("Fehler: Die aktive Playlist '%(filename)s' kann nicht gelöscht werden.", filename=playlist_to_delete_filename), "error")
        return redirect(url_for('index', active_tab='playlist'))

    # Löschvorgang
    try:
        playlist_path = os.path.join('playlists', playlist_to_delete_filename)
        if os.path.exists(playlist_path):
            os.remove(playlist_path) # Lösche .csv Datei
        
        if target_playlist_id in playlists_db:
            playlists_db.pop(target_playlist_id) # Entferne Eintrag aus der DB
            with open('playlists.json', 'w', encoding='utf-8') as f:
                json.dump(playlists_db, f, indent=4) # Speichere die aktualisierte DB
            
        flash(_("Playlist '%(filename)s' wurde erfolgreich gelöscht.", filename=playlist_to_delete_filename), "success")
    except Exception as e:
        flash(_("Fehler beim Löschen der Playlist: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='playlist'))


# NEUE, ROBUSTERE VERSION
@app.route('/save_metadata', methods=['POST'])
def save_metadata():
    """Speichert Metadaten für die aktuell bearbeitete Playlist via JSON."""
    try:
        # 1. Empfange die JSON-Daten vom Frontend
        data = request.get_json()
        editing_playlist_id = data.get('editing_playlist_id')
        playlist_data = data.get('playlist_data', [])

        if not editing_playlist_id:
            return jsonify(success=False, error=_("Keine zu bearbeitende Playlist-ID übermittelt.")), 400

        playlists_db = load_playlists_db()
        playlist_to_save_info = playlists_db.get(editing_playlist_id)
        if not playlist_to_save_info:
            return jsonify(success=False, error=_("Playlist mit ID '%(id)s' nicht gefunden.", id=editing_playlist_id)), 404

        playlist_path = os.path.join('playlists', playlist_to_save_info['filename'])

        # 2. Bereite die neuen Zeilen für die CSV-Datei vor
        updated_rows = []
        for item in playlist_data:
            video_id = item.get('id')
            title = item.get('title')
            game = item.get('game')
            # Konvertiere den Boolean-Wert (true/false) in '1' oder '0'
            status = '1' if item.get('active', False) else '0'
            updated_rows.append([video_id, title, game, status])

        # 3. Schreibe die CSV-Datei komplett neu
        with open(playlist_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(updated_rows)
        
        flash(_("Änderungen in Playlist '%(name)s' erfolgreich gespeichert!", name=playlist_to_save_info['name']), "success")
        return jsonify(success=True)

    except Exception as e:
        # Gib eine generische, übersetzbare Fehlermeldung zurück anstatt des technischen Fehlers
        return jsonify(success=False, error=_("Ein unerwarteter Fehler ist aufgetreten.")), 500

@app.route('/save_playlist_and_restart', methods=['POST'])
def save_playlist_and_restart():
    """Speichert die Playlist und signalisiert einen sofortigen Neustart mit der korrekten ID."""
    save_metadata() # Ruft die bereits korrigierte Speicherfunktion auf
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f: config = json.load(f)
        session_data = {}
        try:
            with open('session.json', 'r', encoding='utf-8') as f: session_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): pass
        
        session_data['active_playlist_id'] = config.get('active_playlist_id') # ID HINZUGEFÜGT
        session_data['force_restart'] = True
        
        with open('session.json', 'w', encoding='utf-8') as f: json.dump(session_data, f, indent=2)
        flash(_('Playlist gespeichert! Neustart-Signal wurde gesendet.'), "info")
    except Exception as e:
        flash(_('Fehler beim Speichern der Playlist: %(error)s', error=e), "error")
    return redirect(url_for('index', active_tab='process'))

@app.route('/save_manager_config', methods=['POST'])
def save_manager_config():
    """Saves the global manager configuration."""
    config = {}
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    # Lese die Pfade aus der Textarea und konvertiere sie in eine saubere Liste
    video_dirs_text = request.form.get('video_directories', '')
    video_dirs_list = [line.strip() for line in video_dirs_text.splitlines() if line.strip()]

    config.update({
        'title_prefix': request.form.get('title_prefix'),
        'overlay_prefix': request.form.get('overlay_prefix'),
        'language': request.form.get('language'),
        'thumbnail_scale': request.form.get('thumbnail_scale'),
        'video_directories': video_dirs_list # NEU: Speichere als Liste
    })
    
    try:
        with open(MANAGER_CONFIG_JSON, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        flash(_('Manager-Konfiguration erfolgreich gespeichert!'), "success")
    except Exception as e:
        flash(_('Fehler beim Speichern der Manager-Konfiguration: %(error)s', error=e), "error")
    return redirect(url_for('index', active_tab='manager_config'))

@app.route('/save_schedule', methods=['POST'])
def save_schedule():
    """Saves the weekly schedule from the form to schedule.json."""
    try:
        # Lade die bestehende Konfiguration, um den Default-Wert zu erhalten
        try:
            with open('schedule.json', 'r', encoding='utf-8') as f:
                schedule_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            schedule_data = {}

        new_schedule = {'default_playlist': schedule_data.get('default_playlist', '')}
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

        for day in days:
            new_schedule[day] = []
            for i in range(3): # Wir haben 3 Event-Slots pro Tag
                playlist_id = request.form.get(f'{day}_playlist_{i}')
                start_time = request.form.get(f'{day}_start_time_{i}')
                
                # Nur wenn eine Playlist und eine Startzeit ausgewählt wurden
                if playlist_id and start_time:
                    mode = request.form.get(f'{day}_mode_{i}')
                    event = {
                        "playlist": playlist_id,
                        "start_time": start_time,
                        "mode": mode
                    }
                    if mode == 'time':
                        event['end_time'] = request.form.get(f'{day}_end_time_{i}')
                    elif mode == 'repeat':
                        # Stelle sicher, dass der Wert eine Zahl ist
                        try:
                            repeat_val = int(request.form.get(f'{day}_repeat_{i}', 1))
                            event['repeat'] = max(1, repeat_val) # Mindestens 1
                        except (ValueError, TypeError):
                             event['repeat'] = 1
                    
                    new_schedule[day].append(event)
        
        # Schreibe die neue Konfiguration in die Datei
        with open('schedule.json', 'w', encoding='utf-8') as f:
            json.dump(new_schedule, f, indent=4)
        
        flash(_("Sendeplan erfolgreich gespeichert!"), "success")

    except Exception as e:
        flash(_("Fehler beim Speichern des Sendeplans: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='schedule'))



@app.route('/upload_font', methods=['POST'])
def upload_font():
    if 'font_file' not in request.files:
        flash(_('Keine Datei im Request gefunden.'), 'error')
        return redirect(url_for('index', active_tab='settings'))
        
    file = request.files['font_file']
    if file.filename == '':
        flash(_('Keine Datei ausgewählt.'), 'warning')
        return redirect(url_for('index', active_tab='settings'))

    if file and file.filename.lower().endswith(VALID_FONT_EXTENSIONS):
        # Sicherheitsfunktion, um ungültige Zeichen aus Dateinamen zu entfernen
        filename = secure_filename(file.filename)
        upload_path = os.path.join(FONTS_DIR, filename)
        
        if os.path.exists(upload_path):
            flash(_("Eine Schriftart mit dem Namen '%(filename)s' existiert bereits.", filename=filename), "warning")
        else:
            file.save(upload_path)
            flash(_("Schriftart '%(filename)s' erfolgreich hochgeladen!", filename=filename), "success")
    else:
        flash(_('Ungültiger Dateityp. Nur .ttf und .otf sind erlaubt.'), 'error')
        
    return redirect(url_for('index', active_tab='settings'))

@app.route('/delete_font', methods=['POST'])
def delete_font():
    font_name = request.form.get('font_name_to_delete')
    if not font_name:
        flash(_('Kein Schriftart-Name übergeben.'), 'error')
        return redirect(url_for('index', active_tab='settings'))
    
    # Sicherheitsprüfung: Stelle sicher, dass der Dateiname keine Pfade enthält
    secure_name = secure_filename(font_name)
    if secure_name != font_name:
        flash(_('Ungültiger Schriftart-Name.'), 'error')
        return redirect(url_for('index', active_tab='settings'))
        
    font_path = os.path.join(FONTS_DIR, secure_name)
    
    try:
        if os.path.exists(font_path):
            os.remove(font_path)
            flash(_("Schriftart '%(name)s' wurde gelöscht.", name=secure_name), "success")
        else:
            flash(_('Zu löschende Schriftart nicht gefunden.'), 'warning')
    except Exception as e:
        flash(_("Fehler beim Löschen der Schriftart: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='settings'))

@app.route('/save_settings_js', methods=['POST'])
def save_settings_js():
    try:
        # --- TEIL 1: IMMER die config.json speichern ---
        form_data = request.form
        try:
            with open(CONFIG_JSON, 'r', encoding='utf-8') as f: config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): 
            config = {"twitch_api": {}, "stream_settings": {}, "ffmpeg": {}, "twitch_bot": {}}

        # --- KORREKTE, DETAILIERTE AKTUALISIERUNG ---
        config['twitch_api'].update({
            "client_id": form_data.get('twitch_client_id'),
            "channel_name": form_data.get('twitch_channel_name')
        })
        # Speichere das Secret nur, wenn ein neues eingegeben wurde
        if form_data.get('twitch_client_secret'):
            config['twitch_api']['client_secret'] = form_data.get('twitch_client_secret')
        
        config['stream_settings'].update({
            "rtmp_url": form_data.get('rtmp_url')
        })
        if form_data.get('stream_key'):
            config['stream_settings']['stream_key'] = form_data.get('stream_key')

        config['ffmpeg'].update({
            "font_file": form_data.get('ffmpeg_font_file'), "font_position": form_data.get('ffmpeg_font_position'),
            "font_size": form_data.get('ffmpeg_font_size', type=int), "font_color": form_data.get('ffmpeg_font_color'),
            "box_color": form_data.get('ffmpeg_box_color'), "box_alpha": form_data.get('ffmpeg_box_alpha', type=float),
            "encoder": form_data.get('ffmpeg_encoder'), "stream_mode": form_data.get('ffmpeg_stream_mode'),
            "video_bitrate": form_data.get('ffmpeg_video_bitrate'), "audio_bitrate": form_data.get('ffmpeg_audio_bitrate'),
            "preset": form_data.get('ffmpeg_preset'), "resolution": form_data.get('ffmpeg_resolution'),
            "framerate": form_data.get('ffmpeg_framerate'),
            "auto_restart_interval_hours": form_data.get('auto_restart_interval_hours', 24, type=int),
            "auto_restart_time": form_data.get('auto_restart_time', '')
        })
        
        # --- NEU: Twitch Bot Konfiguration speichern ---
        if 'twitch_bot' not in config: config['twitch_bot'] = {}
        config['twitch_bot'].update({
            "bot_nick": form_data.get('bot_nick'),
            "channel_nick": form_data.get('channel_nick')
        })
        if form_data.get('bot_token'):
            config['twitch_bot']['bot_token'] = form_data.get('bot_token')
        # ---------------------------------------------

        with open(CONFIG_JSON, 'w', encoding='utf-8') as f: json.dump(config, f, indent=2)

        # --- TEIL 2: Session.json für Neustart-Signale anpassen ---
        action = form_data.get('action')
        session_data = {}
        try:
            with open('session.json', 'r', encoding='utf-8') as f: session_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): pass

        session_data['restart_pending'] = False
        session_data['force_restart'] = False

        if action == 'save_soft':
            session_data['restart_pending'] = True
        elif action == 'save_hard':
            session_data['force_restart'] = True
            
        with open('session.json', 'w', encoding='utf-8') as f: json.dump(session_data, f, indent=2)
        
        return jsonify(success=True)
    except Exception as e:
        # Ersetze die technische Fehlermeldung durch eine benutzerfreundliche, übersetzbare
        return jsonify(success=False, error=_("Ein unerwarteter Fehler beim Speichern ist aufgetreten.")), 500


@app.route('/save_config_preset', methods=['POST'])
def save_config_preset():
    try:
        preset_name = request.form.get('preset_name')
        if not preset_name or not preset_name.strip():
            return jsonify(success=False, error=_("Preset-Name darf nicht leer sein.")), 400

        # Wir lesen die aktuelle config.json von der Festplatte, die korrekt sein sollte
        with open(CONFIG_JSON, 'r', encoding='utf-8') as f:
            current_config = json.load(f)
        
        presets = {}
        try:
            with open('config_presets.json', 'r', encoding='utf-8') as f: presets = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): pass
        
        presets[preset_name.strip()] = current_config
        
        with open('config_presets.json', 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=2)
        
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=_("Fehler beim Speichern des Presets.")), 500


@app.route('/load_config_preset', methods=['POST'])
def load_config_preset():
    """Lädt ein Preset und überschreibt die config.json."""
    try:
        preset_name = request.form.get('preset_to_load')
        if not preset_name:
            return jsonify(success=False, error=_("Kein Preset zum Laden ausgewählt.")), 400

        with open('config_presets.json', 'r', encoding='utf-8') as f:
            presets = json.load(f)
        
        config_to_load = presets.get(preset_name)
        
        if config_to_load:
            with open(CONFIG_JSON, 'w', encoding='utf-8') as f:
                json.dump(config_to_load, f, indent=2)
            return jsonify(success=True)
        else:
            return jsonify(success=False, error=_("Preset '%(name)s' nicht gefunden.", name=preset_name)), 404
    except Exception as e:
        return jsonify(success=False, error=_("Fehler beim Laden des Presets.")), 500

@app.route('/delete_config_preset', methods=['POST'])
def delete_config_preset():
    """Löscht ein benanntes Preset aus der config_presets.json."""
    try:
        preset_name = request.form.get('preset_to_delete')
        if not preset_name:
            return jsonify(success=False, error=_("Kein Preset zum Löschen ausgewählt.")), 400

        presets = {}
        try:
            with open('config_presets.json', 'r', encoding='utf-8') as f:
                presets = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify(success=False, error=_("Preset-Datei nicht gefunden.")), 404

        if preset_name in presets:
            del presets[preset_name]
            with open('config_presets.json', 'w', encoding='utf-8') as f:
                json.dump(presets, f, indent=2)
            return jsonify(success=True)
        else:
            return jsonify(success=False, error=_("Preset '%(name)s' nicht gefunden.", name=preset_name)), 404
            
    except Exception as e:
        return jsonify(success=False, error=_("Fehler beim Löschen des Presets.")), 500
   
@app.route('/api/now_playing')
def api_now_playing():
    """
    Stellt einen erweiterten JSON-Endpunkt mit Live-Informationen bereit.
    """
    global api_cache

    # --- Grundstruktur der Antwort ---
    response_data = {
        "stream_status": "OFFLINE",
        "last_played": None,
        "now_playing": None,
        "next_up": [],
        "scheduled_event": None,
        "playlist": None
    }

    # --- 1. Lese Live-Daten (status.json & session.json) ---
    try:
        with open(STATUS_JSON, 'r', encoding='utf-8') as f: status = json.load(f)
        with open('session.json', 'r', encoding='utf-8') as f: session = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify(response_data) # Wenn keine Status-Datei da ist, ist der Stream offline.

    if status.get('status') != 'Online':
        return jsonify(response_data)
        
    response_data['stream_status'] = 'ONLINE'

    # --- 2. Aktueller Titel & Fortschritt ---
    na_string = _("N/A") # Übersetzbarer Fallback-Wert
    current_video_path = status.get('now_playing', '')
    duration = status.get('video_duration', 0)
    elapsed = status.get('video_elapsed', 0)
    progress_percent = int((elapsed / duration) * 100) if duration > 0 else 0

    response_data['now_playing'] = {
        "title": status.get('title', na_string),
        "game": status.get('game', na_string),
        "duration_seconds": duration,
        "elapsed_seconds": elapsed,
        "progress_percent": progress_percent
    }

    # --- 3. Letzter Titel (via Cache) ---
    if api_cache.get('current_path') != current_video_path:
        api_cache['last_played'] = api_cache.get('now_playing')
        api_cache['current_path'] = current_video_path
        api_cache['now_playing'] = response_data['now_playing']
    response_data['last_played'] = api_cache['last_played']

    # --- 4. Playlist-Daten & Nächste 5 Titel ---
    try:
        active_playlist_id = session.get('active_playlist_id')
        playlists_db = load_playlists_db()
        active_playlist_info = playlists_db.get(active_playlist_id)

        if active_playlist_info:
            filename = active_playlist_info['filename']
            state = session.get('playlist_states', {}).get(filename)
            if state:
                next_index = state.get('resume_index', 0)
                playlist_path = os.path.join('playlists', filename)
                with open(playlist_path, 'r', encoding='utf-8') as f:
                    rows = list(csv.reader(f))
                
                total_tracks = len(rows)
                if total_tracks > 0:
                    response_data['playlist'] = {
                        "name": active_playlist_info.get('name', na_string),
                        "current_track_number": (next_index - 1 + total_tracks) % total_tracks + 1,
                        "total_tracks": total_tracks
                    }

                    for i in range(5):
                        idx = (next_index + i) % total_tracks
                        if idx < len(rows) and len(rows[idx]) >= 3:
                            response_data['next_up'].append({
                                "title": rows[idx][1],
                                "game": rows[idx][2]
                            })
    except Exception:
        pass # Fehler beim Lesen der Playlist ignorieren

    # --- 5. Nächstes geplantes Event ---
    try:
        with open('schedule.json', 'r', encoding='utf-8') as f: schedule = json.load(f)
        playlists_db = load_playlists_db()
        now = datetime.now()
        found_event = None
        
        for i in range(7):
            check_date = now + timedelta(days=i)
            day_name = check_date.strftime('%A').lower()
            todays_events = schedule.get(day_name, [])

            for event in sorted(todays_events, key=lambda x: x.get('start_time', '')):
                event_time_str = event.get('start_time')
                if event_time_str:
                    event_time = datetime.strptime(f"{check_date.strftime('%Y-%m-%d')} {event_time_str}", '%Y-%m-%d %H:%M')
                    if event_time > now:
                        found_event = event
                        time_until = event_time - now
                        break
            if found_event:
                break
        
        if found_event:
            playlist_info = playlists_db.get(found_event['playlist'])
            if playlist_info:
                response_data['scheduled_event'] = {
                    "title": playlist_info.get('name', _('Geplantes Event')),
                    "start_time": found_event.get('start_time'),
                    "time_until_seconds": int(time_until.total_seconds()),
                    "time_until_human": str(timedelta(seconds=int(time_until.total_seconds())))
                }
    except Exception:
        pass # Fehler beim Lesen des Sendeplans ignorieren

    return jsonify(response_data)
  
@app.route('/add_bot_command', methods=['POST'])
def add_bot_command():
    """Fügt einen neuen, flexiblen Befehl zur commands.json hinzu."""
    try:
        command_name = request.form.get('command_name').lower()
        if not command_name.startswith('!'):
            flash(_("Fehler: Ein Befehl muss mit '!' beginnen."), "error")
            return redirect(url_for('index', active_tab='bot'))

        # Baue das neue, flexible "action"-Objekt
        action_type = request.form.get('action_type')
        action_obj = {"type": action_type}
        if action_type == 'stream_control':
            action_obj['command'] = request.form.get('stream_control_command')
        elif action_type == 'chat_reply':
            action_obj['message'] = request.form.get('chat_reply_message')

        new_command = {
            "action": action_obj,
            "permissions": request.form.get('permissions'),
            "cooldown": request.form.get('cooldown', 10, type=int),
            "response": request.form.get('response') or None # Speichere None statt leerem String
        }

        commands = {}
        try:
            with open('commands.json', 'r', encoding='utf-8') as f:
                commands = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        commands[command_name] = new_command
        
        with open('commands.json', 'w', encoding='utf-8') as f:
            json.dump(commands, f, indent=2)

        flash(_("Befehl '%(name)s' erfolgreich hinzugefügt!", name=command_name), "success")
    except Exception as e:
        flash(_("Fehler beim Hinzufügen des Befehls: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='bot'))


@app.route('/delete_bot_command', methods=['POST'])
def delete_bot_command():
    """Löscht einen Befehl aus der commands.json."""
    try:
        command_name = request.form.get('command_name')
        
        commands = {}
        try:
            with open('commands.json', 'r', encoding='utf-8') as f:
                commands = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            flash(_("Befehlsdatei nicht gefunden."), "error")
            return redirect(url_for('index', active_tab='bot'))

        if command_name in commands:
            del commands[command_name]
            with open('commands.json', 'w', encoding='utf-8') as f:
                json.dump(commands, f, indent=2)
            flash(_("Befehl '%(name)s' erfolgreich gelöscht!", name=command_name), "success")
        else:
            flash(_("Zu löschender Befehl nicht gefunden."), "warning")

    except Exception as e:
        flash(_("Fehler beim Löschen des Befehls: %(error)s", error=e), "error")

    return redirect(url_for('index', active_tab='bot'))  

# In V_5-05-web_manager.py

@app.route('/api/search_game')
def search_game():
    """Sucht bei Twitch nach Spiel-Kategorien basierend auf einer Suchanfrage."""
    query = request.args.get('query', '')
    if len(query) < 2:
        # Sende keine Anfrage für zu kurze Suchbegriffe
        return jsonify([])

    try:
        with open(CONFIG_JSON, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify(error="Config not found"), 500

    client_id = config.get('twitch_api', {}).get('client_id')
    access_token = get_valid_token() # Holt einen gültigen Token

    if not client_id or not access_token:
        print(f"{Fore.RED}" + _("API-FEHLER: Twitch Client-ID oder Token für Spielsuche nicht verfügbar."))
        return jsonify(error="Twitch auth not configured"), 500

    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    params = {
        'query': query,
        'first': 10  # Wir holen maximal 10 Ergebnisse
    }

    try:
        response = requests.get('https://api.twitch.tv/helix/search/categories', headers=headers, params=params, timeout=5)
        response.raise_for_status() # Löst einen Fehler aus, wenn der API-Call fehlschlägt
        
        data = response.json()
        
        # Extrahiere nur die Namen der Spiele aus der Twitch-Antwort
        game_names = [game['name'] for game in data.get('data', [])]
        
        return jsonify(game_names)

    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}" + _("Fehler bei der Twitch-Spielsuche: %(error)s", error=e))
        return jsonify(error=str(e)), 503



if __name__ == '__main__':
    try:
        with open(MANAGER_CONFIG_JSON, 'r', encoding='utf-8') as f:
            manager_cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Wenn die Datei nicht existiert, setze Standardwerte
        manager_cfg = {'port': 5000}
    
    # Lese den Port aus der Konfig, mit 5000 als absolut letztem Fallback
    port = manager_cfg.get('port', 5000)
    
    auto_restart_thread = threading.Thread(target=auto_restart_monitor, daemon=True)
    auto_restart_thread.start()
    
    print(f"Playlist Manager started! Open https://127.0.0.1:{port} in your browser.")
    # Füge ssl_context='adhoc' hinzu, um HTTPS zu aktivieren
    app.run(host='127.0.0.1', port=port, debug=True, ssl_context='adhoc')