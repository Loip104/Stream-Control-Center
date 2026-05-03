# module: Twitch
import requests
import json
import urllib.parse
from colorama import Fore
import time
from flask import request, redirect, url_for, flash

MODULE_ID = "twitch"
MODULE_NAME = "Twitch"

def get_ui_html(config):
    """Gibt das HTML-Snippet für den Tab 'Plattformen' zurück."""
    twitch_cfg = config.get('modules', {}).get(MODULE_ID, {})
    
    # Rückwärtskompatibilität: Falls noch die alte 'twitch_api' Konfiguration existiert
    if not twitch_cfg and 'twitch_api' in config:
         twitch_cfg = config['twitch_api']
         
    client_id = twitch_cfg.get('client_id', '')
    client_secret = twitch_cfg.get('client_secret', '')
    access_token = twitch_cfg.get('access_token', '')
    enabled = twitch_cfg.get('enabled', True) # Standardmäßig an
    
    # Hier nutzen wir doppelte Klammern {{ }} um Jinja-Variablen im generierten String zu schützen
    # oder verarbeiten sie direkt. 
    # WICHTIG: Da Pybabel auf dem Frontend angewendet wird, nutzen wir die Standard Jinja-Tags.
    html = f"""
    <div class="settings-group">
        <h3><i class="fab fa-twitch" style="color: #9146FF; margin-right: 10px;"></i> {MODULE_NAME} {{{{ _('Anbindung') }}}}</h3>
        <p style="font-size: 12px; color: #666; margin-top: -10px;">{{{{ _('Aktualisiert Spieletitel und Kategorie automatisch auf Twitch.') }}}}</p>
        
        <label>
            <input type="checkbox" name="module_{MODULE_ID}_enabled" {'checked' if enabled else ''}>
            {{{{ _('{MODULE_NAME}-Modul aktivieren') }}}}
        </label>
        <br><br>

        <a href="{{{{ url_for('connect_{MODULE_ID}') }}}}" class="cta-button" style="width: 100%; text-align: center; box-sizing: border-box; margin-bottom: 15px; background-color: #9146FF; color: white;">
            {{{{ _('Mit {MODULE_NAME} verbinden') if "{access_token}" == "" else _('Erneut mit {MODULE_NAME} verbinden') }}}}
        </a>
        
        <div style="margin-bottom: 15px;">
            <label>{{{{ _('Status:') }}}}</label>
            <div style="display: flex; align-items: center; gap: 10px; margin-top: 5px;">
                <div class="status-indicator">
                    <div class="status-light {'status-online' if access_token else 'status-offline'}"></div>
                    <span>{{{{ _('Verbunden') if "{access_token}" != "" else _('Nicht verbunden') }}}}</span>
                </div>
            </div>
        </div>

        <label for="module_{MODULE_ID}_client_id">{{{{ _('Twitch Client ID (App):') }}}}</label>
        <input type="text" id="module_{MODULE_ID}_client_id" name="module_{MODULE_ID}_client_id" value="{client_id}">
        
        <label for="module_{MODULE_ID}_client_secret">{{{{ _('Twitch Client Secret:') }}}}</label>
        <input type="password" id="module_{MODULE_ID}_client_secret" name="module_{MODULE_ID}_client_secret" value="{client_secret}">
        
        <small class="form-text text-muted" style="display: block; margin-top: 10px;">{{{{ _('Wichtig: Speichere die Einstellungen, bevor du auf "Verbinden" klickst!') }}}}</small>
    </div>
    """
    return html

def register_routes(app, flash_func, config_path):
    """Registriert alle OAuth-Routen für dieses Modul."""
    
    @app.route(f'/connect_{MODULE_ID}')
    def connect_twitch():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = json.load(f)
        except Exception:
            c = {}
        
        cfg = c.get('modules', {}).get(MODULE_ID, c.get('twitch_api', {}))
        client_id = cfg.get('client_id')
        if not client_id:
            flash_func("Bitte erst eine Twitch Client-ID speichern!", "error")
            return redirect(url_for('index', active_tab='platforms'))
            
        # Port aus manager_config.json lesen
        try:
            with open('manager_config.json', 'r', encoding='utf-8') as f:
                m_cfg = json.load(f)
            port = m_cfg.get('port', 5055)
        except Exception:
            port = 5055

        redirect_uri = f"https://127.0.0.1:{port}/twitch/callback"
        scopes = "channel:manage:broadcast channel:read:subscriptions chat:read chat:edit user:read:email"
        auth_url = f"https://id.twitch.tv/oauth2/authorize?client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}&response_type=code&scope={urllib.parse.quote(scopes)}"
        return redirect(auth_url)

    @app.route(f'/twitch/callback')
    def twitch_oauth_callback():
        code = request.args.get('code')
        if not code:
            flash_func("Kein Autorisierungscode von Twitch erhalten.", "error")
            return redirect(url_for('index', active_tab='platforms'))

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = json.load(f)
        except Exception:
            c = {}
            
        # Port aus manager_config.json lesen
        try:
            with open('manager_config.json', 'r', encoding='utf-8') as f:
                m_cfg = json.load(f)
            port = m_cfg.get('port', 5055)
        except Exception:
            port = 5055

        cfg = c.get('modules', {}).get(MODULE_ID, c.get('twitch_api', {}))
        client_id = cfg.get('client_id')
        client_secret = cfg.get('client_secret')
        redirect_uri = f"https://127.0.0.1:{port}/twitch/callback"

        token_url = "https://id.twitch.tv/oauth2/token"
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }

        try:
            response = requests.post(token_url, data=payload)
            response.raise_for_status()
            token_data = response.json()
            
            cfg['access_token'] = token_data.get('access_token')
            cfg['refresh_token'] = token_data.get('refresh_token')
            cfg['expires_at'] = int(time.time()) + token_data.get('expires_in', 0)
            
            # Hole Kanalnamen und Broadcaster-ID
            headers = {
                'Client-ID': client_id,
                'Authorization': f"Bearer {cfg['access_token']}"
            }
            user_resp = requests.get('https://api.twitch.tv/helix/users', headers=headers)
            user_resp.raise_for_status()
            user_data = user_resp.json()
            if user_data.get('data'):
                cfg['channel_name'] = user_data['data'][0]['login']
                cfg['broadcaster_id'] = user_data['data'][0]['id']
                
            if 'modules' not in c: c['modules'] = {}
            c['modules'][MODULE_ID] = cfg
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(c, f, indent=2)

            flash_func("Erfolgreich mit Twitch verbunden!", "success")
        except Exception as e:
            flash_func(f"Fehler bei der Twitch-Verbindung: {e}", "error")

        return redirect(url_for('index', active_tab='platforms'))

