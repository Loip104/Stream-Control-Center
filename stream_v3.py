# stream_v3.py - V6.3: Version mit Signal- und Sendeplan-Prüfung
import subprocess
import time
import os
import requests
import csv
import json
import hashlib
import platform
import threading
from colorama import Fore, init
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_EXE = os.path.join(BASE_DIR, 'ffmpeg', 'bin', 'ffmpeg.exe')
FFPROBE_EXE = os.path.join(BASE_DIR, 'ffmpeg', 'bin', 'ffprobe.exe')

# Colorama initialisieren
init(autoreset=True)

# Globale Variablen
BROADCASTER_ID = None
CONFIG = None

# --- Helper Functions (unverändert) ---
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

def get_twitch_user_id(username):
    if not CONFIG: return None
    headers = {'Client-ID': CONFIG['twitch_api']['client_id'], 'Authorization': f"Bearer {CONFIG['twitch_api']['oauth_token']}"}
    params = {'login': username}
    try:
        response = requests.get('https://api.twitch.tv/helix/users', headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('data'):
            print(f"Twitch User-ID für '{username}' erfolgreich abgerufen.")
            return data['data'][0]['id']
        else:
            print(f"FEHLER: Twitch User '{username}' nicht gefunden.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Fehler beim Abrufen der User-ID: {e}")
        return None

def get_game_id(game_name):
    if not CONFIG: return None
    headers = {'Client-ID': CONFIG['twitch_api']['client_id'], 'Authorization': f"Bearer {CONFIG['twitch_api']['oauth_token']}"}
    params = {'name': game_name}
    try:
        response = requests.get('https://api.twitch.tv/helix/games', headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('data'):
            return data['data'][0]['id']
        else:
            print(f"WARNUNG: Spiel '{game_name}' wurde auf Twitch nicht gefunden.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Fehler bei der Spielsuche: {e}")
        return None

def update_stream_info(title, game_name, language):
    if not BROADCASTER_ID: return
    print(f"Aktualisiere Twitch-Metadaten -> Titel: {title} | Spiel: {game_name}")
    headers = {'Client-ID': CONFIG['twitch_api']['client_id'], 'Authorization': f"Bearer {CONFIG['twitch_api']['oauth_token']}",'Content-Type': 'application/json'}
    body = {'title': title, 'broadcaster_language': language}
    game_id = get_game_id(game_name)
    if game_id: body['game_id'] = game_id
    try:
        url = f'https://api.twitch.tv/helix/channels?broadcaster_id={BROADCASTER_ID}'
        requests.patch(url, headers=headers, json=body, timeout=10).raise_for_status()
    except requests.exceptions.RequestException as e: print(f"Fehler beim Aktualisieren der Stream-Info: {e}")

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
        print(f"{Fore.CYAN}--- Starte FFmpeg im Remux-Modus (Kopieren) ---")
        command.extend(['-c', 'copy'])
    
    else: # Transcoding-Modus
        print(f"{Fore.CYAN}--- Starte FFmpeg im Transcode-Modus ---")
        video_filters = []

        # Filter nur im Transcoding-Modus hinzufügen
        if ffmpeg_cfg.get('resolution'):
            video_filters.append(f"scale={ffmpeg_cfg['resolution']}")
        if ffmpeg_cfg.get('framerate'):
            video_filters.append(f"fps={ffmpeg_cfg['framerate']}")
        if ffmpeg_cfg.get('font_file'):
            font_path = os.path.join('fonts', ffmpeg_cfg['font_file']).replace('\\', '/')
            position_map = {
                'top_center':    "x=(w-text_w)/2:y=10",
                'bottom_center': "x=(w-text_w)/2:y=h-text_h-10"
            }
            position = position_map.get(ffmpeg_cfg.get('font_position', 'bottom_center'), "x=(w-text_w)/2:y=h-text_h-10")
            box_color = ffmpeg_cfg.get('box_color', '#000000')
            box_alpha = ffmpeg_cfg.get('box_alpha', 0.5)
            box_color_with_alpha = f"{box_color}@{box_alpha}"
            drawtext_filter = (f"drawtext=fontfile='{font_path}':textfile='now_playing.txt':reload=1:{position}:fontsize={ffmpeg_cfg.get('font_size', 24)}:fontcolor={ffmpeg_cfg.get('font_color', 'white')}:box=1:boxcolor='{box_color_with_alpha}':boxborderw=10")
            video_filters.append(drawtext_filter)

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

    print(" ".join(f"'{c}'" if " " in c else c for c in command))
    return subprocess.Popen(command, creationflags=creation_flags, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace', bufsize=1)
    
    
# #############################################################################
# --- NEUE FUNKTION: Signal- und Sendeplan-Prüfung ---
# #############################################################################
def check_and_apply_signals():
    """Prüft Signale und Sendeplan und arbeitet ausschließlich mit IDs."""
    session_file = 'session.json'
    schedule_file = 'schedule.json' # <-- DAS WAR DIE FEHLENDE ZEILE

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
            print(f"{Fore.CYAN}--- SENDEPLAN: Zeit-Event beendet. ---")
            event_ended = True
        
        if event_ended:
            return_playlist_id = active_event.get('return_to', schedule.get('default_playlist'))
            return_playlist_info = playlists_db.get(return_playlist_id)
            if return_playlist_info:
                print(f"{Fore.CYAN}--- SENDEPLAN: Kehre zurück zu Playlist '{return_playlist_info.get('name')}' ---")
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
                print(f"{Fore.YELLOW}WARNUNG: Playlist-ID '{playlist_id}' aus Sendeplan nicht gefunden.")
                continue

            print(f"{Fore.CYAN}--- SENDEPLAN: Starte Event für Playlist '{playlist_info.get('name')}' ---")
            
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
        
        # NEU: Leite jede empfangene Zeile sofort an den eigenen stderr-Ausgang weiter.
        # Da web_manager.py diesen Ausgang in die ffmpeg.log umleitet, landet die Zeile dort.
        sys.stderr.write(line)
        sys.stderr.flush()

        # Der bisherige Code zur Analyse der Zeit für den Fortschrittsbalken bleibt unverändert.
        if 'time=' in line and 'speed=' in line:
            try:
                time_str = line.split('time=')[1].split(' ')[0]
                h, m, s = map(float, time_str.split(':'))
                total_seconds = h * 3600 + m * 60 + s
                shared_state['ffmpeg_time'] = total_seconds
            except:
                pass # Ignoriere fehlerhafte Zeilen

def main():
    global BROADCASTER_ID, CONFIG
    status_file, session_file = 'status.json', 'session.json'
    print(f"Streamer V6.5 (Echter Sanfter Neustart) gestartet.")
    ffmpeg_process = None
    soft_restart_is_pending = False # Der "Merkzettel" für den sanften Neustart

    while True:
        try:
            # --- Signalverarbeitung mit Priorität ---
            session_data = {}
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                pass 

            if session_data.get('force_restart'):
                session_data['force_restart'] = False
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=2)
                print(f"{Fore.GREEN}--- Sofort-Neustart-Signal verarbeitet ---")
            
            # --- Setup-Phase ---
            CONFIG = load_config()
            if not CONFIG: time.sleep(10); continue

            try:
                with open('videos.json', 'r', encoding='utf-8') as f: videos_db = json.load(f)
                with open('playlists.json', 'r', encoding='utf-8') as f: playlists_db = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                print(f"{Fore.RED}FEHLER: videos.json oder playlists.json nicht gefunden."); time.sleep(30); continue

            if not BROADCASTER_ID: BROADCASTER_ID = get_twitch_user_id(CONFIG['twitch_api']['channel_name'])

            active_playlist_id = session_data.get('active_playlist_id')
            active_playlist_info = playlists_db.get(active_playlist_id)

            if not active_playlist_info:
                print(f"{Fore.YELLOW}Warnung: Keine gültige 'active_playlist_id' in session.json. Nutze Fallback.")
                try:
                    with open('schedule.json', 'r', encoding='utf-8') as f: schedule = json.load(f)
                    active_playlist_id = schedule.get('default_playlist')
                    active_playlist_info = playlists_db.get(active_playlist_id)
                except (FileNotFoundError, json.JSONDecodeError): active_playlist_info = None
                
                if not active_playlist_info and playlists_db:
                    active_playlist_id = list(playlists_db.keys())[0]
                    active_playlist_info = playlists_db[active_playlist_id]

            if not active_playlist_info:
                print(f"{Fore.RED}FEHLER: Konnte keine aktive Playlist ermitteln."); time.sleep(30); continue

            active_playlist_filename = active_playlist_info['filename']
            playlist_path = os.path.join('playlists', active_playlist_filename)
            print(f"--- Lade aktive Playlist: '{active_playlist_filename}' (ID: {active_playlist_id}) ---")
            
            soft_restart_is_pending = False
            
            # --- Signatur-Check ---
            with open(playlist_path, 'r', encoding='utf-8') as f: playlist_content = f.read()
            signature = hashlib.sha256(playlist_content.encode('utf-8')).hexdigest()
            playlist_states = session_data.get('playlist_states', {})
            if active_playlist_filename not in playlist_states or playlist_states[active_playlist_filename].get('signature') != signature:
                playlist_states[active_playlist_filename] = {'resume_index': 0, 'signature': signature}
                session_data['playlist_states'] = playlist_states
                
                # Speichere die Session sofort, um die neue Signatur zu persistieren.
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=2)
                    
            resume_index = playlist_states[active_playlist_filename].get('resume_index', 0)
            
            # --- Playlist-Ladeblock ---
# --- Playlist-Ladeblock (Bulletproof Version) ---
            full_playlist = []
            print("--- Überprüfe Videodateien via ID-System ---")
            
            # Filtert leere Zeilen aus der Playlist-Datei heraus, um Fehler zu vermeiden
            lines = [line for line in playlist_content.splitlines() if line.strip()]
            
            for i, row in enumerate(csv.reader(lines)):
                try:
                    # Prüfe, ob die Zeile genügend Spalten hat und aktiv ist
                    if len(row) >= 4 and row[3].strip() == '1':
                        video_id = row[0].strip()
                        if not video_id:
                            continue # Überspringe Zeilen ohne Video-ID

                        video_info = videos_db.get(video_id)
                        
                        if not video_info:
                            print(f"{Fore.YELLOW}WARNUNG (Zeile {i+1}): Video-ID '{video_id}' nicht in videos.json gefunden.")
                            continue

                        video_path = video_info.get('path')
                        if not video_path or not os.path.exists(video_path):
                            print(f"{Fore.YELLOW}WARNUNG (Zeile {i+1}): Videopfad für ID '{video_id}' nicht gefunden: {video_path}")
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
                    print(f"{Fore.YELLOW}WARNUNG: Zeile {i+1} in Playlist konnte nicht gelesen werden und wird übersprungen. Fehler: {e}")
                    continue
            
            if resume_index >= len(full_playlist): resume_index = 0
            playlist_for_ffmpeg = full_playlist[resume_index:] + full_playlist[:resume_index]
            
            timeline, current_offset = [], 0
            for video in playlist_for_ffmpeg:
                timeline.append({'start_offset': current_offset, 'end_offset': current_offset + video['duration'], 'video_info': video})
                current_offset += video['duration']
            total_cycle_duration = current_offset if current_offset > 0 else 1

            # Erst danach wird die Datei für FFmpeg geschrieben
            ffmpeg_playlist_file = 'ffmpeg_playlist.txt'
            with open(ffmpeg_playlist_file, 'w', encoding='utf-8') as f:
                # SCHLEIFE 2: Schreibt die Pfade in die Datei
                for video in playlist_for_ffmpeg:
                    # Hier ist unsere Korrektur von vorhin
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
                    print(f"{Fore.RED}FFmpeg-Prozess unerwartet beendet. Starte Zyklus neu.")
                    break

                current_session = {}
                try:
                    with open(session_file, 'r', encoding='utf-8') as f: current_session = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError): pass

                if current_session.get('force_restart'):
                    print(f"{Fore.YELLOW}--- SOFORT-Neustart-Signal erkannt. ---")
                    if ffmpeg_process: ffmpeg_process.terminate(); ffmpeg_process.wait(timeout=5)
                    break 

                if current_session.get('restart_pending'):
                    print(f"{Fore.CYAN}--- SANFTER Neustart vorgemerkt. Warte auf nächstes Video. ---")
                    soft_restart_is_pending = True
                    current_session['restart_pending'] = False
                    with open(session_file, 'w', encoding='utf-8') as f: json.dump(current_session, f, indent=2)

                if check_and_apply_signals():
                    print(f"{Fore.YELLOW}--- Sendeplan-Signal verarbeitet. Starte Stream-Zyklus neu. ---")
                    if ffmpeg_process: ffmpeg_process.terminate(); ffmpeg_process.wait(timeout=5)
                    break
                
                time_in_cycle = shared_state['ffmpeg_time'] % total_cycle_duration
                current_video_entry, index_in_timeline = next(( (e, i) for i, e in enumerate(timeline) if e['start_offset'] <= time_in_cycle < e['end_offset']), (None, -1) )

                if current_video_entry and currently_playing_video_path != current_video_entry['video_info']['path']:
                    if soft_restart_is_pending:
                        print(f"{Fore.CYAN}--- Nächstes Video erreicht. Führe SANFTEN NEUSTART jetzt aus. ---")
                        if ffmpeg_process: ffmpeg_process.terminate(); ffmpeg_process.wait(timeout=5)
                        break

                    video = current_video_entry['video_info']
                    currently_playing_video_path = video['path']
                    print(f"FFmpeg-Uhr-Sync: Neues Video -> {os.path.basename(video['path'])}")
                    
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
                    
                    # Lese die Session erneut, um die neuesten Daten zu haben, bevor wir schreiben
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
                            print(f"{Fore.CYAN}--- SENDEPLAN: Repeat-Event hat Schleife {loops_done}/{active_event.get('repeat')} abgeschlossen. ---")
                            
                            if loops_done >= active_event.get('repeat', 1):
                                print(f"{Fore.CYAN}--- SENDEPLAN: Repeat-Event beendet. ---")
                                session_to_update['active_event'] = None
                                session_to_update['force_restart'] = True

                    with open(session_file, 'w', encoding='utf-8') as f: json.dump(session_to_update, f, indent=2)

                if current_video_entry:
                    video_elapsed = time_in_cycle - current_video_entry['start_offset']
                    status_data = {"status": "Online", "now_playing": os.path.basename(current_video_entry['video_info']['path']), "title": current_video_entry['video_info']['title'], "game": current_video_entry['video_info']['game'], "video_duration": current_video_entry['video_info'].get('duration', 0), "video_elapsed": video_elapsed}
                else:
                    status_data = {"status": "Online", "now_playing": "Warte auf Sync...", "title": "", "game": "", "video_duration": 0, "video_elapsed": 0}
                with open(status_file, 'w', encoding='utf-8') as f: json.dump(status_data, f)
                
                time.sleep(1)

        except KeyboardInterrupt:
            if ffmpeg_process: ffmpeg_process.terminate()
            print("\nSkript beendet.")
            break
        except Exception as e:
            if ffmpeg_process: ffmpeg_process.terminate()
            print(f"{Fore.RED}Unerwarteter Fehler in der Hauptschleife: {e}"); 
            import traceback
            traceback.print_exc()
            time.sleep(10)
            
if __name__ == "__main__":
    main()