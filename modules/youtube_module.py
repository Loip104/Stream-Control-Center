import traceback
import requests
import json
import urllib.parse
import time
from colorama import Fore
from flask import request, redirect, url_for, flash

MODULE_ID = "youtube"
MODULE_NAME = "YouTube Live"

# Globaler Status, um doppelte Transitions-Threads zu vermeiden
_transition_in_progress = False

def get_ui_html(CONFIG):
    """
    Liefert das HTML-Snippet für das Web-Interface.
    Alle Texte sind mit _( ) umschlossen, damit Pybabel sie erfasst.
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
    
    # Status-Text und Button-Text vorab bestimmen für sauberere Template-Logik
    status_text = "{{ _('Verbunden') }}" if access_token else "{{ _('Nicht verbunden') }}"
    if access_token and mod_config.get('channel_name'):
        status_text += f" (Kanal: <b>{mod_config['channel_name']}</b>)"
    button_text = "{{ _('Erneut mit YouTube verbinden') }}" if access_token else "{{ _('Mit YouTube verbinden') }}"

    html = f"""
    <div class="settings-group">
        <h3><i class="fab fa-youtube" style="color: #FF0000; margin-right: 10px;"></i> {{{{ _('YouTube Live API') }}}}</h3>
        <p style="font-size: 12px; color: #666; margin-top: -10px;">{{{{ _('Für die automatische Aktualisierung von YouTube Live-Streams (Titel und Kategorie).') }}}}</p>
        
        <label>
            <input type="checkbox" name="module_{MODULE_ID}_enabled" {'checked' if enabled else ''}>
            {{{{ _('YouTube Integration aktivieren') }}}}
        </label>
        <br><br>

        <a href="{{{{ url_for('connect_{MODULE_ID}') }}}}" class="cta-button" style="width: 100%; text-align: center; box-sizing: border-box; margin-bottom: 15px; background-color: #FF0000; color: white;">
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
        
        <label>{{{{ _('Client-ID (Google API):') }}}}</label>
        <input type="text" name="module_{MODULE_ID}_client_id" value="{client_id}">
        
        <label>{{{{ _('Client Secret:') }}}}</label>
        <input type="password" name="module_{MODULE_ID}_client_secret" placeholder="{placeholder_text}">

        <label>{{{{ _('Stream-Beschreibung Template:') }}}}</label>
        <textarea name="module_{MODULE_ID}_description_template" rows="5" style="width: 100%; background: #111; color: #fff; border: 1px solid #444; padding: 5px; border-radius: 3px; font-family: inherit;">{mod_config.get('description_template', '')}</textarea>
        <small class="form-text text-muted" style="display: block; margin-top: 5px;">{{{{ _('Verwende {{game}} für den Namen des Spiels.') }}}}</small>

        <label style="margin-top: 15px; display: block;">{{{{ _('YouTube Stream-Schlüssel (Geheim):') }}}}</label>
        <input type="password" name="module_{MODULE_ID}_youtube_stream_key" value="{mod_config.get('youtube_stream_key', '')}" placeholder="{{{{ _('xxxx-xxxx-xxxx-xxxx') }}}}" style="width: 100%; background: #111; color: #fff; border: 1px solid #444; padding: 5px; border-radius: 3px;">
        <small class="form-text text-muted" style="display: block; margin-top: 5px;">{{{{ _('Optional: Gib hier exakt den YouTube Stream-Key ein, an den gesendet wird, damit das Modul ihn erzwingt.') }}}}</small>

        <label style="margin-top: 15px; display: block;">{{{{ _('Wartezeit vor Live-Schaltung (Sekunden):') }}}}</label>
        <input type="number" name="module_{MODULE_ID}_live_wait_time" value="{mod_config.get('live_wait_time', 10)}" min="0" max="60" style="width: 100%; background: #111; color: #fff; border: 1px solid #444; padding: 5px; border-radius: 3px;">
        <small class="form-text text-muted" style="display: block; margin-top: 5px;">{{{{ _('Zeit, die das Tool wartet, bis YouTube das Signal verarbeitet hat (Standard: 10).') }}}}</small>

        <small class="form-text text-muted" style="display: block; margin-top: 10px;">{{{{ _('Wichtig: Speichere die Einstellungen, bevor du auf "Verbinden" klickst!') }}}}</small>

        <details style="margin-top: 15px; background: #2a2a2a; padding: 10px; border-radius: 5px; border: 1px solid #444; color: #eee;">
            <summary style="font-weight: bold; cursor: pointer; display: list-item;">{{{{ _('Anleitung: Google Cloud Console einrichten (Beim ersten Mal)') }}}}</summary>
            <div style="margin-top: 10px; font-size: 13px; line-height: 1.5;">
                <ol style="padding-left: 20px; text-align: left; margin: 0;">
                    <li>Gehe zur <a href="https://console.cloud.google.com/" target="_blank" style="color: #66b3ff;">Google Cloud Console</a> und erstelle ein neues Projekt.</li>
                    <li>Aktiviere unter <b>"APIs & Dienste" &gt; "Bibliothek"</b> die <b>YouTube Data API v3</b> für dein Projekt.</li>
                    <li>Gehe zu <b>"APIs & Dienste" &gt; "OAuth-Zustimmungsbildschirm"</b> und konfiguriere ihn:<br>
                        Nutzer: <b>Extern</b>, App-Infos ausfüllen, und füge deine E-Mail bei Testnutzern hinzu.
                    </li>
                    <li>Gehe zu <b>"Anmeldedaten" &gt; "+ Anmeldedaten erstellen" &gt; OAuth-Client-ID</b> (als Typ: Webanwendung).</li>
                    <li>Trage unter <b>Zulässige Umleitungs-URIs</b> zwingend folgendes ein:<br>
                    <code style="background: #111; padding: 3px; border-radius: 3px; user-select: all;">https://127.0.0.1:{port}/youtube_oauth_callback</code><br>
                    <span style="color: #ffcc00; font-size: 11px;">(Google erlaubt bei lokalen IP-Adressen wie 192.168.x.x keine Web-Registrierung. Darum erzwingen wir 127.0.0.1 mit dem Port {port}, was erlaubt ist.)</span></li>
                    <li>Kopiere dann auf der rechten Seite die <b>Client-ID</b> und das <b>Client Secret</b> und füge sie in unsere UI-Felder ein.</li>
                    <li>Klicke in unserem Manager ganz unten auf <b>"Speichern"</b>. Klicke DANACH auf <b>"Mit YouTube verbinden"</b>.</li>
                </ol>
                <p style="margin-top: 10px; font-style: italic; color: #ccc;">Sollte Google "App is unverified" anzeigen, klicke auf "Continue" oder "Erweitert" -> "Go to (unsafe)", da es deine eigene Test-App ist!</p>
            </div>
        </details>
    </div>
    """
    return html

def register_routes(app, flash_func, config_path):
    """
    Registriert die OAuth-Handler-Routen für Google/YouTube.
    """
    @app.route(f'/connect_{MODULE_ID}')
    def connect_youtube():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = json.load(f)
        except Exception:
            c = {}
        
        cfg = c.get('modules', {}).get(MODULE_ID, {})
        client_id = cfg.get('client_id')
        if not client_id:
            flash_func("Bitte erst eine YouTube Client-ID speichern!", "error")
            return redirect(url_for('index', _anchor='platforms'))
            
        # Port aus manager_config.json lesen
        try:
            with open('manager_config.json', 'r', encoding='utf-8') as f:
                m_cfg = json.load(f)
            port = m_cfg.get('port', 5055)
        except Exception:
            port = 5055

        # Wir erzwingen https://127.0.0.1, da Google lokale IPs verbietet und der Manager HTTPS nutzt.
        redirect_uri = f"https://127.0.0.1:{port}{url_for(f'{MODULE_ID}_oauth_callback')}"
        scopes = "https://www.googleapis.com/auth/youtube"
        
        auth_url = (f"https://accounts.google.com/o/oauth2/v2/auth?"
                    f"client_id={urllib.parse.quote(client_id)}&"
                    f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
                    f"response_type=code&"
                    f"scope={urllib.parse.quote(scopes)}&"
                    f"access_type=offline&prompt=consent")
        return redirect(auth_url)

    @app.route(f'/{MODULE_ID}_oauth_callback')
    def youtube_oauth_callback():
        code = request.args.get('code')
        if not code:
            flash_func("Kein Autorisierungscode von Google erhalten oder abgebrochen.", "error")
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
        redirect_uri = f"https://127.0.0.1:{port}{url_for(f'{MODULE_ID}_oauth_callback')}"

        token_url = "https://oauth2.googleapis.com/token"
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
            if 'refresh_token' in token_data:
                cfg['refresh_token'] = token_data.get('refresh_token')
            cfg['expires_at'] = int(time.time()) + token_data.get('expires_in', 3599)
            
            # --- NEU: Kanalnamen direkt auslesen und abspeichern ---
            try:
                ch_url = "https://youtube.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
                ch_resp = requests.get(ch_url, headers={'Authorization': f"Bearer {cfg['access_token']}"}, timeout=5)
                if ch_resp.ok:
                    items = ch_resp.json().get('items', [])
                    if items:
                        cfg['channel_name'] = items[0].get('snippet', {}).get('title', 'Unbekannt')
            except Exception:
                pass
            
            if 'modules' not in c: 
                c['modules'] = {}
            c['modules'][MODULE_ID] = cfg
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(c, f, indent=2)

            flash_func("Erfolgreich mit YouTube verbunden!", "success")
        except Exception as e:
            flash_func(f"Fehler bei der YouTube-Verbindung: {e}", "error")

        return redirect(url_for('index', _anchor='platforms'))


# --- Interne Logik für stream_v3.py (ohne Flask Kontext) ---

def _refresh_token(client_id, client_secret, refresh_token, translate):
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }
    try:
        response = requests.post(token_url, data=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(Fore.RED + translate("[YouTube] Fehler beim Erneuern des Tokens: %(error)s") % {'error': str(e)})
        return None

def _get_valid_token(config, translate):
    cfg = config.get('modules', {}).get(MODULE_ID, {})
    access_token = cfg.get('access_token')
    refresh_token = cfg.get('refresh_token')
    expires_at = cfg.get('expires_at', 0)
    client_id = cfg.get('client_id')
    client_secret = cfg.get('client_secret')

    if not all([access_token, client_id, client_secret]):
        return None

    # Wenn Token in weniger als 10 Minuten abläuft (oder abgelaufen ist)
    if expires_at < (int(time.time()) + 600):
        if not refresh_token:
            print(Fore.RED + translate("[YouTube] Fehler: Token abgelaufen und kein Refresh-Token vorhanden. Bitte neu einloggen!"))
            return None
            
        new_tokens = _refresh_token(client_id, client_secret, refresh_token, translate)
        if new_tokens:
            cfg['access_token'] = new_tokens.get('access_token')
            if 'refresh_token' in new_tokens: 
                cfg['refresh_token'] = new_tokens.get('refresh_token')
            cfg['expires_at'] = int(time.time()) + new_tokens.get('expires_in', 3599)
            
            # Speichere die aktualisierten Tokens in die config.json
            try:
                with open('config.json', 'r', encoding='utf-8') as f: 
                    full_cfg = json.load(f)
                if 'modules' not in full_cfg: 
                    full_cfg['modules'] = {}
                full_cfg['modules'][MODULE_ID] = cfg
                with open('config.json', 'w', encoding='utf-8') as f: 
                    json.dump(full_cfg, f, indent=2)
            except Exception: 
                pass
            return cfg['access_token']
        return None
    return access_token


def _create_broadcast(valid_token, title, description, translate):
    headers = {
        'Authorization': f"Bearer {valid_token}",
        'Content-Type': 'application/json'
    }
    safe_title = title.replace('<', '').replace('>', '')[:100]

    data = {
        "snippet": {
            "title": safe_title,
            "description": description,
            "scheduledStartTime": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 60))
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        },
        "contentDetails": {
            "enableAutoStart": True,
            "enableAutoStop": True,
            "monitorStream": {
                "enableMonitorStream": False
            }
        }
    }
    try:
        url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status,contentDetails"
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(Fore.RED + f"[YouTube] Fehler beim Erstellen des Broadcasts: {e}")
    return None

def _bind_broadcast(valid_token, broadcast_id, stream_id, translate):
    headers = {'Authorization': f"Bearer {valid_token}"}
    try:
        url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts/bind?id={broadcast_id}&part=id,contentDetails&streamId={stream_id}"
        resp = requests.post(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(Fore.RED + f"[YouTube] Fehler beim Binden des Streams: {e}")
    return False

def update_stream_info(config, title, game_name, language, translate):
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            fresh_config = json.load(f)
        cfg = fresh_config.get('modules', {}).get(MODULE_ID, {})
    except Exception:
        cfg = config.get('modules', {}).get(MODULE_ID, {})

    valid_token = _get_valid_token(fresh_config if 'fresh_config' in locals() else config, translate)
    if not valid_token:
        print(Fore.RED + translate("[YouTube] Fehler: Konnte keinen gültigen Token erhalten. Bitte im Web-Manager neu verbinden."))
        return

    headers = {
        'Authorization': f"Bearer {valid_token}",
        'Content-Type': 'application/json'
    }

    try:
        # Try to find active/upcoming broadcast (genau wie StreamChanger)
        get_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,contentDetails,status&mine=true&broadcastType=all&maxResults=10"
        resp = requests.get(get_url, headers=headers, timeout=10)
        resp.raise_for_status()
        items = resp.json().get('items', [])
        
        bRow = None
        for i in items:
            st = i.get('status', {}).get('lifeCycleStatus')
            if st in ['live', 'active', 'ready', 'testing', 'upcoming']:
                bRow = i
                break

        # AUTO-CREATION: If no broadcast found, create one!
        if not bRow:
            print(Fore.MAGENTA + translate("[YouTube] 🚀 Kein aktiver Broadcast gefunden. Starte Auto-Creation..."))
            
            # getYouTubeStreamId equivalent
            stream_url = "https://youtube.googleapis.com/youtube/v3/liveStreams?part=id&mine=true"
            s_resp = requests.get(stream_url, headers=headers, timeout=10)
            s_items = s_resp.json().get('items', [])
            stream_id = s_items[0]['id'] if s_items else None
            
            if not stream_id:
                print(Fore.RED + translate("[YouTube] Keine Stream-ID gefunden. Bitte erstelle einen Stream-Key im Studio."))
                return
                
            new_b = _create_broadcast(valid_token, title, f"Live-Stream via StreamChanger\nSpiel: {game_name}", translate)
            if not new_b:
                return
            
            _bind_broadcast(valid_token, new_b['id'], stream_id, translate)
            bRow = new_b
            print(Fore.GREEN + translate(f"[YouTube] ✅ Auto-Created & Bound: {bRow['id']}"))

        if bRow:
            # Update Logik exakt wie in index.js
            template = cfg.get('description_template', '')
            if template and template.strip():
                new_desc = template.replace('{game}', game_name if game_name else '').replace('{title}', title if title else '')
            else:
                desc = bRow.get('snippet', {}).get('description', '')
                if game_name and game_name not in desc:
                    new_desc = f"Gespielt wird: {game_name}\n\n{desc}"
                else:
                    new_desc = desc

            safe_title = title.replace('<', '').replace('>', '')[:100]
            
            updated_snippet = bRow['snippet'].copy()
            updated_snippet['title'] = safe_title
            updated_snippet['description'] = new_desc
            
            updated_status = bRow['status'].copy()
            updated_status['privacyStatus'] = 'public'
            
            put_payload = {
                "id": bRow['id'],
                "snippet": updated_snippet,
                "status": updated_status,
                "contentDetails": bRow['contentDetails']
            }
            
            update_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status,contentDetails"
            put_resp = requests.put(update_url, headers=headers, json=put_payload, timeout=10)
            put_resp.raise_for_status()
            
            print(Fore.GREEN + translate("[YouTube] Erfolgreich live aktualisiert (Status: öffentlich)!"))

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_msg += f" | API: {json.dumps(e.response.json())}"
            except Exception:
                error_msg += f" | API: {e.response.text}"
        print(Fore.RED + translate("[YouTube] Fehler beim Aktualisieren der Stream-Info: %(error)s") % {'error': error_msg})

