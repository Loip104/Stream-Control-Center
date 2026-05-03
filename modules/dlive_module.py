import requests
import json
import time
import os
import uuid
import urllib.parse
from flask import redirect, url_for, request
from colorama import Fore

# Modul-Metadaten
MODULE_ID = "dlive"
MODULE_NAME = "DLive"

def get_ui_html(CONFIG):
    """
    Liefert das HTML-Snippet für das Web-Interface.
    """
    mod_config = CONFIG.get('modules', {}).get(MODULE_ID, {})
    client_id = mod_config.get('client_id', '')
    client_secret_exists = bool(mod_config.get('client_secret'))
    access_token = mod_config.get('access_token', '')
    fingerprint = mod_config.get('fingerprint', '')
    display_name = mod_config.get('display_name', '')
    enabled = mod_config.get('enabled', False)
    
    # Generiere einen Fingerprint, falls keiner existiert
    if not fingerprint:
        fingerprint = str(uuid.uuid4())

    # Port aus manager_config.json lesen
    try:
        with open('manager_config.json', 'r', encoding='utf-8') as f:
            m_cfg = json.load(f)
        port = m_cfg.get('port', 5055)
    except Exception:
        port = 5055

    placeholder_text = '••••••••••••••••' if client_secret_exists else "{{ _('Wird zum Einrichten oder Ändern benötigt') }}"
    
    status_text = f"{{{{ _('Verbunden als:') }}}} {display_name}" if access_token and display_name else "{{ _('Nicht verbunden') }}"
    button_text = "{{ _('Erneut mit DLive verbinden') }}" if access_token else "{{ _('Mit DLive verbinden') }}"

    html = f"""
    <div class="settings-group">
        <h3><i class="fas fa-gem" style="color: #ffd700; margin-right: 10px;"></i> {{{{ _('DLive API (GraphQL)') }}}}</h3>
        <p style="font-size: 12px; color: #666; margin-top: -10px;">{{{{ _('DLive nutzt GraphQL für Stream-Updates. Du musst deine App erst registrieren lassen.') }}}}</p>
        
        <label>
            <input type="checkbox" name="module_{MODULE_ID}_enabled" {'checked' if enabled else ''}>
            {{{{ _('DLive Integration aktivieren') }}}}
        </label>
        <br><br>

        <a href="{{{{ url_for('connect_{MODULE_ID}') }}}}" class="cta-button" style="width: 100%; text-align: center; box-sizing: border-box; margin-bottom: 15px; background-color: #ffd700; color: #111;">
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
                <label>{{{{ _('DLive Client-ID:') }}}}</label>
                <input type="text" name="module_{MODULE_ID}_client_id" value="{client_id}" placeholder="Client-ID von DLive">
            </div>
            <div>
                <label>{{{{ _('DLive Client Secret:') }}}}</label>
                <input type="password" name="module_{MODULE_ID}_client_secret" placeholder="{placeholder_text}">
            </div>
        </div>

        <div style="margin-top: 15px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 5px; font-size: 13px;">
            <strong>{{{{ _('Anleitung:') }}}}</strong>
            <ol style="margin-top: 5px; padding-left: 20px;">
                <li>{{{{ _('Registriere deine App unter') }}}} <a href="https://go.dlive.tv/developers" target="_blank">go.dlive.tv/developers</a>.</li>
                <li>{{{{ _('Nach der Freischaltung erhältst du Client-ID und Secret.') }}}}</li>
                <li>{{{{ _('Trage unter **Redirect URI** folgendes ein:') }}}}<br>
                    <code style="background: #111; padding: 3px; border-radius: 3px; user-select: all;">https://127.0.0.1:{port}/dlive_oauth_callback</code></li>
                <li>{{{{ _('Kopiere die Daten hier hinein und klicke oben auf Verbinden.') }}}}</li>
            </ol>
        </div>
    </div>
    """
    return html

