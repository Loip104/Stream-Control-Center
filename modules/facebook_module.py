import requests
import json
import urllib.parse
import time
import os
from flask import redirect, url_for, request, render_template_string
from colorama import Fore

# Modul-Metadaten
MODULE_ID = "facebook"
MODULE_NAME = "Facebook"

def get_ui_html(CONFIG):
    """
    Liefert das HTML-Snippet für das Web-Interface.
    """
    mod_config = CONFIG.get('modules', {}).get(MODULE_ID, {})
    app_id = mod_config.get('app_id', '')
    app_secret_exists = bool(mod_config.get('app_secret'))
    page_access_token = mod_config.get('page_access_token', '')
    page_name = mod_config.get('page_name', '')
    enabled = mod_config.get('enabled', False)
    
    # Port aus manager_config.json lesen
    try:
        with open('manager_config.json', 'r', encoding='utf-8') as f:
            m_cfg = json.load(f)
        port = m_cfg.get('port', 5055)
    except Exception:
        port = 5055

    placeholder_text = '••••••••••••••••' if app_secret_exists else "{{ _('Wird zum Einrichten oder Ändern benötigt') }}"
    
    status_text = f"{{{{ _('Verbunden mit Seite:') }}}} {page_name}" if page_access_token else "{{ _('Nicht verbunden') }}"
    button_text = "{{ _('Erneut mit Facebook verbinden') }}" if page_access_token else "{{ _('Mit Facebook verbinden') }}"

    html = f"""
    <div class="settings-group">
        <h3><i class="fab fa-facebook" style="color: #1877F2; margin-right: 10px;"></i> {{{{ _('Facebook Live API') }}}}</h3>
        <p style="font-size: 12px; color: #666; margin-top: -10px;">{{{{ _('Für die automatische Aktualisierung von Facebook Live-Streams auf Pages.') }}}}</p>
        
        <label>
            <input type="checkbox" name="module_{MODULE_ID}_enabled" {'checked' if enabled else ''}>
            {{{{ _('Facebook Integration aktivieren') }}}}
        </label>
        <br><br>

        <a href="{{{{ url_for('connect_{MODULE_ID}') }}}}" class="cta-button" style="width: 100%; text-align: center; box-sizing: border-box; margin-bottom: 15px; background-color: #1877F2; color: white;">
            {button_text}
        </a>
        
        <div style="margin-bottom: 15px;">
            <label>{{{{ _('Status:') }}}}</label>
            <div style="display: flex; align-items: center; gap: 10px; margin-top: 5px;">
                <div class="status-indicator">
                    <div class="status-light {'status-online' if page_access_token else 'status-offline'}"></div>
                    <span>{status_text}</span>
                </div>
            </div>
        </div>

        <div class="settings-grid" style="grid-template-columns: 1fr 1fr; gap: 15px;">
            <div>
                <label>{{{{ _('Facebook App-ID:') }}}}</label>
                <input type="text" name="module_{MODULE_ID}_app_id" value="{app_id}" placeholder="App-ID von developers.facebook.com">
            </div>
            <div>
                <label>{{{{ _('Facebook App Secret:') }}}}</label>
                <input type="password" name="module_{MODULE_ID}_app_secret" placeholder="{placeholder_text}">
            </div>
        </div>

        <div style="margin-top: 15px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 5px; font-size: 13px;">
            <strong>{{{{ _('Anleitung:') }}}}</strong>
            <ol style="margin-top: 5px; padding-left: 20px;">
                <li>{{{{ _('Gehe zum') }}}} <a href="https://developers.facebook.com/" target="_blank">Meta App Dashboard</a>.</li>
                <li>{{{{ _('Erstelle eine neue App (Typ: Business).') }}}}</li>
                <li>{{{{ _('Füge das Produkt "Facebook Login" hinzu.') }}}}</li>
                <li>{{{{ _('Trage unter **Gültige OAuth-Redirect-URIs** folgendes ein:') }}}}<br>
                    <code style="background: #111; padding: 3px; border-radius: 3px; user-select: all;">https://127.0.0.1:{port}/facebook_oauth_callback</code></li>
                <li>{{{{ _('Kopiere App-ID und App Secret hier hinein und speichere ganz unten.') }}}}</li>
                <li>{{{{ _('Klicke danach auf den blauen Button oben, um dich zu verbinden.') }}}}</li>
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
    def connect_facebook():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = json.load(f)
        except Exception:
            c = {}
        
        cfg = c.get('modules', {}).get(MODULE_ID, {})
        app_id = cfg.get('app_id')
        if not app_id:
            flash_func("Bitte erst eine Facebook App-ID speichern!", "error")
            return redirect(url_for('index', _anchor='platforms'))
            
        # Port aus manager_config.json lesen
        try:
            with open('manager_config.json', 'r', encoding='utf-8') as f:
                m_cfg = json.load(f)
            port = m_cfg.get('port', 5055)
        except Exception:
            port = 5055

        redirect_uri = f"https://127.0.0.1:{port}/facebook_oauth_callback"
        # Benötigte Berechtigungen für Pages & Live Streaming
        scopes = "public_profile,pages_manage_posts,pages_read_engagement,pages_show_list"
        
        auth_url = (f"https://www.facebook.com/v25.0/dialog/oauth?"
                    f"client_id={urllib.parse.quote(app_id)}&"
                    f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
                    f"scope={urllib.parse.quote(scopes)}")
                    
        return redirect(auth_url)

    @app.route('/facebook_oauth_callback')
    def facebook_oauth_callback():
        code = request.args.get('code')
        if not code:
            flash_func("Kein Autorisierungscode von Facebook erhalten.", "error")
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
        app_id = cfg.get('app_id')
        app_secret = cfg.get('app_secret')
        redirect_uri = f"https://127.0.0.1:{port}/facebook_oauth_callback"

        try:
            # 1. Kurzlebigen User-Token abrufen
            token_url = "https://graph.facebook.com/v25.0/oauth/access_token"
            params = {
                "client_id": app_id,
                "client_secret": app_secret,
                "redirect_uri": redirect_uri,
                "code": code
            }
            resp = requests.get(token_url, params=params)
            resp.raise_for_status()
            short_token = resp.json().get('access_token')

            # 2. In langlebigen User-Token umtauschen (60 Tage)
            long_token_params = {
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token
            }
            long_resp = requests.get(token_url, params=long_token_params)
            long_resp.raise_for_status()
            long_user_token = long_resp.json().get('access_token')

            # 3. Liste der Pages abrufen (deren Page-Tokens sind dann permanent)
            pages_url = "https://graph.facebook.com/v25.0/me/accounts"
            pages_resp = requests.get(pages_url, params={"access_token": long_user_token})
            pages_resp.raise_for_status()
            pages_data = pages_resp.json().get('data', [])

            if not pages_data:
                flash_func("Keine Facebook Pages für diesen Account gefunden.", "error")
                return redirect(url_for('index', _anchor='platforms'))

            # Wir zeigen nun eine einfache Seite zur Auswahl der Page an
            # In einer komplexeren App würde man das in das Haupt-UI integrieren,
            # für den ersten Wurf lassen wir den User hier wählen:
            options_html = ""
            for p in pages_data:
                options_html += f'<li><a href="/facebook/select_page?id={p["id"]}&name={urllib.parse.quote(p["name"])}&token={p["access_token"]}" class="cta-button" style="margin-bottom:5px; background:#1877F2;">{p["name"]}</a></li>'
            
            return render_template_string(f"""
                <body style="background:#1a1a1a; color:white; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
                <div style="background:#2a2a2a; padding:30px; border-radius:10px; max-width:400px; width:100%; text-align:center;">
                    <h2>Facebook Page wählen</h2>
                    <p>Für welche Seite sollen die Stream-Updates aktiviert werden?</p>
                    <ul style="list-style:none; padding:0;">{options_html}</ul>
                    <br><a href="/" style="color:#aaa; text-decoration:none;">Abbrechen</a>
                </div>
                </body>
            """)

        except Exception as e:
            flash_func(f"Fehler bei Facebook-Verbindung: {e}", "error")
            return redirect(url_for('index', _anchor='platforms'))

    @app.route('/facebook/select_page')
    def facebook_select_page():
        page_id = request.args.get('id')
        name = request.args.get('name')
        token = request.args.get('token')
        
        if not all([page_id, name, token]):
            return redirect(url_for('index', _anchor='platforms'))

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = json.load(f)
            
            if 'modules' not in c: c['modules'] = {}
            if MODULE_ID not in c['modules']: c['modules'][MODULE_ID] = {}
            
            c['modules'][MODULE_ID]['page_access_token'] = token
            c['modules'][MODULE_ID]['page_id'] = page_id
            c['modules'][MODULE_ID]['page_name'] = name
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(c, f, indent=2)
                
            flash_func(f"Facebook Page '{name}' erfolgreich verknüpft!", "success")
        except Exception as e:
            flash_func(f"Fehler beim Speichern der Page: {e}", "error")

        return redirect(url_for('index', _anchor='platforms'))

def _get_game_id(access_token, game_name):
    """Sucht nach der Facebook Video-Game ID für einen Spielnamen."""
    if not game_name: return None
    
    url = "https://graph.facebook.com/v25.0/search"
    params = {
        "type": "game",
        "q": game_name,
        "access_token": access_token,
        "fields": "id,name"
    }
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        games = data.get('data', [])
        if games:
            return games[0].get('id')
    except Exception as e:
        print(f"[Facebook] Fehler bei Spielsuche: {e}")
    return None

def update_stream_info(config, title, game_name, language, translate):
    """Aktualisiert Stream-Metadaten auf Facebook."""
    mod_config = config.get('modules', {}).get(MODULE_ID, {})
    if not mod_config.get('enabled') or not mod_config.get('page_access_token'):
        return

    page_token = mod_config.get('page_access_token')
    page_id = mod_config.get('page_id')

    try:
        # 1. Aktives Live-Video auf der Page finden
        live_url = f"https://graph.facebook.com/v25.0/{page_id}/live_videos"
        live_resp = requests.get(live_url, params={"access_token": page_token, "fields": "id,status,is_live"})
        live_resp.raise_for_status()
        videos = live_resp.json().get('data', [])
        
        active_video_id = None
        for v in videos:
            if v.get('status') == 'LIVE' or v.get('is_live'):
                active_video_id = v.get('id')
                break
        
        if not active_video_id:
            # Kein aktiver Stream gefunden
            return

        # 2. Spiel-ID suchen (optional)
        game_id = _get_game_id(page_token, game_name)

        # 3. Metadaten aktualisieren
        update_url = f"https://graph.facebook.com/v25.0/{active_video_id}"
        payload = {
            "title": title,
            "description": f"Gespielt wird: {game_name}\n\nAktueller Stream: {title}",
            "access_token": page_token
        }
        if game_id:
            payload["game_id"] = game_id
            
        resp = requests.post(update_url, data=payload)
        resp.raise_for_status()
        
        print(Fore.GREEN + translate("[Facebook] Stream erfolgreich aktualisiert: %(title)s") % {'title': title})
        if game_id:
            print(f"[Facebook] Spiel auf ID {game_id} gesetzt.")
            
    except Exception as e:
        print(Fore.RED + translate("[Facebook] Fehler bei Metadaten-Update: %(error)s") % {'error': e})
        if hasattr(e, 'response') and e.response is not None:
            print(f"API Response: {e.response.text}")
