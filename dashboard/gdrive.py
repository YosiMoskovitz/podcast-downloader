from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
import json
import os
import time
import tempfile
import sys
from dotenv import load_dotenv, set_key, dotenv_values

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from src.google_drive_uploader import token_is_valid
    from src.database import PodcastDatabase
except Exception:
    token_is_valid = None
    PodcastDatabase = None

bp = Blueprint('gdrive', __name__, template_folder='templates')

CREDENTIALS_JSON = os.path.join(os.path.dirname(__file__), '..', 'config', 'credentials.json')
PODCASTS_JSON = os.path.join(os.path.dirname(__file__), '..', 'config', 'podcasts.json')
TOKEN_JSON = os.path.join(os.path.dirname(__file__), '..', 'token.json')

# In-memory cache for Drive status to avoid calling the API on every page load.
# TTL controls how long the cached value is considered fresh (in seconds).
_DRIVE_STATUS_CACHE = {'connected': False, 'message': 'unknown', 'ts': 0}
_DRIVE_STATUS_TTL = 300  # 5 minutes


def _get_drive_status(force_refresh=False):
    """Return cached drive status, refreshing it if stale or forced.

    Returns a tuple (connected: bool, message: str).
    """
    now = time.time()
    if not force_refresh and (now - _DRIVE_STATUS_CACHE['ts']) < _DRIVE_STATUS_TTL:
        return _DRIVE_STATUS_CACHE['connected'], _DRIVE_STATUS_CACHE['message']

    # Refresh cache by calling the existing status logic (reuse gdrive_status code)
    try:
        # Prefer helper if available
        if token_is_valid is not None:
            try:
                # Load credentials
                if not os.path.exists(CREDENTIALS_JSON):
                    connected, msg = False, 'credentials.json not found'
                else:
                    with open(CREDENTIALS_JSON, 'r', encoding='utf-8') as f:
                        creds_data = json.load(f)
                    
                    # Load token (JSON format)
                    token_data = None
                    if os.path.exists(TOKEN_JSON):
                        try:
                            with open(TOKEN_JSON, 'r', encoding='utf-8') as f:
                                token_data = json.load(f)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            token_data = None
                    
                    connected, msg = token_is_valid(creds_data, token_data)
            except Exception as e:
                connected, msg = False, f'token check failed: {e}'
        else:
            # Manual check - JSON format only
            if not os.path.exists(TOKEN_JSON):
                connected, msg = False, 'token file not found'
            else:
                creds = None
                # Try to load token (JSON only)
                token_data = None
                try:
                    with open(TOKEN_JSON, 'r', encoding='utf-8') as f:
                        token_data = json.load(f)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    connected, msg = False, f'Failed to load token: {e}'
                
                # If we loaded JSON, try to create credentials
                if token_data:
                    try:
                        from google.oauth2.credentials import Credentials
                        creds = Credentials.from_authorized_user_info(token_data)
                    except ImportError:
                        # Google packages not available - assume token is OK if it exists
                        connected, msg = True, 'Token file exists (google packages not available for validation)'
                        creds = None
                    except Exception as e:
                        connected, msg = False, f'Failed to create credentials: {e}'
                        creds = None
                
                if creds:
                    try:
                        from googleapiclient.discovery import build
                        service = build('drive', 'v3', credentials=creds)
                        service.about().get(fields='user').execute()
                        connected, msg = True, 'Token is valid and API call succeeded'
                    except Exception as e:
                        connected, msg = False, f'Token/API call failed: {e}'
    except Exception as e:
        connected, msg = False, f'Error checking token: {e}'

    _DRIVE_STATUS_CACHE['connected'] = connected
    _DRIVE_STATUS_CACHE['message'] = msg
    _DRIVE_STATUS_CACHE['ts'] = now
    return connected, msg

# Helper to load credentials

def load_credentials():
    # Load from local file
    with open(CREDENTIALS_JSON, encoding='utf-8') as f:
        return json.load(f)


