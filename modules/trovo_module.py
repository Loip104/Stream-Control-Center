import requests
import json
import urllib.parse
import time
import os
from flask import redirect, url_for, request
from colorama import Fore

# Modul-Metadaten
MODULE_ID = "trovo"
MODULE_NAME = "Trovo"

def get_ui_html(CONFIG):
    """
    Liefert das HTML-Snippet für das Web-Interface.
    """
    mod_config = CONFIG.get('modules', {}).get(MODULE_ID, {})
    client_id = mod_config.get('client_id', '')
    client_secret_exists = bool(mod_config.get('client_secret'))
    access_token = mod_config.get('access_token', '')
    enabled = mod_config.get('enabled', False)
    
    # Port aus manager_config.json lesen
    try:
        with open('manager_config.json', 'r', encoding='utf-8') as f:
            m_cfg = json.load(f)
        port = m_cfg.get('port', 5055)
    except Exception:
        port = 5055

    placeholder_text = '••••••••••••••••' if client_secret_exists else "{{ _('Wird zum Einrichten oder Ändern benötigt') }}"
    
    status_text = "{{ _('Verbunden') }}" if access_token else "{{ _('Nicht verbunden') }}"
    button_text = "{{ _('Erneut mit Trovo verbinden') }}" if access_token else "{{ _('Mit Trovo verbinden') }}"

    html = f"""
    <div class="settings-group">
        <h3><i class="fas fa-video" style="color: #19d66b; margin-right: 10px;"></i> {{{{ _('Trovo Live API') }}}}</h3>
        <p style="font-size: 12px; color: #666; margin-top: -10px;">{{{{ _('Für die automatische Aktualisierung von Trovo Live-Streams (Titel und Kategorie).') }}}}</p>
        
        <label>
            <input type="checkbox" name="module_{MODULE_ID}_enabled" {'checked' if enabled else ''}>
            {{{{ _('Trovo Integration aktivieren') }}}}
        </label>
        <br><br>

        <a href="{{{{ url_for('connect_{MODULE_ID}') }}}}" class="cta-button" style="width: 100%; text-align: center; box-sizing: border-box; margin-bottom: 15px; background-color: #19d66b; color: white;">
            {button_text}
        </a>
        
        <div style="margin-bottom: 15px;">
            <label>{{{{ _('Status:') }}}}</label>
            <div style="display: flex; align-items: center; gap: 10px; margin-top: 5px;">
                <div class="status-indicator">
                    <div class="status-light {'status-online' if access_token else 'status-offline'}"></div>
                    <span>{status_text}</span>
                </div>
            </div>
        </div>

        <div class="settings-grid" style="grid-template-columns: 1fr 1fr; gap: 15px;">
            <div>
                <label>{{{{ _('Trovo Client-ID:') }}}}</label>
                <input type="text" name="module_{MODULE_ID}_client_id" value="{client_id}" placeholder="Client-ID von developer.trovo.live">
            </div>
            <div>
                <label>{{{{ _('Trovo Client Secret:') }}}}</label>
                <input type="password" name="module_{MODULE_ID}_client_secret" placeholder="{placeholder_text}">
            </div>
        </div>

        <div style="margin-top: 15px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 5px; font-size: 13px;">
            <strong>{{{{ _('Anleitung:') }}}}</strong>
            <ol style="margin-top: 5px; padding-left: 20px;">
                <li>{{{{ _('Gehe zum') }}}} <a href="https://developer.trovo.live/" target="_blank">Trovo Developer Portal</a>.</li>
                <li>{{{{ _('Erstelle eine neue App (als "Web" Typ).') }}}}</li>
                <li>{{{{ _('Trage unter **Redirect URI** folgendes ein:') }}}}<br>
                    <code style="background: #111; padding: 3px; border-radius: 3px; user-select: all;">https://127.0.0.1:{port}/trovo_oauth_callback</code></li>
                <li>{{{{ _('Kopiere Client-ID und Secret hier hinein und speichere ganz unten.') }}}}</li>
                <li>{{{{ _('Klicke danach auf den grünen Button oben, um dich zu verbinden.') }}}}</li>
            </ol>
        </div>
    </div>
    """
    return html

