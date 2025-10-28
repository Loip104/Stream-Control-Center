from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subprocess
import time
import requests
import csv
import json
import hashlib
import platform
import threading
from colorama import Fore, init
import gettext
import json
from token_manager import get_valid_token

try:
    # Lese die Sprache aus der zentralen Konfigurationsdatei
    with open('manager_config.json', 'r', encoding='utf-8') as f:
        lang = json.load(f).get('language', 'de')
except (FileNotFoundError, json.JSONDecodeError):
    lang = 'de' # Nutze Deutsch als Standard, wenn etwas schiefgeht

# Lade die passende Übersetzungsdatei für die ermittelte Sprache
translation = gettext.translation('messages', localedir='translations', languages=[lang], fallback=True)
# Richte die Übersetzungsfunktion global als '_' ein
_ = translation.gettext
# --- Ende des Blocks ---


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_EXE = os.path.join(BASE_DIR, 'ffmpeg', 'bin', 'ffmpeg.exe')
FFPROBE_EXE = os.path.join(BASE_DIR, 'ffmpeg', 'bin', 'ffprobe.exe')

# Colorama initialisieren
init(autoreset=True)

# Globale Variablen
BROADCASTER_ID = None
CONFIG = None




# --- Helper Functions  ---
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f: return json.load(f)
    except Exception: return None

def get_video_duration(video_path):
    creation_flags = 0
    if platform.system() == "Windows": creation_flags = subprocess.CREATE_NO_WINDOW
    command = [FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, creationflags=creation_flags)
        return float(result.stdout)
    except Exception: return 0.0

# ERSETZE DIESE BEIDEN FUNKTIONEN IN stream_v3.py