# --- Interne Logik für stream_v3.py (ohne Flask Kontext) ---

def _refresh_token(client_id, client_secret, refresh_token, translate):
    params = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret
    }
    try:
        response = requests.post('https://id.twitch.tv/oauth2/token', data=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        error_info = str(e)
        if e.response is not None:
            try:
                error_info += f" | API: {json.dumps(e.response.json())}"
            except Exception:
                error_info += f" | API: {e.response.text}"
        print(Fore.RED + translate("[Twitch] Fehler beim Erneuern des Tokens: %(error)s") % {'error': error_info})
        return None

def _get_valid_token(config, translate):
    cfg = config.get('modules', {}).get(MODULE_ID, config.get('twitch_api', {}))
    access_token = cfg.get('access_token')
    refresh_token = cfg.get('refresh_token')
    expires_at = cfg.get('expires_at', 0)
    client_id = cfg.get('client_id')
    client_secret = cfg.get('client_secret')

    if not all([access_token, refresh_token, client_id, client_secret]):
        return None

    if expires_at < (int(time.time()) + 600):
        new_tokens = _refresh_token(client_id, client_secret, refresh_token, translate)
        if new_tokens:
            cfg['access_token'] = new_tokens['access_token']
            cfg['refresh_token'] = new_tokens['refresh_token']
            cfg['expires_at'] = int(time.time()) + new_tokens['expires_in']
            # Speichern
            try:
                with open('config.json', 'r', encoding='utf-8') as f: full_cfg = json.load(f)
                if 'modules' not in full_cfg: full_cfg['modules'] = {}
                full_cfg['modules'][MODULE_ID] = cfg
                with open('config.json', 'w', encoding='utf-8') as f: json.dump(full_cfg, f, indent=2)
            except Exception: pass
            return cfg['access_token']
        return None
    return access_token

def _get_game_id(game_name, config, translate):
    cfg = config.get('modules', {}).get(MODULE_ID, config.get('twitch_api', {}))
    valid_token = _get_valid_token(config, translate)
    if not valid_token: return None

    headers = {'Client-ID': cfg.get('client_id'), 'Authorization': f"Bearer {valid_token}"}
    params = {'name': game_name}
    try:
        response = requests.get('https://api.twitch.tv/helix/games', headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('data'):
            return data['data'][0]['id']
        else:
             print(Fore.YELLOW + translate("[Twitch] Warnung: Spiel '%(game)s' nicht gefunden.") % {'game': game_name})
             return None
    except Exception as e:
        return None

def update_stream_info(config, title, game_name, language, translate):
    """
    Wird vom stream_v3 aufgerufen. Aktualisiert die Metadaten.
    """
    cfg = config.get('modules', {}).get(MODULE_ID, config.get('twitch_api', {}))
    if not cfg.get('enabled', True):
        return

    broadcaster_id = cfg.get('broadcaster_id')
    if not broadcaster_id:
        print(Fore.RED + translate("[Twitch] Fehler: Keine Broadcaster-ID. Bitte neu verbinden im Web-UI."))
        return

    valid_token = _get_valid_token(config, translate)
    if not valid_token:
        print(Fore.RED + translate("[Twitch] Fehler: Konnte keinen gültigen Token erhalten."))
        return

    print(Fore.MAGENTA + translate("[Twitch] Aktualisiere Metadaten -> Titel: %(title)s | Spiel: %(game)s") % {'title': title, 'game': game_name})

    headers = {
        'Client-ID': cfg.get('client_id'), 
        'Authorization': f"Bearer {valid_token}",
        'Content-Type': 'application/json'
    }

    body = {'title': title, 'broadcaster_language': language}
    game_id = _get_game_id(game_name, config, translate)
    if game_id: body['game_id'] = game_id

    try:
        url = f'https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}'
        requests.patch(url, headers=headers, json=body, timeout=10).raise_for_status()
    except requests.exceptions.RequestException as e:
        print(Fore.RED + translate("[Twitch] Fehler beim Aktualisieren der Stream-Info: %(error)s") % {'error': e})