def register_routes(app, flash_func, config_path):
    """
    Registriert alle OAuth-Routen für dieses Modul.
    """
    @app.route(f'/connect_{MODULE_ID}')
    def connect_trovo():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = json.load(f)
        except Exception:
            c = {}
        
        cfg = c.get('modules', {}).get(MODULE_ID, {})
        client_id = cfg.get('client_id')
        if not client_id:
            flash_func("Bitte erst eine Trovo Client-ID speichern!", "error")
            return redirect(url_for('index', _anchor='platforms'))
            
        # Port aus manager_config.json lesen
        try:
            with open('manager_config.json', 'r', encoding='utf-8') as f:
                m_cfg = json.load(f)
            port = m_cfg.get('port', 5055)
        except Exception:
            port = 5055

        redirect_uri = f"https://127.0.0.1:{port}/trovo_oauth_callback"
        scopes = "channel_update_self user_details_self"
        state = "trovo_state" # Einfacher State
        
        auth_url = (f"https://open.trovo.live/page/login.html?"
                    f"client_id={urllib.parse.quote(client_id)}&"
                    f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
                    f"response_type=code&"
                    f"scope={urllib.parse.quote(scopes)}&"
                    f"state={state}")
                    
        return redirect(auth_url)

    @app.route('/trovo_oauth_callback')
    def trovo_oauth_callback():
        code = request.args.get('code')
        if not code:
            flash_func("Kein Autorisierungscode von Trovo erhalten.", "error")
            return redirect(url_for('index', _anchor='platforms'))

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

        cfg = c.get('modules', {}).get(MODULE_ID, {})
        client_id = cfg.get('client_id')
        client_secret = cfg.get('client_secret')
        redirect_uri = f"https://127.0.0.1:{port}/trovo_oauth_callback"

        # 1. Access Token abrufen
        token_url = "https://open-api.trovo.live/openplatform/exchangetoken"
        payload = {
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri
        }
        # Trovo erwartet client-id Header
        headers = {
            "Accept": "application/json",
            "client-id": client_id,
            "Content-Type": "application/json"
        }
        
        try:
            resp = requests.post(token_url, headers=headers, json=payload)
            resp.raise_for_status()
            token_data = resp.json()
            
            # 2. Channel ID abrufen (wird für Updates benötigt)
            access_token = token_data.get('access_token')
            user_info_url = "https://open-api.trovo.live/openplatform/getuserinfo"
            user_headers = {
                "Accept": "application/json",
                "client-id": client_id,
                "Authorization": f"OAuth {access_token}"
            }
            user_resp = requests.get(user_info_url, headers=user_headers)
            user_data = user_resp.json()
            channel_id = user_data.get('channelId')

            # 3. In Config speichern
            if 'modules' not in c: c['modules'] = {}
            if MODULE_ID not in c['modules']: c['modules'][MODULE_ID] = {}
            
            c['modules'][MODULE_ID]['access_token'] = access_token
            c['modules'][MODULE_ID]['refresh_token'] = token_data.get('refresh_token')
            c['modules'][MODULE_ID]['expires_at'] = int(time.time()) + token_data.get('expires_in', 3600)
            c['modules'][MODULE_ID]['channel_id'] = channel_id
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(c, f, indent=2)
                
            flash_func("Erfolgreich mit Trovo verbunden!", "success")
        except Exception as e:
            flash_func(f"Fehler bei Trovo-Verbindung: {e}", "error")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Trovo API Error: {e.response.text}")

        return redirect(url_for('index', _anchor='platforms'))

