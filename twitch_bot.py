# twitch_bot.py (Version 3.1 - Flexible API-URL)
import socket
import json
import time
import requests
from colorama import Fore, init
import gettext

# --- i18n Setup Block (Already correct) ---
try:
    with open('manager_config.json', 'r', encoding='utf-8') as f:
        lang = json.load(f).get('language', 'de')
except (FileNotFoundError, json.JSONDecodeError):
    lang = 'de'

translation = gettext.translation('messages', localedir='translations', languages=[lang], fallback=True)
_ = translation.gettext
# --- End of Block ---

init(autoreset=True)

# --- Constants ---
CONFIG_FILE = 'config.json'
COMMANDS_FILE = 'commands.json'
SESSION_FILE = 'session.json'
MANAGER_CONFIG_FILE = 'manager_config.json' # New
SERVER = "irc.chat.twitch.tv"
PORT = 6667

# --- Helper Functions ---
def load_config_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"{Fore.RED}" + _("Warnung: %(filename)s nicht gefunden oder fehlerhaft.", filename=filename))
        return {}

def send_message(sock, message):
    channel = load_config_file(CONFIG_FILE).get('twitch_bot', {}).get('channel_nick')
    if channel and message:
        print(f"{Fore.MAGENTA}<-- {_('BOT SENDET')}: {message}")
        sock.send(f"PRIVMSG #{channel} :{message}\r\n".encode('utf-8'))

def parse_tags(tag_string):
    tags = {}
    for tag in tag_string.split(';'):
        key, value = tag.split('=', 1)
        tags[key] = value
    return tags

# --- Actions ---
def handle_stream_control(sock, action):
    # ... (This function remains unchanged) ...
    command = action.get('command')
    print(f"{Fore.YELLOW}{_('Aktion \'stream_control\' wird ausgeführt')}: {command}")
    try:
        with open(SESSION_FILE, 'r+', encoding='utf-8') as f:
            session_data = json.load(f)
            if command == 'skip_track':
                session_data['force_restart'] = True
            elif command == 'restart_playlist':
                active_playlist_id = session_data.get('active_playlist_id')
                if active_playlist_id:
                    playlists_db = load_config_file('playlists.json')
                    active_playlist_info = playlists_db.get(active_playlist_id)
                    if active_playlist_info:
                        filename = active_playlist_info['filename']
                        if 'playlist_states' in session_data and filename in session_data['playlist_states']:
                            session_data['playlist_states'][filename]['resume_index'] = 0
                session_data['force_restart'] = True
            f.seek(0)
            json.dump(session_data, f, indent=2)
            f.truncate()
        print(Fore.YELLOW + _("Signal '%(command)s' erfolgreich in %(file)s geschrieben.", command=command, file=SESSION_FILE))
        return True
    except Exception as e:
        print(f"{Fore.RED}" + _("Fehler beim Schreiben der %(file)s: ", file=SESSION_FILE) + f"{e}")
        return False

def handle_chat_reply(sock, action, context, api_url): # Takes api_url as an argument
    message_template = action.get('message', '')
    print(f"{Fore.YELLOW}{_('Aktion \'chat_reply\' wird ausgeführt.')}")
    na_string = _("N/A") # Translatable fallback value
    try:
        response = requests.get(api_url, timeout=2) # Uses the dynamic URL
        if response.status_code == 200:
            api_data = response.json()
            message_template = message_template.replace('{now_playing.title}', api_data.get('now_playing', {}).get('title', na_string))
            message_template = message_template.replace('{playlist.name}', api_data.get('playlist', {}).get('name', na_string))
    except requests.RequestException:
        print(f"{Fore.RED}{_('Fehler: API unter %(url)s nicht erreichbar.', url=api_url)}")
    message_template = message_template.replace('{user}', context.get('display-name', ''))
    send_message(sock, message_template)
    return True

# --- Hauptlogik ---
def main():
    bot_config = load_config_file(CONFIG_FILE).get('twitch_bot', {})
    manager_config = load_config_file(MANAGER_CONFIG_FILE)
    
    if not all(k in bot_config for k in ['bot_nick', 'bot_token', 'channel_nick']):
        print(f"{Fore.RED}{_('FEHLER')}: " + _("Bot-Konfiguration in %(file)s unvollständig.", file=CONFIG_FILE))
        time.sleep(10)
        return
        
    port = manager_config.get('port', 5000)
    api_url = f"http://127.0.0.1:{port}/api/now_playing"
    print(f"{Fore.CYAN}" + _("API-Endpunkt wird auf %(url)s erwartet.", url=api_url))
    
    commands = load_config_file(COMMANDS_FILE)
    if not commands:
        print(f"{Fore.YELLOW}" + _("Keine Befehle in %(file)s gefunden. Bot hört nur zu.", file=COMMANDS_FILE))
    
    command_cooldowns = {cmd: 0 for cmd in commands}

    sock = socket.socket()
    sock.connect((SERVER, PORT))
    sock.send(f"PASS {bot_config['bot_token']}\n".encode('utf-8'))
    sock.send(f"NICK {bot_config['bot_nick']}\n".encode('utf-8'))
    sock.send("CAP REQ :twitch.tv/tags\r\n".encode('utf-8'))
    sock.send(f"JOIN #{bot_config['channel_nick']}\n".encode('utf-8'))
    print(_("Bot '%(bot_name)s' ist Kanal '#%(channel_name)s' beigetreten.", bot_name=bot_config['bot_nick'], channel_name=bot_config['channel_nick']))

    buffer = ""
    while True:
        try:
            buffer += sock.recv(4096).decode('utf-8')
            lines = buffer.split('\r\n')
            buffer = lines.pop()

            for line in lines:
                if "PING" in line:
                    sock.send("PONG :tmi.twitch.tv\r\n".encode('utf-8'))
                    continue

                if "PRIVMSG" in line:
                    tag_string, rest = line.split(' ', 1)
                    tags = parse_tags(tag_string[1:])
                    
                    user_info, _, message = rest.partition(' :')
                    display_name = tags.get('display-name', '')
                    
                    # Chat-Logging
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                    log_line = f"[{timestamp}] {display_name}: {message}\n"
                    with open('chat.log', 'a', encoding='utf-8') as f:
                        f.write(log_line)
                    
                    # This line logs the raw chat message; it should not be translated.
                    print(f"{Fore.GREEN}{display_name}: {Fore.WHITE}{message}")

                    # Befehls-Verarbeitung
                    for command_name, command_details in commands.items():
                        if message.lower() == command_name:
                            user_is_mod = tags.get('mod') == '1' or tags.get('display-name', '').lower() == bot_config['channel_nick'].lower()
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
                                action_executed = handle_chat_reply(sock, action, tags, api_url)
                            
                            if action_executed:
                                command_cooldowns[command_name] = current_time
                                response = command_details.get('response')
                                if response:
                                    send_message(sock, response.replace('{user}', tags.get('display-name', '')))
                            break

        except (socket.timeout, ConnectionResetError):
            print(f"{Fore.RED}{_('Verbindung verloren. Skript wird beendet.')}")
            break
        except Exception as e:
            print(f"{Fore.RED}{_('Unerwarteter Fehler')}: {e}")
            break

if __name__ == "__main__":
    main()