import sys
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import socket
import json
import time
import requests
from colorama import Fore, init
import gettext
import traceback
import shutil

def init_config_files():
    """Prüft, ob die benötigten Konfigurationsdateien existieren. Falls nicht, werden sie aus den .example.json Dateien kopiert."""
    files_to_check = {
        'config.json': 'config.example.json',
        'manager_config.json': 'manager_config.example.json',
        'commands.json': 'commands.example.json',
        'rotations.json': 'rotations.example.json',
        'schedule.json': 'schedule.example.json'
    }
    
    for target_file, example_file in files_to_check.items():
        if not os.path.exists(target_file):
            if os.path.exists(example_file):
                try:
                    shutil.copy2(example_file, target_file)
                    print(Fore.GREEN + f"[*] {target_file} wurde aus {example_file} erstellt.")
                except Exception as e:
                    print(Fore.RED + f"[!] Fehler beim Erstellen von {target_file}: {e}")

init_config_files()

# --- Importiere den neuen Token-Manager ---
try:
    from token_manager import get_valid_token
except ImportError:
    print("FATALER FEHLER: token_manager.py nicht gefunden.")
    print(f"Aktueller Pfad: {os.getcwd()}")
    print(f"Sys.path: {sys.path}")
    time.sleep(10)
    sys.exit(1)

# --- Pfad-Kontext (WICHTIG für .exe) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# --- i18n Setup ---
try:
    with open('manager_config.json', 'r', encoding='utf-8') as f:
        lang = json.load(f).get('language', 'de')
except (FileNotFoundError, json.JSONDecodeError):
    lang = 'de'

try:
    translation = gettext.translation('messages', localedir='translations', languages=[lang], fallback=True)
    _ = translation.gettext
except FileNotFoundError:
    print(f"WARNUNG: Übersetzungsdateien ('translations') nicht gefunden. Fallback auf Standard-gettext.")
    def _(text):
        return text
# --- Ende i18n ---

init(autoreset=True)

# --- Konstanten ---
CONFIG_FILE = 'config.json'
COMMANDS_FILE = 'commands.json'
SESSION_FILE = 'session.json'
MANAGER_CONFIG_FILE = 'manager_config.json'
SERVER = "irc.chat.twitch.tv"
PORT = 6667
CHAT_LOG_FILE = 'chat.log'

# --- Helper Funktionen ---