def register_routes(app, flash_func, config_path):
    """Registriert OAuth-Routen für DLive."""
    @app.route(f'/connect_{MODULE_ID}')
    def connect_dlive():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = json.load(f)
        except Exception:
            c = {}
        
        cfg = c.get('modules', {}).get(MODULE_ID, {})
        client_id = cfg.get('client_id')
        if not client_id:
            flash_func("Bitte erst eine DLive Client-ID speichern!", "error")
            return redirect(url_for('index', _anchor='platforms'))
            
        # Port aus manager_config.json lesen
        try:
            with open('manager_config.json', 'r', encoding='utf-8') as f:
                m_cfg = json.load(f)
            port = m_cfg.get('port', 5055)
        except Exception:
            port = 5055

        redirect_uri = f"https://127.0.0.1:{port}/dlive_oauth_callback"
        # Scopes laut DLive Doku
        scopes = "user:read livestream:write"
        
        auth_url = (f"https://dlive.tv/o/authorize?"
                    f"client_id={urllib.parse.quote(client_id)}&"
                    f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
                    f"response_type=code&"
                    f"scope={urllib.parse.quote(scopes)}")
                    
        return redirect(auth_url)

    @app.route('/dlive_oauth_callback')
    def dlive_oauth_callback():
        code = request.args.get('code')
        if not code:
            flash_func("Kein Autorisierungscode von DLive erhalten.", "error")
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
        redirect_uri = f"https://127.0.0.1:{port}/dlive_oauth_callback"

        try:
            # 1. Token abrufen
            token_url = "https://dlive.tv/o/token"
            payload = {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }
            resp = requests.post(token_url, data=payload)
            resp.raise_for_status()
            token_data = resp.json()
            
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 2592000) # 30 Tage Standard

            # 2. Fingerprint generieren falls nötig
            fingerprint = cfg.get('fingerprint') or str(uuid.uuid4())

            # 3. Usernamen abrufen zur Bestätigung
            query = "query { me { displayname } }"
            user_data = _query_dlive(access_token, fingerprint, query)
            display_name = ""
            if user_data and 'data' in user_data and user_data['data'].get('me'):
                display_name = user_data['data']['me'].get('displayname')

            # 4. Speichern
            if 'modules' not in c: c['modules'] = {}
            if MODULE_ID not in c['modules']: c['modules'][MODULE_ID] = {}
            
            c['modules'][MODULE_ID]['access_token'] = access_token
            c['modules'][MODULE_ID]['refresh_token'] = refresh_token
            c['modules'][MODULE_ID]['expires_at'] = int(time.time()) + expires_in
            c['modules'][MODULE_ID]['display_name'] = display_name
            c['modules'][MODULE_ID]['fingerprint'] = fingerprint
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(c, f, indent=2)
                
            flash_func(f"Erfolgreich mit DLive verbunden ({display_name})!", "success")
        except Exception as e:
            flash_func(f"Fehler bei DLive-Verbindung: {e}", "error")

        return redirect(url_for('index', _anchor='platforms'))

def _query_dlive(access_token, fingerprint, query, variables=None):
    """Hilfsfunktion für GraphQL-Anfragen an DLive."""
    url = "https://api.dlive.tv"
    headers = {
        "Authorization": access_token,
        "fingerprint": fingerprint,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
        
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[DLive] API Fehler: {e}")
        return None

def _get_category_id(access_token, fingerprint, game_name):
    """Sucht nach der numerischen Kategorie-ID für DLive."""
    if not game_name: return 0
    
    query = """
    query CategorySearch($text: String) {
      categories(text: $text, first: 5) {
        list {
          id
          name
        }
      }
    }
    """
    data = _query_dlive(access_token, fingerprint, query, {"text": game_name})
    if data and 'data' in data and data['data'].get('categories'):
        cat_list = data['data']['categories'].get('list', [])
        if cat_list:
            return int(cat_list[0]['id'])
    return 0

def update_stream_info(config, title, game_name, language, translate):
    """Aktualisiert Stream-Metadaten auf DLive."""
    mod_config = config.get('modules', {}).get(MODULE_ID, {})
    if not mod_config.get('enabled') or not mod_config.get('access_token'):
        return

    access_token = mod_config.get('access_token')
    fingerprint = mod_config.get('fingerprint', 'antigravity-default')

    # Sprache zu DLive ID mappen (Standard: 8 = Deutsch, 1 = Englisch)
    lang_id = 8 if language.lower() == 'de' else 1
    
    try:
        # 1. Kategorie suchen
        category_id = _get_category_id(access_token, fingerprint, game_name)
        
        # 2. Mutation senden
        mutation = """
        mutation LivestreamUpdate($title: String, $categoryId: Int, $languageId: Int) {
          livestreamUpdate(title: $title, categoryId: $categoryId, languageId: $languageId) {
            title
            category {
              id
              name
            }
          }
        }
        """
        variables = {
            "title": title,
            "categoryId": category_id,
            "languageId": lang_id
        }
        
        result = _query_dlive(access_token, fingerprint, mutation, variables)
        
        if result and 'data' in result and result['data'].get('livestreamUpdate'):
            print(Fore.GREEN + translate("[DLive] Stream erfolgreich aktualisiert: %(title)s") % {'title': title})
            if category_id:
                print(f"[DLive] Kategorie: {category_id}")
        else:
            err = result.get('errors', 'Unbekannter Fehler') if result else "Keine Antwort"
            print(Fore.RED + translate("[DLive] Update fehlgeschlagen: %(error)s") % {'error': err})
            
    except Exception as e:
        print(Fore.RED + translate("[DLive] Schwerwiegender Fehler: %(error)s") % {'error': e})

# Hook für den Web-Manager: Überprüfe den Token beim Speichern
def on_settings_saved(config):
    """Wird aufgerufen, wenn die Einstellungen im Web-UI gespeichert werden."""
    mod_config = config.get('modules', {}).get(MODULE_ID, {})
    access_token = mod_config.get('access_token')
    fingerprint = mod_config.get('fingerprint')
    
    if access_token and fingerprint:
        query = "query { me { displayname } }"
        data = _query_dlive(access_token, fingerprint, query)
        if data and 'data' in data and data['data'].get('me'):
            display_name = data['data']['me'].get('displayname')
            # Update den Anzeigenamen in der Config für das UI
            config['modules'][MODULE_ID]['display_name'] = display_name
            return True
    return False
