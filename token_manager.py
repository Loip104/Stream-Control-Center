import requests
import json
import os
import time
from colorama import Fore, init
import gettext

# --- i18n Setup ---
try:
    with open('manager_config.json', 'r', encoding='utf-8') as f:
        lang = json.load(f).get('language', 'de')
except (FileNotFoundError, json.JSONDecodeError):
    lang = 'de'

translation = gettext.translation('messages', localedir='translations', languages=[lang], fallback=True)
_ = translation.gettext
init(autoreset=True)
# --- End of Block ---


# --- Konstanten ---
CONFIG_FILE = 'config.json'
TWITCH_TOKEN_URL = 'https://id.twitch.tv/oauth2/token'
# Diese Variable wird nur noch als Fallback genutzt, web_manager.py baut die URI jetzt dynamisch
REDIRECT_URI = 'https://127.0.0.1:5000/twitch/callback'

def save_tokens_to_config(token_data):
    """Liest die config.json, aktualisiert sie mit den neuen Token-Daten und speichert sie."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}

    if 'twitch_api' not in config:
        config['twitch_api'] = {}

    config['twitch_api']['access_token'] = token_data['access_token']
    config['twitch_api']['refresh_token'] = token_data['refresh_token']
    config['twitch_api']['expires_at'] = int(time.time()) + token_data['expires_in']

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        print(_("Tokens erfolgreich in %(file)s gespeichert.") % {'file': CONFIG_FILE})
        return True
    except Exception as e:
        print(Fore.RED + _("FEHLER beim Speichern der Tokens: %(error)s") % {'error': e})
        return False

def exchange_code_for_token(code, client_id, client_secret, redirect_uri):
    """Tauscht einen Autorisierungscode gegen Access- und Refresh-Tokens bei Twitch ein."""
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri
    }
    
    try:
        print(_("Tausche Autorisierungscode gegen Tokens aus..."))
        response = requests.post(TWITCH_TOKEN_URL, data=params)
        response.raise_for_status()
        
        token_data = response.json()
        print(_("Tokens erfolgreich von Twitch erhalten."))
        return token_data

    except requests.exceptions.RequestException as e:
        print(Fore.RED + _("FEHLER bei der Kommunikation mit der Twitch API: %(error)s") % {'error': e})
        if e.response is not None:
            print(Fore.RED + _("Antwort von Twitch: %(response)s") % {'response': e.response.text})
        return None

def refresh_access_token(refresh_token, client_id, client_secret):
    """Erneuert einen abgelaufenen Access-Token mithilfe des Refresh-Tokens."""
    params = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret
    }
    try:
        print(_("Access-Token ist abgelaufen. Erneuere Token..."))
        response = requests.post(TWITCH_TOKEN_URL, data=params)
        response.raise_for_status()
        
        new_token_data = response.json()
        print(Fore.GREEN + _("Token erfolgreich erneuert."))
        return new_token_data

    except requests.exceptions.RequestException as e:
        print(Fore.RED + _("FEHLER: Konnte den Access-Token nicht erneuern."))
        if e.response is not None:
            print(Fore.RED + _("Antwort von Twitch: %(response)s") % {'response': e.response.text})
        return None

def get_valid_token():
    """
    Die zentrale Funktion, um einen gültigen Access-Token zu erhalten.
    Prüft, ob der Token noch gültig ist, erneuert ihn bei Bedarf und gibt ihn zurück.
    """
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(Fore.RED + _("FEHLER: Konnte %(file)s nicht laden, um Token zu prüfen.") % {'file': CONFIG_FILE})
        return None

    twitch_api_config = config.get('twitch_api', {})
    access_token = twitch_api_config.get('access_token')
    refresh_token = twitch_api_config.get('refresh_token')
    expires_at = twitch_api_config.get('expires_at')
    client_id = twitch_api_config.get('client_id')
    client_secret = twitch_api_config.get('client_secret')

    if not all([access_token, refresh_token, expires_at, client_id, client_secret]):
        print(Fore.RED + _("FEHLER: Unvollständige Token-Informationen in der Konfiguration."))
        return None

    # Prüfe, ob der Token in den nächsten 10 Minuten (600 Sekunden) abläuft
    if expires_at < (int(time.time()) + 600):
        new_tokens = refresh_access_token(refresh_token, client_id, client_secret)
        if new_tokens:
            if save_tokens_to_config(new_tokens):
                return new_tokens.get('access_token')
            else:
                return None # Fehler beim Speichern
        else:
            print(Fore.RED + _("KRITISCH: Token-Erneuerung fehlgeschlagen. Bitte verbinde die Anwendung im Web-UI erneut mit Twitch."))
            return None # Fehler beim Erneuern
    else:
        print(_("Access-Token ist noch gültig."))
        return access_token