# token_manager.py
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

try:
    translation = gettext.translation('messages', localedir='translations', languages=[lang], fallback=True)
    _ = translation.gettext
except FileNotFoundError:
    print("WARNUNG: Übersetzungsdateien nicht gefunden. Fallback auf Standard-gettext.")
    # Fallback, damit das Skript nicht abstürzt
    def _(text):
        return text
# --- Ende i18n ---

init(autoreset=True)

# --- Konstanten ---
CONFIG_FILE = 'config.json'
TWITCH_TOKEN_URL = 'https://id.twitch.tv/oauth2/token'

def save_tokens_to_config(token_data, config_key='twitch_api'):
    """
    Liest die config.json, aktualisiert sie mit den neuen Token-Daten 
    unter dem angegebenen Schlüssel (z.B. 'twitch_api' or 'twitch_bot') und speichert sie.
    """
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}

    if config_key not in config:
        config[config_key] = {}

    # Passe die Schlüsselnamen basierend auf dem config_key an
    if config_key == 'twitch_bot':
        config[config_key]['bot_token'] = token_data['access_token']
        config[config_key]['bot_refresh_token'] = token_data['refresh_token']
        config[config_key]['bot_expires_at'] = int(time.time()) + token_data['expires_in']
    else: # Standard 'twitch_api'
        config[config_key]['access_token'] = token_data['access_token']
        config[config_key]['refresh_token'] = token_data['refresh_token']
        config[config_key]['expires_at'] = int(time.time()) + token_data['expires_in']

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        # KORREKTE FORMATIERUNG
        print((_("Tokens erfolgreich in %(file)s gespeichert.") % {'file': CONFIG_FILE}) + f" (Key: {config_key})")
        return True
    except Exception as e:
        # KORREKTE FORMATIERUNG
        print(f"{Fore.RED}" + (_("FEHLER beim Speichern der Tokens: %(error)s") % {'error': e}))
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
        # KORREKTE FORMATIERUNG
        print(f"{Fore.RED}" + (_("FEHLER bei der Kommunikation mit der Twitch API: %(error)s") % {'error': e}))
        if e.response is not None:
            # KORREKTE FORMATIERUNG
            print(f"{Fore.RED}" + (_("Antwort von Twitch: %(response)s") % {'response': e.response.text}))
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
            # KORREKTE FORMATIERUNG
            print(f"{Fore.RED}" + (_("Antwort von Twitch: %(response)s") % {'response': e.response.text}))
        return None

def get_valid_token(token_data, client_id, client_secret, config_key='twitch_api'):
    """
    Die zentrale Funktion, um einen gültigen Access-Token zu erhalten.
    Prüft, ob der Token noch gültig ist, erneuert ihn bei Bedarf und gibt ihn zurück.
    Nimmt jetzt die Token-Daten als Argumente entgegen.
    """
    
    # Passe die Schlüsselnamen basierend auf dem config_key an
    if config_key == 'twitch_bot':
        access_token = token_data.get('bot_token')
        refresh_token = token_data.get('bot_refresh_token')
        expires_at = token_data.get('bot_expires_at')
    else: # Standard 'twitch_api'
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_at = token_data.get('expires_at')


    if not all([access_token, refresh_token, expires_at, client_id, client_secret]):
        print(Fore.RED + _("FEHLER: Unvollständige Token-Informationen in der Konfiguration."))
        return None

    # Prüfe, ob der Token in den nächsten 10 Minuten (600 Sekunden) abläuft
    if expires_at < (int(time.time()) + 600):
        new_tokens = refresh_access_token(refresh_token, client_id, client_secret)
        if new_tokens:
            # Speichere die neuen Tokens unter dem korrekten Schlüssel (twitch_api oder twitch_bot)
            if save_tokens_to_config(new_tokens, config_key):
                return new_tokens.get('access_token')
            else:
                return None # Fehler beim Speichern
        else:
            print(Fore.RED + _("KRITISCH: Token-Erneuerung fehlgeschlagen. Bitte verbinde die Anwendung im Web-UI erneut mit Twitch."))
            return None # Fehler beim Erneuern
    else:
        print(_("Access-Token ist noch gültig."))
        return access_token