def load_config_file(filename):
    """Lädt eine JSON-Konfigurationsdatei sicher."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"{Fore.RED}" + (_("Warnung: %(filename)s nicht gefunden oder fehlerhaft.") % {'filename': filename}))
        return {}

def send_message(sock, channel, message):
    """Sendet eine formatierte PRIVMSG-Nachricht an den Chat."""
    if channel and message:
        print(f"{Fore.MAGENTA}<-- " + _('BOT SENDET') + f": {message}")
        sock.send(f"PRIVMSG #{channel} :{message}\r\n".encode('utf-8'))

def parse_tags(tag_string):
    """Parst die IRCv3-Tags von Twitch."""
    tags = {}
    try:
        if tag_string.startswith('@'):
            tag_string = tag_string[1:]
        
        for tag in tag_string.split(';'):
            key, value = tag.split('=', 1)
            tags[key] = value
    except Exception as e:
        print(f"{Fore.RED}Fehler beim Parsen der Tags: {e} | String: {tag_string}")
    return tags

# --- Aktionen ---

def handle_stream_control(sock, action):
    """Führt Aktionen aus, die die session.json (Streamer) beeinflussen."""
    command = action.get('command')
    print(f"{Fore.YELLOW}" + _('Aktion \'stream_control\' wird ausgeführt') + f": {command}")
    try:
        session_data = load_config_file(SESSION_FILE)
        
        if command == 'skip_track':
            session_data['force_restart'] = True 
        elif command == 'restart_playlist':
            active_playlist_id = session_data.get('active_playlist_id')
            if active_playlist_id:
                playlists_db = load_config_file('playlists.json')
                active_playlist_info = playlists_db.get(active_playlist_id, {})
                filename = active_playlist_info.get('filename')
                if filename and 'playlist_states' in session_data and filename in session_data['playlist_states']:
                    session_data['playlist_states'][filename]['resume_index'] = 0
            session_data['force_restart'] = True
        
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)
            
        print(Fore.YELLOW + (_("Signal '%(command)s' erfolgreich in %(file)s geschrieben.") % {'command': command, 'file': SESSION_FILE}))
        return True
    except Exception as e:
        print(f"{Fore.RED}" + (_("Fehler beim Schreiben der %(file)s: ") % {'file': SESSION_FILE}) + f"{e}")
        return False

def handle_chat_reply(sock, channel, action, context, api_url):
    """Führt Aktionen aus, die eine Chat-Antwort erfordern (ggf. mit API-Daten)."""
    message_template = action.get('message', '')
    print(f"{Fore.YELLOW}" + _('Aktion \'chat_reply\' wird ausgeführt.'))
    na_string = _("N/A")
    
    try:
        # verify=False ist unsicher, aber notwendig für selbstsignierte SSL-Zertifikate
        response = requests.get(api_url, timeout=2, verify=False)
        if response.status_code == 200:
            api_data = response.json()
            message_template = message_template.replace('{now_playing.title}', api_data.get('now_playing', {}).get('title', na_string))
            message_template = message_template.replace('{playlist.name}', api_data.get('playlist', {}).get('name', na_string))
    except requests.RequestException:
        print(f"{Fore.RED}" + (_('Fehler: API unter %(url)s nicht erreichbar.') % {'url': api_url}))
    
    message_template = message_template.replace('{user}', context.get('display-name', ''))
    send_message(sock, channel, message_template)
    return True

# --- Hauptlogik ---

def main():
    bot_config = load_config_file(CONFIG_FILE).get('twitch_bot', {})
    manager_config = load_config_file(MANAGER_CONFIG_FILE)
    
    # --- NEUE TOKEN-LOGIK ---
    BOT_NICK = bot_config.get('bot_nick')
    CHANNEL_NICK = bot_config.get('channel_nick')
    
    bot_token_data = {
        'bot_token': bot_config.get('bot_token'),
        'bot_refresh_token': bot_config.get('bot_refresh_token'),
        'bot_expires_at': bot_config.get('bot_expires_at')
    }
    
    api_config = load_config_file(CONFIG_FILE).get('twitch_api', {})
    client_id = api_config.get('client_id')
    client_secret = api_config.get('client_secret')

    if not all([client_id, client_secret]):
        print(f"{Fore.RED}{_('FEHLER')}: Client-ID/Secret (aus twitch_api) fehlt, um Bot-Token zu verwalten.")
        time.sleep(10)
        return

    BOT_TOKEN = get_valid_token(bot_token_data, client_id, client_secret, 'twitch_bot')
    
    if not all([BOT_NICK, BOT_TOKEN, CHANNEL_NICK]):
        print(f"{Fore.RED}{_('FEHLER')}: " + (_("Bot-Konfiguration in %(file)s unvollständig.") % {'file': CONFIG_FILE}))
        print(f"{Fore.RED}Stelle sicher, dass Bot-Nick, Kanal-Nick und ein Bot-Token (via UI-Button) vorhanden sind.")
        time.sleep(10)
        return
    # --- ENDE NEUE TOKEN-LOGIK ---
        
    # --- FLEXIBLE API URL ---
    host = manager_config.get('host', '127.0.0.1')
    port = manager_config.get('port', 5000)
    protocol = manager_config.get('protocol', 'https') 
    api_url = f"{protocol}://{host}:{port}/api/now_playing"
    print(f"{Fore.CYAN}" + (_("API-Endpunkt wird auf %(url)s erwartet.") % {'url': api_url}))
    # --- ENDE FLEXIBLE API URL ---
    
    commands = load_config_file(COMMANDS_FILE)
    if not commands:
        print(f"{Fore.YELLOW}" + (_("Keine Befehle in %(file)s gefunden. Bot hört nur zu.") % {'file': COMMANDS_FILE}))
    
    command_cooldowns = {cmd: 0 for cmd in commands}

    # --- Verbindungsaufbau ---
    try:
        sock = socket.socket()
        sock.connect((SERVER, PORT))
        sock.send(f"PASS oauth:{BOT_TOKEN}\n".encode('utf-8'))
        sock.send(f"NICK {BOT_NICK}\n".encode('utf-8'))
        sock.send("CAP REQ :twitch.tv/tags\r\n".encode('utf-8'))
        sock.send(f"JOIN #{CHANNEL_NICK}\n".encode('utf-8'))
        print(_("Bot '%(bot_name)s' ist Kanal '#%(channel_name)s' beigetreten.") % {'bot_name': BOT_NICK, 'channel_name': CHANNEL_NICK})
    except socket.error as e:
        print(f"{Fore.RED}FEHLER BEIM VERBINDEN: {e}")
        time.sleep(10)
        return

    buffer = ""
    
    # --- Hauptschleife ---
    while True:
        try:
            buffer += sock.recv(4096).decode('utf-8')
            lines = buffer.split('\r\n')
            buffer = lines.pop()

            for line in lines:
                if not line:
                    continue

                if "PING" in line:
                    sock.send("PONG :tmi.twitch.tv\r\n".encode('utf-8'))
                    continue

                if "PRIVMSG" in line:
                    tag_string, rest = line.split(' ', 1)
                    tags = parse_tags(tag_string)
                    
                    # KORREKTE FORMATIERUNG (FIX FÜR UnboundLocalError)
                    user_info, _sep, message = rest.partition(' :')
                    display_name = tags.get('display-name', '')
                    
                    # --- Chat-Logging ---
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                    log_line = f"[{timestamp}] {display_name}: {message}\n"
                    try:
                        with open(CHAT_LOG_FILE, 'a', encoding='utf-8') as f:
                            f.write(log_line)
                    except Exception as e:
                        print(f"{Fore.RED}Fehler beim Schreiben des Chat-Logs: {e}")
                    
                    print(f"{Fore.GREEN}{display_name}: {Fore.WHITE}{message}")

                    # --- Befehls-Verarbeitung ---
                    for command_name, command_details in commands.items():
                        if message.lower() == command_name:
                            user_is_mod = tags.get('mod') == '1' or tags.get('display-name', '').lower() == CHANNEL_NICK.lower()
                            if command_details.get('permissions') == 'moderator' and not user_is_mod:
                                continue

                            current_time = time.time()
                            if current_time - command_cooldowns.get(command_name, 0) < command_details.get('cooldown', 0):
                                continue
                            
                            action_executed = False
                            action = command_details.get('action', {})
                            
                            if action.get('type') == 'stream_control':
                                action_executed = handle_stream_control(sock, action)
                            elif action.get('type') == 'chat_reply':
                                action_executed = handle_chat_reply(sock, CHANNEL_NICK, action, tags, api_url)
                            
                            if action_executed:
                                command_cooldowns[command_name] = current_time
                                response = command_details.get('response')
                                if response:
                                    send_message(sock, CHANNEL_NICK, response.replace('{user}', tags.get('display-name', '')))
                            break

        except (socket.timeout, ConnectionResetError) as e:
            print(f"{Fore.RED}" + _('Verbindung verloren. Skript wird beendet.') + f" ({e})")
            break
        except Exception as e:
            print(f"{Fore.RED}" + _('Unerwarteter Fehler') + f": {e}")
            traceback.print_exc()
            break
    
    sock.close()
    print("Bot-Prozess beendet.")

if __name__ == "__main__":
    main()