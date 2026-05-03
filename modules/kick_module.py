import requests
import json
import urllib.parse
import time
import os
import hashlib
import base64
import secrets
from flask import redirect, url_for, request
from colorama import Fore

# Modul-Metadaten
MODULE_ID = "kick"
MODULE_NAME = "Kick"

# Datei für PKCE Verifier (um Cookie-Probleme zu umgehen)
PKCE_FILE = "kick_pkce.json"

def _save_pkce(state, verifier, redirect_uri):
    """Speichert den PKCE Verifier und die genutzte Redirect-URI in einer Datei."""
    try:
        data = {}
        if os.path.exists(PKCE_FILE):
            with open(PKCE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        # Nur die letzten 10 Anfragen behalten (Cleanup)
        if len(data) > 10:
            data = dict(list(data.items())[-10:])
            
        data[state] = {
            "verifier": verifier,
            "redirect_uri": redirect_uri,
            "timestamp": int(time.time())
        }
        
        with open(PKCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[Kick] Fehler beim Speichern des PKCE Verifiers: {e}")

def _load_pkce(state):
    """Lädt den PKCE Verifier und die Redirect-URI und löscht den Eintrag."""
    try:
        if not os.path.exists(PKCE_FILE): return None, None
        with open(PKCE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if state in data:
            # Checke ob nicht älter als 10 Minuten
            if int(time.time()) - data[state]['timestamp'] < 600:
                verifier = data[state]['verifier']
                redirect_uri = data[state]['redirect_uri']
                del data[state]
                with open(PKCE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
                return verifier, redirect_uri
    except Exception as e:
        print(f"[Kick] Fehler beim Laden des PKCE Verifiers: {e}")
    return None, None

import random
import string

def generate_pkce():
    """Generiert PKCE Verifier ohne Sonderzeichen (umgeht Beta-Bugs mancher APIs)."""
    # Exakt 43 Zeichen (Minimum), nur Buchstaben und Zahlen
    chars = string.ascii_letters + string.digits
    verifier = ''.join(random.choices(chars, k=43))
    # HASHLIB SHA256
    sha256 = hashlib.sha256(verifier.encode('utf-8')).digest()
    # BASE64 URLSAFE ENCODING WITHOUT PADDING
    challenge = base64.urlsafe_b64encode(sha256).decode('utf-8').rstrip('=')
    return verifier, challenge

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
    button_text = "{{ _('Erneut mit Kick verbinden') }}" if access_token else "{{ _('Mit Kick verbinden') }}"

    html = f"""
    <div class="settings-group">
        <h3><i class="fas fa-k" style="color: #53fc18; margin-right: 10px;"></i> {{{{ _('Kick API (Public Beta)') }}}}</h3>
        <p style="font-size: 12px; color: #666; margin-top: -10px;">{{{{ _('Nutzt die offizielle Kick API v1 für Stream-Updates.') }}}}</p>
        
        <label>
            <input type="checkbox" name="module_{MODULE_ID}_enabled" {'checked' if enabled else ''}>
            {{{{ _('Kick Integration aktivieren') }}}}
        </label>
        <br><br>

        <a href="{{{{ url_for('connect_{MODULE_ID}') }}}}" class="cta-button" style="width: 100%; text-align: center; box-sizing: border-box; margin-bottom: 15px; background-color: #53fc18; color: black;">
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
                <label>{{{{ _('Kick Client-ID:') }}}}</label>
                <input type="text" name="module_{MODULE_ID}_client_id" value="{client_id}" placeholder="Client-ID von api.kick.com">
            </div>
            <div>
                <label>{{{{ _('Kick Client Secret:') }}}}</label>
                <input type="password" name="module_{MODULE_ID}_client_secret" placeholder="{placeholder_text}">
            </div>
        </div>

        <div style="margin-top: 15px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 5px; font-size: 13px;">
            <strong>{{{{ _('Anleitung:') }}}}</strong>
            <ol style="margin-top: 5px; padding-left: 20px;">
                <li>{{{{ _('Registriere deine App im Kick Developer Dashboard.') }}}}</li>
                <li>{{{{ _('Trage unter **Redirect URI** folgendes ein:') }}}}<br>
                    <code style="background: #111; padding: 3px; border-radius: 3px; user-select: all;">https://127.0.0.1:{port}/kick_oauth_callback</code></li>
                <li>{{{{ _('Kopiere Client-ID und Secret hier hinein und speichere ganz unten.') }}}}</li>
                <li>{{{{ _('Klicke auf den grünen Button oben, um die Verbindung zu autorisieren.') }}}}</li>
            </ol>
        </div>
    </div>
    """
    return html

def register_routes(app, flash_func, config_path):
    """Registriert OAuth-Routen für Kick."""
    
    @app.route(f'/connect_{MODULE_ID}')
    def connect_kick():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = json.load(f)
        except Exception:
            c = {}
        
        cfg = c.get('modules', {}).get(MODULE_ID, {})
        client_id = cfg.get('client_id')
        if not client_id:
            flash_func("Bitte erst eine Kick Client-ID speichern!", "error")
            return redirect(url_for('index', _anchor='platforms'))
            
        # Dynamisch die Redirect-URI bilden (basiert auf der aktuellen Browser-Anfrage)
        scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
        redirect_uri = f"{scheme}://{request.host}/kick_oauth_callback"
        
        # Reduziere auf das absolute Minimum
        scopes = "channel:write"
        
        # PKCE generieren
        verifier, challenge = generate_pkce()
        state = secrets.token_urlsafe(16)
        
        # DEBUG: Was senden wir an Kick?
        print(f"{Fore.YELLOW}[Kick] Starte OAuth-Login...")
        print(f"{Fore.YELLOW}[Kick] Redirect-URI (Schritt 1): {redirect_uri}")
        
        # In Datei speichern ZUSAMMEN mit der redirect_uri für Call #2
        _save_pkce(state, verifier, redirect_uri)
        
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256"
        }
        
        auth_url = f"https://id.kick.com/oauth/authorize?{urllib.parse.urlencode(params)}"
                    
        return redirect(auth_url)

    @app.route('/kick_oauth_callback')
    def kick_oauth_callback():
        code = request.args.get('code')
        state = request.args.get('state')
        
        verifier, saved_redirect_uri = _load_pkce(state) if state else (None, None)
        
        if not code or not verifier or not saved_redirect_uri:
            print(f"{Fore.RED}[Kick] Fehler: Code oder Verifier fehlen.")
            flash_func("Autorisierung bei Kick fehlgeschlagen oder abgelaufen. Bitte versuche es erneut.", "error")
            return redirect(url_for('index', _anchor='platforms'))

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = json.load(f)
        except Exception:
            c = {}

        cfg = c.get('modules', {}).get(MODULE_ID, {})
        client_id = cfg.get('client_id')
        client_secret = cfg.get('client_secret')
        
        # Nutze EXAKT die URI aus dem ersten Call
        redirect_uri = saved_redirect_uri

        # DEBUG: Was senden wir für den Token-Swap?
        print(f"{Fore.YELLOW}[Kick] Tausche Code gegen Token...")
        print(f"{Fore.YELLOW}[Kick] Genutzte Redirect-URI (Schritt 2): {redirect_uri}")

        try:
            # 1. Token abrufen
            token_url = "https://id.kick.com/oauth/token"
            
            # Payload für den Token-Swap
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
                "client_id": client_id,
                "client_secret": client_secret
            }
            
            # Header-basierte Authentifizierung (Manche APIs brauchen beides oder nur eins)
            auth_str = f"{client_id}:{client_secret}"
            base64_auth = base64.b64encode(auth_str.encode('ascii')).decode('ascii')
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json",
                "Authorization": f"Basic {base64_auth}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # Protokollierung für den User vereinfachen
            with open("kick_debug.log", "a", encoding="utf-8") as debug_f:
                debug_f.write(f"\n--- {time.ctime()} ---\n")
                debug_f.write(f"Token Swap Request (Schritt 2).\n")
                debug_f.write(f"Redirect URI: {redirect_uri}\n")
            
            # Erster Versuch: form-urlencoded (Standard)
            resp = requests.post(token_url, data=payload, headers=headers)
            
            # Zweiter Versuch: Falls 400, 401 oder 415, probiere JSON-Payload
            if resp.status_code in [400, 401, 415]:
                print(f"[Kick] Erster Versuch fehlgeschlagen ({resp.status_code}), probiere JSON-POST...")
                headers["Content-Type"] = "application/json"
                resp = requests.post(token_url, json=payload, headers=headers)
            
            print(f"[Kick] Antwort erhalten: Status {resp.status_code}")
            
            if resp.status_code != 200:
                error_text = resp.text
                print(f"{Fore.RED}[Kick] Fehler-Body: {error_text}")
                with open("kick_debug.log", "a", encoding="utf-8") as debug_f:
                    debug_f.write(f"Status: {resp.status_code}\n")
                    debug_f.write(f"Error Body: {error_text}\n")
                flash_func(f"Kick Login fehlgeschlagen (Status {resp.status_code}). Bitte Konsole prüfen.", "error")
                return redirect(url_for('index', _anchor='platforms'))
                
            resp.raise_for_status()
            token_data = resp.json()
            
            # User Info abrufen für Fallback-Updates
            slug = ""
            channel_id = ""
            try:
                user_resp = requests.get('https://api.kick.com/public/v1/users/me', headers={'Authorization': f"Bearer {token_data.get('access_token')}"}, timeout=5)
                if user_resp.status_code == 200:
                    user_data = user_resp.json()
                    slug = user_data.get('slug', '')
                    channel_id = user_data.get('id', '')
            except Exception as e:
                print(f"[Kick] Warnung: Konnte User-Profil nicht abrufen: {e}")

            # 2. In Config speichern
            if 'modules' not in c: c['modules'] = {}
            if MODULE_ID not in c['modules']: c['modules'][MODULE_ID] = {}
            
            c['modules'][MODULE_ID]['access_token'] = token_data.get('access_token')
            c['modules'][MODULE_ID]['refresh_token'] = token_data.get('refresh_token')
            c['modules'][MODULE_ID]['expires_at'] = int(time.time()) + token_data.get('expires_in', 3600)
            if slug: c['modules'][MODULE_ID]['slug'] = slug
            if channel_id: c['modules'][MODULE_ID]['channel_id'] = channel_id
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(c, f, indent=2)
                
            flash_func("Erfolgreich mit Kick verbunden! Du kannst das Modul jetzt aktivieren.", "success")
            with open("kick_debug.log", "a", encoding="utf-8") as debug_f:
                debug_f.write(f"Erfolg: Token erhalten.\n")
        except Exception as e:
            print(f"[Kick] Schwerwiegender Fehler: {e}")
            flash_func(f"Fehler bei Kick-Verbindung: {e}", "error")

        return redirect(url_for('index', _anchor='platforms'))

def _get_category_id(access_token, game_name):
    """Sucht nach der Kick Category ID."""
    if not game_name: return None
    
    url = "https://api.kick.com/public/v1/categories"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    params = {"q": game_name}
    
    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        categories = resp.json().get('data', [])
        if categories:
            # Wir nehmen den ersten Match, der am besten passt
            return categories[0].get('id')
    except Exception as e:
        print(f"[Kick] Fehler bei Kategorie-Suche: {e}")
    return None

def _get_valid_token(mod_config, translate):
    """Erneuert den Kick-Token falls abgelaufen."""
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
            url = "https://id.kick.com/oauth/token"
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret
            }
            resp = requests.post(url, data=payload)
            resp.raise_for_status()
            data = resp.json()
            
            new_access = data.get('access_token')
            new_refresh = data.get('refresh_token')
            new_expires = int(time.time()) + data.get('expires_in', 3600)
            
            # In config.json speichern
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
                    print(f"Fehler beim Speichern der Kick-Tokens: {e}")

            return new_access
        except Exception as e:
            print(Fore.RED + translate("[Kick] Fehler beim Token-Refresh: %(error)s") % {'error': e})
            return None
    
    return access_token

def update_stream_info(config, title, game_name, language, translate):
    """Aktualisiert Stream-Metadaten auf Kick."""
    mod_config = config.get('modules', {}).get(MODULE_ID, {})
    if not mod_config.get('enabled') or not mod_config.get('access_token'):
        return

    access_token = _get_valid_token(mod_config, translate)
    if not access_token:
        return

    try:
        # 1. Kategorie-ID suchen
        category_id = _get_category_id(access_token, game_name)
        
        # 2. Update via API (PATCH /public/v1/channels)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "stream_title": title
        }
        if category_id:
            payload["category_id"] = category_id
            
        try:
            print("[Kick Update] Attempting self-update (patch /channels)")
            url = "https://api.kick.com/public/v1/channels"
            resp = requests.patch(url, headers=headers, json=payload)
            resp.raise_for_status()
            print(Fore.GREEN + translate("[Kick] Stream erfolgreich aktualisiert: %(title)s") % {'title': title})
            if category_id:
                print(f"[Kick] Kategorie auf ID {category_id} gesetzt.")
        except Exception as e:
            # Fallback
            targets = [t for t in [mod_config.get('channel_id'), mod_config.get('slug')] if t]
            sub_err = e
            error_details = e.response.text if hasattr(e, 'response') and e.response else str(e)
            print(Fore.YELLOW + translate("[Kick Update] Self-update fehlgeschlagen. Versuche Fallbacks..."))
            print(f"Fehler: {error_details}")
            
            success = False
            for target in targets:
                try:
                    print(f"[Kick Update] Targeted fallback for {target}")
                    url = f"https://api.kick.com/public/v1/channels/{target}"
                    resp = requests.patch(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    print(Fore.GREEN + translate(f"[Kick] Targeted update erfolgreich für {target}"))
                    success = True
                    break
                except Exception as err:
                    sub_err = err
                    err_details = err.response.text if hasattr(err, 'response') and err.response else str(err)
                    print(Fore.RED + f"[Kick Update] Fallback for {target} fehlgeschlagen: {err_details}")
            
            if not success:
                raise sub_err

    except Exception as e:
        print(Fore.RED + translate("[Kick] Fehler bei Metadaten-Update: %(error)s") % {'error': str(e)})
        if hasattr(e, 'response') and e.response is not None:
            print(f"API Response: {e.response.text}")