def save_credentials(data):
    """Save credentials JSON to file and database for persistence.

    Writes to a temp file in the same directory and then atomically replaces
    the target file. Also stores in database for production deployments.
    """
    # Save to file (for development)
    dirpath = os.path.dirname(CREDENTIALS_JSON)
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, prefix='credentials.', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CREDENTIALS_JSON)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    
    # Also save to database (for production with ephemeral storage)
    if PodcastDatabase:
        try:
            db = PodcastDatabase()
            db.set_setting('google_credentials', json.dumps(data, ensure_ascii=False))
        except Exception:
            pass  # Database might not be available in local dev


def save_token(token_data):
    """Save token JSON to file and database for persistence."""
    # Save to file (for development)
    with open(TOKEN_JSON, 'w', encoding='utf-8') as f:
        json.dump(token_data, f, indent=2, ensure_ascii=False)
    
    # Also save to database (for production with ephemeral storage)
    if PodcastDatabase:
        try:
            db = PodcastDatabase()
            db.set_setting('google_token', json.dumps(token_data, ensure_ascii=False))
        except Exception:
            pass  # Database might not be available in local dev


def _validate_and_normalize_credentials(data):
    """Validate uploaded credentials JSON and normalize to a dict that
    contains an `installed` key (the app templates expect this shape).

    Accepts either the standard Google download (top-level `installed` or
    `web`) and returns a dict suitable for saving and use by the app.
    Raises ValueError on invalid input.
    """
    if not isinstance(data, dict):
        raise ValueError('Credentials file is not a JSON object')

    if 'installed' in data and isinstance(data['installed'], dict):
        return data

    if 'web' in data and isinstance(data['web'], dict):
        # Convert web -> installed so the rest of the app can access creds['installed']
        return {'installed': data['web']}

    # Some service account or other JSON might not be acceptable here
    raise ValueError('Uploaded credentials JSON must contain an "installed" or "web" object')


def _persist_env_settings(settings: dict):
    """Persist provided settings to the .env file next to the project root.

    settings: dict of key -> value (string). Values set to None will be removed.
    Returns True on success, False on failure.
    """
    try:
        # Ensure .env path exists (use repo root .env)
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        # Load existing values
        load_dotenv(dotenv_path=env_path)
        current = dotenv_values(env_path) or {}
        # Update keys
        for k, v in settings.items():
            if v is None:
                # remove key by setting empty in file via set_key to empty string and then trimming later
                set_key(env_path, k, '')
            else:
                set_key(env_path, k, str(v))
        return True
    except Exception:
        return False


def load_folder_names():
    with open(PODCASTS_JSON, encoding='utf-8') as f:
        data = json.load(f)
    return [p['folder_name'] for p in data.get('podcasts', [])]