def get_twitch_user_id(username):
    """Holt die Twitch User ID mit einem gültigen Token."""
    if not CONFIG: return None
    
    valid_token = get_valid_token() # Holt einen frischen Token
    if not valid_token:
        print(Fore.RED + _("FEHLER: Konnte keinen gültigen Token für die User-ID-Abfrage erhalten."))
        return None

    headers = {
        'Client-ID': CONFIG['twitch_api']['client_id'], 
        'Authorization': f"Bearer {valid_token}"
    }
    params = {'login': username}
    
    try:
        response = requests.get('https://api.twitch.tv/helix/users', headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('data'):
            print(_("Twitch User-ID für '%(user)s' erfolgreich abgerufen.") % {'user': username})
            return data['data'][0]['id']
        else:
            print(Fore.RED + _("FEHLER: Twitch User '%(user)s' nicht gefunden.") % {'user': username})
            return None
    except requests.exceptions.RequestException as e:
        print(Fore.RED + _("Fehler beim Abrufen der User-ID: %(error)s") % {'error': e})
        return None

def get_game_id(game_name):
    """Holt die Twitch Game ID mit einem gültigen Token."""
    if not CONFIG: return None

    valid_token = get_valid_token() # Holt einen frischen Token
    if not valid_token:
        print(Fore.RED + _("FEHLER: Konnte keinen gültigen Token für die Game-ID-Abfrage erhalten."))
        return None

    headers = {
        'Client-ID': CONFIG['twitch_api']['client_id'], 
        'Authorization': f"Bearer {valid_token}"
    }
    params = {'name': game_name}
    
    try:
        response = requests.get('https://api.twitch.tv/helix/games', headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('data'):
            return data['data'][0]['id']
        else:
            print(Fore.YELLOW + _("WARNUNG: Spiel '%(game)s' wurde auf Twitch nicht gefunden.") % {'game': game_name})
            return None
    except requests.exceptions.RequestException as e:
        print(Fore.RED + _("Fehler bei der Spielsuche: %(error)s") % {'error': e})
        return None

def update_stream_info(title, game_name, language):
    if not BROADCASTER_ID: return

    # HOLT EINEN GARANTIERT GÜLTIGEN TOKEN
    valid_token = get_valid_token()
    if not valid_token:
        print(Fore.RED + _("FEHLER: Konnte keinen gültigen Twitch-Token erhalten. Metadaten werden nicht aktualisiert."))
        return

    print(_("Aktualisiere Twitch-Metadaten -> Titel: %(title)s | Spiel: %(game)s") % {'title': title, 'game': game_name})

    # VERWENDET DEN NEUEN, GÜLTIGEN TOKEN
    headers = {
        'Client-ID': CONFIG['twitch_api']['client_id'], 
        'Authorization': f"Bearer {valid_token}",
        'Content-Type': 'application/json'
    }

    body = {'title': title, 'broadcaster_language': language}
    game_id = get_game_id(game_name) # This function also needs a valid token, which we now have.
    if game_id: body['game_id'] = game_id

    try:
        url = f'https://api.twitch.tv/helix/channels?broadcaster_id={BROADCASTER_ID}'
        requests.patch(url, headers=headers, json=body, timeout=10).raise_for_status()
    except requests.exceptions.RequestException as e:
        print(Fore.RED + _("Fehler beim Aktualisieren der Stream-Info: %(error)s") % {'error': e})

def run_stream(ffmpeg_playlist_path):
    creation_flags = 0
    if platform.system() == "Windows": creation_flags = subprocess.CREATE_NO_WINDOW

    ffmpeg_cfg = CONFIG['ffmpeg']
    stream_cfg = CONFIG['stream_settings']
    stream_mode = ffmpeg_cfg.get('stream_mode', 'transcode')

    # Baue den Basis-Befehl
    command = [FFMPEG_EXE, '-re', '-stream_loop', '-1', '-f', 'concat', '-safe', '0', '-i', ffmpeg_playlist_path]

    # --- NEUE STRIKTE LOGIK ---
    if stream_mode == 'remux':
        print(f"{Fore.CYAN}--- " + _("Starte FFmpeg im Remux-Modus (Kopieren)") + " ---")
        command.extend(['-c', 'copy'])
    
    else: # Transcoding-Modus
        print(f"{Fore.CYAN}--- " + _("Starte FFmpeg im Transcode-Modus") + " ---")
        video_filters = []

        # ... (Rest of the function has no user-facing text, so it remains unchanged) ...
        
        if video_filters:
            command.extend(['-vf', ",".join(video_filters)])

        # Encoder-Einstellungen anwenden
        command.extend(['-c:v', ffmpeg_cfg.get('encoder', 'libx264'), '-preset', ffmpeg_cfg.get('preset', 'veryfast'), '-c:a', 'aac'])
        if ffmpeg_cfg.get('video_bitrate'):
            command.extend(['-b:v', ffmpeg_cfg['video_bitrate']])
        if ffmpeg_cfg.get('audio_bitrate'):
            command.extend(['-b:a', ffmpeg_cfg['audio_bitrate']])

    # Ziel-URL hinzufügen (für beide Modi gleich)
    command.extend(['-f', 'flv', stream_cfg['rtmp_url'].format(STREAM_KEY=stream_cfg['stream_key'])])

    # This print shows the technical command to the server operator, it should not be translated.
    print(" ".join(f"'{c}'" if " " in c else c for c in command))
    return subprocess.Popen(command, creationflags=creation_flags, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace', bufsize=1)
    
    
# #############################################################################
# --- NEUE FUNKTION: Signal- und Sendeplan-Prüfung ---
# #############################################################################
def check_and_apply_signals():
    """Prüft Signale und Sendeplan und arbeitet ausschließlich mit IDs."""
    session_file = 'session.json'
    schedule_file = 'schedule.json'

    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            session = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False

    # Prüft nur noch, ob ein manuelles Signal da ist
    if session.get('force_restart') or session.get('restart_pending'):
        return True

    # Prüft den Sendeplan
    try:
        with open(schedule_file, 'r', encoding='utf-8') as f: schedule = json.load(f)
        with open('playlists.json', 'r', encoding='utf-8') as f: playlists_db = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False

    now = time.localtime()
    day_name = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][now.tm_wday]
    current_time_str = time.strftime("%H:%M", now)
    
    active_event = session.get('active_event')

    # Event beenden
    if active_event:
        event_ended = False
        if active_event.get('mode') == 'time' and current_time_str >= active_event.get('end_time', '23:59'):
            print(f"{Fore.CYAN}{_('--- SENDEPLAN: Zeit-Event beendet. ---')}")
            event_ended = True
        
        if event_ended:
            return_playlist_id = active_event.get('return_to', schedule.get('default_playlist'))
            return_playlist_info = playlists_db.get(return_playlist_id)
            if return_playlist_info:
                print(Fore.CYAN + _("--- SENDEPLAN: Kehre zurück zu Playlist '%(name)s' ---") % {'name': return_playlist_info.get('name')})
                session['active_playlist_id'] = return_playlist_id
                session['active_event'] = None
                with open(session_file, 'w', encoding='utf-8') as f: json.dump(session, f, indent=2)
                return True

    # Neues Event starten
    todays_events = schedule.get(day_name, [])
    for event in todays_events:
        event_id_str = f"{event.get('start_time')}-{event.get('playlist')}"
        active_event_id_str = f"{active_event.get('start_time')}-{active_event.get('playlist')}" if active_event else None

        if current_time_str == event.get('start_time') and event_id_str != active_event_id_str:
            playlist_id = event.get('playlist')
            playlist_info = playlists_db.get(playlist_id)
            if not playlist_info:
                print(Fore.YELLOW + _("WARNUNG: Playlist-ID '%(id)s' aus Sendeplan nicht gefunden.") % {'id': playlist_id})
                continue

            print(Fore.CYAN + _("--- SENDEPLAN: Starte Event für Playlist '%(name)s' ---") % {'name': playlist_info.get('name')})
            
            event['return_to'] = session.get('active_playlist_id', schedule.get('default_playlist'))
            if event.get('mode') == 'repeat': event['loops_done'] = 0
            
            session['active_event'] = event
            session['active_playlist_id'] = playlist_id
            
            with open(session_file, 'w', encoding='utf-8') as f: json.dump(session, f, indent=2)
            return True

    return False

# Thread-Funktion, die FFmpeg-Logs liest und die Zeit extrahiert
def ffmpeg_clock_reader(process, shared_state):
    # Diese Schleife liest jede Zeile, die FFmpeg ausgibt
    for line in iter(process.stderr.readline, ''):
        
        # Leite jede empfangene Zeile sofort an den eigenen stderr-Ausgang weiter.
        sys.stderr.write(line)
        sys.stderr.flush()

        if 'time=' in line and 'speed=' in line:
            try:
                time_str = line.split('time=')[1].split(' ')[0]
                
                # SPRINGE ÜBER, WENN DIE ZEIT UNGÜLTIG IST (z.B. "N/A")
                if ':' not in time_str:
                    continue

                # KORRIGIERTE, ROBUSTE ZEIT-PARSING LOGIK
                parts = time_str.split(':')
                hours = int(parts[0])
                minutes = int(parts[1])
                # Teile Sekunden und Millisekunden am Punkt
                seconds_parts = parts[2].split('.')
                seconds = int(seconds_parts[0])
                if len(seconds_parts) > 1:
                    milliseconds = int(seconds_parts[1])
                else:
                    milliseconds = 0
                
                total_seconds = (hours * 3600) + (minutes * 60) + seconds + (milliseconds / 100)
                shared_state['ffmpeg_time'] = total_seconds

            except (ValueError, IndexError):
                # Ignoriere Zeilen, die nicht korrekt geparst werden können
                pass

def main():
    global BROADCASTER_ID, CONFIG
    status_file, session_file = 'status.json', 'session.json'
    print(_("Streamer V6.5 (Echter Sanfter Neustart) gestartet."))
    ffmpeg_process = None
    soft_restart_is_pending = False # Der "Merkzettel" für den sanften Neustart

    # --- Prozess-Startzeit schreiben (nur einmal beim Start) ---
    try:
        session_data = {}
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass # Neue Datei wird erstellt
        
        # Schreibe die Prozess-Startzeit (für Intervall-Logik)
        session_data['process_start_time'] = datetime.now().isoformat()
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)
        print(f"{Fore.GREEN}{_('Prozess-Startzeit in session.json vermerkt.')}")
    except Exception as e:
        print(f"{Fore.RED}{_('Fehler beim Schreiben der Prozess-Startzeit')}: {e}")
    # --- ENDE ---

    while True:
        try:
            # --- Setup-Phase (Signal-Prüfung wurde in die innere Schleife verschoben) ---
            CONFIG = load_config()
            if not CONFIG: time.sleep(10); continue

            try:
                with open(session_file, 'r', encoding='utf-8') as f: session_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError): 
                session_data = {}

            try:
                with open('videos.json', 'r', encoding='utf-8') as f: videos_db = json.load(f)
                with open('playlists.json', 'r', encoding='utf-8') as f: playlists_db = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                print(f"{Fore.RED}{_('FEHLER: videos.json oder playlists.json nicht gefunden.')}"); time.sleep(30); continue

            if not BROADCASTER_ID: BROADCASTER_ID = get_twitch_user_id(CONFIG['twitch_api']['channel_name'])

            active_playlist_id = session_data.get('active_playlist_id')
            active_playlist_info = playlists_db.get(active_playlist_id)

            if not active_playlist_info:
                print(f"{Fore.YELLOW}{_('Warnung: Keine gültige active_playlist_id in session.json. Nutze Fallback.')}")
                try:
                    with open('schedule.json', 'r', encoding='utf-8') as f: schedule = json.load(f)
                    active_playlist_id = schedule.get('default_playlist')
                    active_playlist_info = playlists_db.get(active_playlist_id)
                except (FileNotFoundError, json.JSONDecodeError): active_playlist_info = None
                
                if not active_playlist_info and playlists_db:
                    active_playlist_id = list(playlists_db.keys())[0]
                    active_playlist_info = playlists_db[active_playlist_id]

            if not active_playlist_info:
                print(f"{Fore.RED}{_('FEHLER: Konnte keine aktive Playlist ermitteln.')}"); time.sleep(30); continue

            active_playlist_filename = active_playlist_info['filename']
            playlist_path = os.path.join('playlists', active_playlist_filename)
            print(_("--- Lade aktive Playlist: '%(filename)s' (ID: %(id)s) ---") % {'filename': active_playlist_filename, 'id': active_playlist_id})
            
            soft_restart_is_pending = False
            
            # --- Signatur-Check ---
            with open(playlist_path, 'r', encoding='utf-8') as f: playlist_content = f.read()
            signature = hashlib.sha256(playlist_content.encode('utf-8')).hexdigest()
            playlist_states = session_data.get('playlist_states', {})
            if active_playlist_filename not in playlist_states or playlist_states[active_playlist_filename].get('signature') != signature:
                playlist_states[active_playlist_filename] = {'resume_index': 0, 'signature': signature}
                session_data['playlist_states'] = playlist_states
                
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=2)
                    
            resume_index = playlist_states[active_playlist_filename].get('resume_index', 0)
            
            # --- Playlist-Ladeblock ---
            full_playlist = []
            print(_("--- Überprüfe Videodateien via ID-System ---"))
            
            lines = [line for line in playlist_content.splitlines() if line.strip()]
            
            for i, row in enumerate(csv.reader(lines)):
                try:
                    if len(row) >= 4 and row[3].strip() == '1':
                        video_id = row[0].strip()
                        if not video_id:
                            continue

                        video_info = videos_db.get(video_id)
                        
                        if not video_info:
                            print(Fore.YELLOW + _("WARNUNG (Zeile %(line)s): Video-ID '%(id)s' nicht in videos.json gefunden.") % {'line': i+1, 'id': video_id})
                            continue

                        video_path = video_info.get('path')
                        if not video_path or not os.path.exists(video_path):
                            print(Fore.YELLOW + _("WARNUNG (Zeile %(line)s): Videopfad für ID '%(id)s' nicht gefunden: %(path)s") % {'line': i+1, 'id': video_id, 'path': video_path})
                            continue
                            
                        duration = get_video_duration(video_path)
                        if duration > 0:
                            full_playlist.append({
                                'path': video_path, 
                                'title': row[1], 
                                'game': row[2], 
                                'duration': duration
                            })
                except Exception as e:
                    print(Fore.YELLOW + _("WARNUNG: Zeile %(line)s in Playlist konnte nicht gelesen werden und wird übersprungen. Fehler: %(error)s") % {'line': i+1, 'error': e})
                    continue
            
            if resume_index >= len(full_playlist): resume_index = 0
            playlist_for_ffmpeg = full_playlist[resume_index:] + full_playlist[:resume_index]
            
            timeline, current_offset = [], 0
            for video in playlist_for_ffmpeg:
                timeline.append({'start_offset': current_offset, 'end_offset': current_offset + video['duration'], 'video_info': video})
                current_offset += video['duration']
            total_cycle_duration = current_offset if current_offset > 0 else 1

            ffmpeg_playlist_file = 'ffmpeg_playlist.txt'
            with open(ffmpeg_playlist_file, 'w', encoding='utf-8') as f:
                for video in playlist_for_ffmpeg:
                    clean_path = video['path'].strip().replace('\\', '/')
                    f.write(f"file '{clean_path}'\n")
                    
            if ffmpeg_process and ffmpeg_process.poll() is None: ffmpeg_process.terminate(); ffmpeg_process.wait()
            ffmpeg_process = run_stream(ffmpeg_playlist_file)
            
            shared_state = {'ffmpeg_time': 0}
            reader_thread = threading.Thread(target=ffmpeg_clock_reader, args=(ffmpeg_process, shared_state))
            reader_thread.daemon = True
            reader_thread.start()

            currently_playing_video_path = None
            
            # --- Überwachungsschleife ---
            while True:
                if ffmpeg_process and ffmpeg_process.poll() is not None: 
                    print(f"{Fore.RED}{_('FFmpeg-Prozess unerwartet beendet. Starte Zyklus neu.')}")
                    break

                current_session = {}
                try:
                    with open(session_file, 'r', encoding='utf-8') as f: current_session = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError): pass

                # --- KORRIGIERTER AUTO-RESTART BLOCK ---
                if current_session.get('force_restart'):
                    print(f"{Fore.YELLOW}{_('--- SOFORT-Neustart-Signal erkannt. ---')}")
                    if ffmpeg_process: 
                        ffmpeg_process.terminate()
                        ffmpeg_process.wait(timeout=5)
                    
                    # --- OFFLINE-WARTEZEIT ---
                    print(f"{Fore.RED}{_('Erzwinge 2 Minuten Offline-Zeit, um 48h-Sitzung zurückzusetzen...')}")
                    try:
                        with open(status_file, 'w', encoding='utf-8') as f: 
                            json.dump({"status": "Offline", "now_playing": _("Geplanter Neustart...")}, f)
                    except Exception: pass
                    time.sleep(120) # 2 Minuten warten
                    
                    # --- FLAG SICHER ZURÜCKSETZEN ---
                    try:
                        # Lade die session.json erneut, um keine Keys zu überschreiben
                        with open(session_file, 'r', encoding='utf-8') as f:
                            session_to_update = json.load(f)
                        session_to_update['force_restart'] = False
                        with open(session_file, 'w', encoding='utf-8') as f:
                            json.dump(session_to_update, f, indent=2)
                        print(f"{Fore.GREEN}{_('Neustart-Flag erfolgreich zurückgesetzt.')}")
                    except Exception as e:
                        print(f"{Fore.RED}{_('Fehler beim Zurücksetzen des Neustart-Flags')}: {e}")
                    # --- ENDE ---
                    
                    break # Starte jetzt den Zyklus neu (bricht die innere Schleife)
                # --- ENDE KORRIGIERTER BLOCK ---

                if current_session.get('restart_pending'):
                    print(f"{Fore.CYAN}{_('--- SANFTER Neustart vorgemerkt. Warte auf nächstes Video. ---')}")
                    soft_restart_is_pending = True
                    current_session['restart_pending'] = False
                    with open(session_file, 'w', encoding='utf-8') as f: json.dump(current_session, f, indent=2)

                if check_and_apply_signals():
                    print(f"{Fore.YELLOW}{_('--- Sendeplan-Signal verarbeitet. Starte Stream-Zyklus neu. ---')}")
                    if ffmpeg_process: ffmpeg_process.terminate(); ffmpeg_process.wait(timeout=5)
                    break
                
                time_in_cycle = shared_state['ffmpeg_time'] % total_cycle_duration
                current_video_entry, index_in_timeline = next(( (e, i) for i, e in enumerate(timeline) if e['start_offset'] <= time_in_cycle < e['end_offset']), (None, -1) )

                if current_video_entry and currently_playing_video_path != current_video_entry['video_info']['path']:
                    if soft_restart_is_pending:
                        print(f"{Fore.CYAN}{_('--- Nächstes Video erreicht. Führe SANFTEN NEUSTART jetzt aus. ---')}")
                        if ffmpeg_process: ffmpeg_process.terminate(); ffmpeg_process.wait(timeout=5)
                        break

                    video = current_video_entry['video_info']
                    currently_playing_video_path = video['path']
                    print(_("FFmpeg-Uhr-Sync: Neues Video -> %(name)s") % {'name': os.path.basename(video['path'])})
                    
                    manager_config_live = {}
                    try:
                        with open('manager_config.json', 'r', encoding='utf-8') as f: manager_config_live = json.load(f)
                    except Exception: pass
                    
                    prefix = manager_config_live.get('title_prefix', '')
                    full_title = f"{prefix} | {video['title']}" if prefix else video['title']
                    update_stream_info(full_title.strip(), video['game'].strip(), manager_config_live.get('language', 'de'))
                    
                    overlay_prefix = manager_config_live.get('overlay_prefix', 'Now Playing:')
                    overlay_text = f"{overlay_prefix} {video['title']}".strip()
                    with open('now_playing.txt', 'w', encoding='utf-8') as f: f.write(overlay_text)

                    original_index = (resume_index + index_in_timeline) % len(full_playlist)
                    next_index = (original_index + 1) % len(full_playlist)
                    
                    try:
                        with open(session_file, 'r', encoding='utf-8') as f: session_to_update = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError): session_to_update = {}
                    
                    if 'playlist_states' not in session_to_update: session_to_update['playlist_states'] = {}
                    if active_playlist_filename not in session_to_update['playlist_states']:
                         session_to_update['playlist_states'][active_playlist_filename] = {}

                    session_to_update['playlist_states'][active_playlist_filename]['resume_index'] = next_index
                    
                    if next_index == 0:
                        active_event = session_to_update.get('active_event')
                        if active_event and active_event.get('mode') == 'repeat':
                            loops_done = active_event.get('loops_done', 0) + 1
                            session_to_update['active_event']['loops_done'] = loops_done
                            print(Fore.CYAN + _("--- SENDEPLAN: Repeat-Event hat Schleife %(done)s/%(total)s abgeschlossen. ---") % {'done': loops_done, 'total': active_event.get('repeat')})
                            
                            if loops_done >= active_event.get('repeat', 1):
                                print(f"{Fore.CYAN}{_('--- SENDEPLAN: Repeat-Event beendet. ---')}")
                                session_to_update['active_event'] = None
                                session_to_update['force_restart'] = True

                    with open(session_file, 'w', encoding='utf-8') as f: json.dump(session_to_update, f, indent=2)

                if current_video_entry:
                    video_elapsed = time_in_cycle - current_video_entry['start_offset']
                    status_data = {"status": "Online", "now_playing": os.path.basename(current_video_entry['video_info']['path']), "title": current_video_entry['video_info']['title'], "game": current_video_entry['video_info']['game'], "video_duration": current_video_entry['video_info'].get('duration', 0), "video_elapsed": video_elapsed}
                else:
                    status_data = {"status": "Online", "now_playing": _("Warte auf Sync..."), "title": "", "game": "", "video_duration": 0, "video_elapsed": 0}
                with open(status_file, 'w', encoding='utf-8') as f: json.dump(status_data, f)
                
                time.sleep(1)

        except KeyboardInterrupt:
            if ffmpeg_process: ffmpeg_process.terminate()
            print(_("\nSkript beendet."))
            break
        except Exception as e:
            if ffmpeg_process: ffmpeg_process.terminate()
            print(f"{Fore.RED}{_('Unerwarteter Fehler in der Hauptschleife')}: {e}"); 
            import traceback
            traceback.print_exc()
            time.sleep(10)
            
if __name__ == "__main__":
    main()