def _get_category_id(client_id, game_name):
    """Sucht nach der Trovo Category ID für einen Spielnamen."""
    if not game_name: return None
    
    url = "https://open-api.trovo.live/openplatform/categorys/search"
    headers = {
        "Accept": "application/json",
        "client-id": client_id,
        "Content-Type": "application/json"
    }
    payload = {"query": game_name}
    
    try:
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        categories = data.get('category_info', [])
        if categories:
            # Wir nehmen den ersten Match
            return categories[0].get('id')
    except Exception as e:
        print(f"[Trovo] Fehler bei Kategorie-Suche: {e}")
    return None

def _get_valid_token(mod_config, translate):
    """Erneuert den Trovo-Token falls abgelaufen."""
    access_token = mod_config.get('access_token')
    refresh_token = mod_config.get('refresh_token')
    expires_at = mod_config.get('expires_at', 0)
    client_id = mod_config.get('client_id')
    client_secret = mod_config.get('client_secret')

    if not all([access_token, refresh_token, client_id, client_secret]):
        return None

    # Falls Token in < 5 Min abläuft
    if expires_at < (int(time.time()) + 300):
        try:
            url = "https://open-api.trovo.live/openplatform/refreshtoken"
            headers = {
                "Accept": "application/json",
                "client-id": client_id,
                "Content-Type": "application/json"
            }
            payload = {
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            }
            resp = requests.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            new_access = data.get('access_token')
            new_refresh = data.get('refresh_token')
            new_expires = int(time.time()) + data.get('expires_in', 3600)
            
            # In config.json speichern (via Reload-Save Pattern)
            if os.path.exists('config.json'):
                try:
                    with open('config.json', 'r', encoding='utf-8') as f:
                        c = json.load(f)
                    if 'modules' not in c: c['modules'] = {}
                    if MODULE_ID not in c['modules']: c['modules'][MODULE_ID] = {}
                    c['modules'][MODULE_ID]['access_token'] = new_access
                    c['modules'][MODULE_ID]['refresh_token'] = new_refresh
                    c['modules'][MODULE_ID]['expires_at'] = new_expires
                    with open('config.json', 'w', encoding='utf-8') as f:
                        json.dump(c, f, indent=2)
                except Exception as e:
                    print(f"Fehler beim Speichern der Trovo-Tokens: {e}")

            return new_access
        except Exception as e:
            print(Fore.RED + translate("[Trovo] Fehler beim Token-Refresh: %(error)s") % {'error': e})
            return None
    
    return access_token

def update_stream_info(config, title, game_name, language, translate):
    """Aktualisiert Stream-Metadaten auf Trovo."""
    mod_config = config.get('modules', {}).get(MODULE_ID, {})
    if not mod_config.get('enabled'):
        return

    access_token = _get_valid_token(mod_config, translate)
    channel_id = mod_config.get('channel_id')
    client_id = mod_config.get('client_id')
    
    if not access_token or not channel_id or not client_id:
        print(Fore.YELLOW + translate("[Trovo] Fehlende Konfiguration oder Login-Daten."))
        return

    try:
        # 1. Kategorie-ID suchen
        category_id = _get_category_id(client_id, game_name)
        
        # 2. Update via API
        url = "https://open-api.trovo.live/openplatform/channels/update"
        headers = {
            "Accept": "application/json",
            "client-id": client_id,
            "Authorization": f"OAuth {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "channel_id": channel_id,
            "live_title": title
        }
        if category_id:
            payload["category_id"] = category_id
            
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        
        print(Fore.GREEN + translate("[Trovo] Stream erfolgreich aktualisiert: %(title)s") % {'title': title})
        if category_id:
            print(f"[Trovo] Kategorie auf ID {category_id} gesetzt.")
            
    except Exception as e:
        print(Fore.RED + translate("[Trovo] Fehler bei Metadaten-Update: %(error)s") % {'error': e})
        if hasattr(e, 'response') and e.response is not None:
            print(f"API Response: {e.response.text}")