@bp.route('/gdrive/generate_env_vars', methods=['GET'])
def generate_env_vars():
    """Generate base64-encoded environment variables for production deployment."""
    import base64
    
    result = {
        'success': False,
        'credentials_base64': None,
        'token_base64': None,
        'errors': []
    }
    
    # Encode credentials
    if os.path.exists(CREDENTIALS_JSON):
        try:
            with open(CREDENTIALS_JSON, 'r', encoding='utf-8') as f:
                creds_data = json.load(f)
            creds_json = json.dumps(creds_data)
            result['credentials_base64'] = base64.b64encode(creds_json.encode()).decode()
        except Exception as e:
            result['errors'].append(f'Failed to encode credentials: {e}')
    else:
        result['errors'].append('credentials.json not found')
    
    # Encode token (JSON format only)
    if os.path.exists(TOKEN_JSON):
        try:
            with open(TOKEN_JSON, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            
            token_json = json.dumps(token_data)
            result['token_base64'] = base64.b64encode(token_json.encode()).decode()
        except Exception as e:
            result['errors'].append(f'Failed to encode token: {e}')
    else:
        result['errors'].append('token.json not found')
    
    result['success'] = len(result['errors']) == 0
    return jsonify(result)


@bp.route('/gdrive', methods=['GET', 'POST'])
def gdrive():
    folders = load_folder_names()
    # Check token status for UI
    # Prefer the helper when available, but if it's missing or fails,
    # do a lightweight Drive API call to determine connectivity.
    connected = False
    msg = 'token check not available'
    # Use cached status when possible
    connected, msg = _get_drive_status()
    insecure_transport = os.environ.get('OAUTHLIB_INSECURE_TRANSPORT') == '1'
    # Determine credential presence for UI (do NOT expose credential contents)
    local_exists = os.path.exists(CREDENTIALS_JSON)
    if local_exists:
        creds_source = 'local'
    else:
        creds_source = 'none'

    if request.method == 'POST':
        # If a credentials file was uploaded, prefer that path
        if 'credentials_file' in request.files and request.files['credentials_file']:
            f = request.files['credentials_file']
            try:
                # Limit read size to 1MB to avoid excessive uploads
                raw = f.stream.read(1024 * 1024)
                data = json.loads(raw.decode('utf-8'))
                norm = _validate_and_normalize_credentials(data)
                save_credentials(norm)
                flash('Uploaded credentials file saved successfully! Your credentials are now stored in the database and will persist across deployments.', 'success')
            except ValueError as ve:
                flash(f'Invalid credentials file: {ve}', 'danger')
            except json.JSONDecodeError as je:
                flash(f'Uploaded file is not valid JSON: {je}', 'danger')
            except Exception as e:
                flash(f'Failed to save credentials file: {e}', 'danger')
            return redirect(url_for('gdrive.gdrive'))
        
        # Handle token file upload
        if 'token_file' in request.files and request.files['token_file']:
            f = request.files['token_file']
            try:
                # Limit read size to 1MB
                raw = f.stream.read(1024 * 1024)
                # Parse JSON format only
                try:
                    token_data = json.loads(raw.decode('utf-8'))
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    raise ValueError(f"Token file must be valid JSON: {e}")
                
                # Save token in JSON format
                save_token(token_data)
                
                flash('Uploaded token file saved successfully!', 'success')
                # Force status refresh
                _DRIVE_STATUS_CACHE['ts'] = 0
            except Exception as e:
                flash(f'Failed to save token file: {e}', 'danger')
            return redirect(url_for('gdrive.gdrive'))
        
        # If no file uploaded, show informational message
        if 'credentials_file' not in request.files and 'token_file' not in request.files:
            flash('No file uploaded.', 'warning')
        return redirect(url_for('gdrive.gdrive'))

    return render_template('gdrive.html', folders=folders, gdrive_connected=connected, gdrive_status_msg=msg, insecure_transport=insecure_transport, creds_source=creds_source)


# Route to enable insecure transport for local testing
@bp.route('/gdrive/set_insecure_transport', methods=['POST'])
def set_insecure_transport():
    import sys
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    # Optionally persist this in a .env file for future runs
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    try:
        with open(env_path, 'a', encoding='utf-8') as f:
            f.write('\nOAUTHLIB_INSECURE_TRANSPORT=1\n')
    except Exception as e:
        flash(f'Failed to persist environment variable: {e}', 'danger')
        return redirect(url_for('gdrive.gdrive'))

    # Attempt to restart the server automatically
    try:
        flash('OAUTHLIB_INSECURE_TRANSPORT=1 set for this machine. Restarting server...', 'info')
        # Clear status cache so next load re-checks quickly after restart
        _DRIVE_STATUS_CACHE['ts'] = 0
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        flash(f'Failed to restart server automatically: {e}', 'danger')
    return redirect(url_for('gdrive.gdrive'))


@bp.route('/gdrive/status', methods=['GET'])
def gdrive_status():
    # Prefer using the token_is_valid helper when available. If it's not
    # importable (or it raises), fall back to performing a lightweight
    # Drive API call using the saved token. This ensures the status badge
    # reflects an actual API success rather than just token file readability.
    if token_is_valid is not None:
        try:
            # Load credentials
            if not os.path.exists(CREDENTIALS_JSON):
                return jsonify({'connected': False, 'message': 'credentials.json not found'})
            
            with open(CREDENTIALS_JSON, 'r', encoding='utf-8') as f:
                creds_data = json.load(f)
            
            # Load token (try JSON first, then pickle for backwards compatibility)
            token_data = None
            if os.path.exists(TOKEN_JSON):
                try:
                    with open(TOKEN_JSON, 'r', encoding='utf-8') as f:
                        token_data = json.load(f)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    return jsonify({'connected': False, 'message': f'Failed to load token: {e}'})
            
            connected, msg = token_is_valid(creds_data, token_data)
            return jsonify({'connected': connected, 'message': msg})
        except Exception as e:
            # fall through to manual check
            pass

    # Manual check: attempt to load token and call Drive API
    try:
        if not os.path.exists(TOKEN_JSON):
            return jsonify({'connected': False, 'message': 'token file not found'})
        
        # Load JSON format only
        creds = None
        try:
            with open(TOKEN_JSON, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_info(token_data)
        except (json.JSONDecodeError, UnicodeDecodeError, ImportError) as e:
            return jsonify({'connected': False, 'message': f'Failed to load token: {e}'})
        
        if not creds:
            return jsonify({'connected': False, 'message': 'Failed to load credentials'})
        
        try:
            from googleapiclient.discovery import build
        except Exception as e:
            return jsonify({'connected': False, 'message': f'googleapiclient not available: {e}'})
        try:
            service = build('drive', 'v3', credentials=creds)
            service.about().get(fields='user').execute()
            return jsonify({'connected': True, 'message': 'Token is valid and API call succeeded'})
        except Exception as e:
            return jsonify({'connected': False, 'message': f'Token/API call failed: {e}'})
    except Exception as e:
        return jsonify({'connected': False, 'message': f'Error checking token: {e}'})


def _run_oauth_flow_in_thread():
    # Deprecated helper - retained for reference
    pass


@bp.route('/gdrive/start_auth', methods=['GET'])
def start_auth():
    """Start the web-based OAuth flow by redirecting the user to Google's consent page.

    The callback will be handled by /gdrive/oauth2callback.
    """
    # Ensure we have a client secrets file
    if not os.path.exists(CREDENTIALS_JSON):
        flash('Credentials file not found. Please upload credentials.json first.', 'danger')
        return redirect(url_for('gdrive.gdrive'))

    try:
        scopes = ['https://www.googleapis.com/auth/drive']
        from google_auth_oauthlib.flow import Flow
        redirect_uri = url_for('gdrive.oauth2callback', _external=True)
        flow = Flow.from_client_secrets_file(CREDENTIALS_JSON, scopes=scopes, redirect_uri=redirect_uri)
        auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
        # Store state in session for verification in callback
        session['oauth_state'] = state
        return redirect(auth_url)
    except Exception as e:
        flash(f'Failed to start OAuth flow: {e}', 'danger')
        return redirect(url_for('gdrive.gdrive'))


@bp.route('/gdrive/oauth2callback', methods=['GET'])
def oauth2callback():
    """OAuth2 callback endpoint to exchange code for tokens and save token.json."""
    if 'oauth_state' not in session:
        flash('OAuth state missing from session. Please start authentication again.', 'danger')
        return redirect(url_for('gdrive.gdrive'))
    try:
        from google_auth_oauthlib.flow import Flow
        state = session.pop('oauth_state', None)
        
        if not os.path.exists(CREDENTIALS_JSON):
            flash('Credentials file not found. Please upload credentials.json first.', 'danger')
            return redirect(url_for('gdrive.gdrive'))

        redirect_uri = url_for('gdrive.oauth2callback', _external=True)
        flow = Flow.from_client_secrets_file(CREDENTIALS_JSON, scopes=['https://www.googleapis.com/auth/drive'], state=state, redirect_uri=redirect_uri)
        # Use the full request URL (including query string) to fetch the token
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
        
        # Convert credentials to JSON and save (both file and database)
        token_data = json.loads(creds.to_json())
        save_token(token_data)
        
        # Clear cached status so the next page load shows the new connected state
        _DRIVE_STATUS_CACHE['ts'] = 0
        flash('Google Drive successfully authenticated! Your token is now stored in the database and will persist across deployments.', 'success')
        return redirect(url_for('gdrive.gdrive'))
    except Exception as e:
        msg = f'OAuth callback failed: {e}'
        if 'insecure_transport' in str(e):
            msg += '  If this is a local deployment, you can enable OAuth over HTTP by clicking the red button on this page.'
        flash(msg, 'danger')
        return redirect(url_for('gdrive.gdrive'))
