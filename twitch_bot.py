# twitch_bot.py (Version 3.1 - Flexible API-URL)
import socket
import json
import time
import requests
from colorama import Fore, init

init(autoreset=True)

# --- Konstanten ---
CONFIG_FILE = 'config.json'
COMMANDS_FILE = 'commands.json'
SESSION_FILE = 'session.json'
MANAGER_CONFIG_FILE = 'manager_config.json' # Neu
SERVER = "irc.chat.twitch.tv"
PORT = 6667

# --- Helfer-Funktionen ---
def load_config_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"{Fore.RED}Warnung: {filename} nicht gefunden oder fehlerhaft.")
        return {}

def send_message(sock, message):
    channel = load_config_file(CONFIG_FILE).get('twitch_bot', {}).get('channel_nick')
    if channel and message:
        print(f"{Fore.MAGENTA}<-- BOT SENDET: {message}")
        sock.send(f"PRIVMSG #{channel} :{message}\r\n".encode('utf-8'))

def parse_tags(tag_string):
    tags = {}
    for tag in tag_string.split(';'):
        key, value = tag.split('=', 1)
        tags[key] = value
    return tags

# --- Aktionen ---
def handle_stream_control(sock, action):
    # ... (Diese Funktion bleibt unverändert) ...
    command = action.get('command')
    print(f"{Fore.YELLOW}Aktion 'stream_control' wird ausgeführt: {command}")
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
        print(f"{Fore.YELLOW}Signal '{command}' erfolgreich in {SESSION_FILE} geschrieben.")
        return True
    except Exception as e:
        print(f"{Fore.RED}Fehler beim Schreiben der {SESSION_FILE}: {e}")
        return False

def handle_chat_reply(sock, action, context, api_url): # Nimmt jetzt api_url als Argument
    message_template = action.get('message', '')
    print(f"{Fore.YELLOW}Aktion 'chat_reply' wird ausgeführt.")
    try:
        response = requests.get(api_url, timeout=2) # Verwendet die dynamische URL
        if response.status_code == 200:
            api_data = response.json()
            message_template = message_template.replace('{now_playing.title}', api_data.get('now_playing', {}).get('title', 'N/A'))
            message_template = message_template.replace('{playlist.name}', api_data.get('playlist', {}).get('name', 'N/A'))
    except requests.RequestException:
        print(f"{Fore.RED}Fehler: API unter {api_url} nicht erreichbar.")
    message_template = message_template.replace('{user}', context.get('display-name', ''))
    send_message(sock, message_template)
    return True

# --- Hauptlogik ---
def main():
    bot_config = load_config_file(CONFIG_FILE).get('twitch_bot', {})
    manager_config = load_config_file(MANAGER_CONFIG_FILE)
    
    if not all(k in bot_config for k in ['bot_nick', 'bot_token', 'channel_nick']):
        print(f"{Fore.RED}FEHLER: Bot-Konfiguration in {CONFIG_FILE} unvollständig.")
        time.sleep(10)
        return
        
    port = manager_config.get('port', 5000)
    api_url = f"http://127.0.0.1:{port}/api/now_playing"
    print(f"{Fore.CYAN}API-Endpunkt wird auf {api_url} erwartet.")
    
    commands = load_config_file(COMMANDS_FILE)
    if not commands:
        print(f"{Fore.YELLOW}Keine Befehle in {COMMANDS_FILE} gefunden. Bot hört nur zu.")
    
    command_cooldowns = {cmd: 0 for cmd in commands}

    sock = socket.socket()
    sock.connect((SERVER, PORT))
    sock.send(f"PASS {bot_config['bot_token']}\n".encode('utf-8'))
    sock.send(f"NICK {bot_config['bot_nick']}\n".encode('utf-8'))
    sock.send("CAP REQ :twitch.tv/tags\r\n".encode('utf-8'))
    sock.send(f"JOIN #{bot_config['channel_nick']}\n".encode('utf-8'))
    print(f"Bot '{bot_config['bot_nick']}' ist Kanal '#{bot_config['channel_nick']}' beigetreten.")

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
            print(f"{Fore.RED}Verbindung verloren. Skript wird beendet.")
            break
        except Exception as e:
            print(f"{Fore.RED}Unerwarteter Fehler: {e}")
            break

if __name__ == "__main__":
    main()