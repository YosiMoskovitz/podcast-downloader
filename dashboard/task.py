from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context
import subprocess
import os
import signal
import sys
import logging
import time

bp = Blueprint('task', __name__, template_folder='templates')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store the PID of the background process in a file
PID_FILE = os.path.join(os.path.dirname(__file__), '..', 'task.pid')
MAIN_PATH = os.path.join(os.path.dirname(__file__), '..', 'main.py')

# Ensure src is in the path for imports
src_path = os.path.join(os.path.dirname(__file__), '..', 'src')
if src_path not in sys.path:
    sys.path.append(src_path)

# Determine Python executable to use for background tasks:
# 1. Environment variable PODCAST_PYTHON_EXE (highest priority)
# 2. config setting `settings.python_executable` in config/podcasts.json
# 3. Fallback to the interpreter running this process (sys.executable)
PYTHON_EXE = os.environ.get('PODCAST_PYTHON_EXE')
if not PYTHON_EXE:
    try:
        # Importing Config from src
        from config import Config
        try:
            cfg = Config()
            PYTHON_EXE = cfg.get_settings().get('python_executable')
        except Exception:
            PYTHON_EXE = None
    except Exception:
        PYTHON_EXE = None

if not PYTHON_EXE:
    PYTHON_EXE = sys.executable

logger.info(f"Using Python executable for background tasks: {PYTHON_EXE}")
RUN_ONCE_LOCK = os.path.join(os.path.dirname(__file__), '..', 'run_once.lock')

# Drive token check helper
try:
    from google_drive_uploader import token_is_valid
except Exception:
    token_is_valid = None

def is_drive_connected():
    """Return (connected, message).

    Use the helper `token_is_valid` from google_drive_uploader when available.
    If it isn't importable, assume the Drive connection is OK for local dev.
    """
    try:
        # Use helper if available
        if token_is_valid is not None:
            try:
                import json
                from config import Config
                
                cfg = Config()
                # Use Config methods to get credentials and token
                try:
                    creds_data = cfg.get_credentials_json()
                    token_data = cfg.get_token_json()
                    return token_is_valid(creds_data, token_data)
                except Exception as e:
                    return False, f'Failed to load credentials/token: {e}'
            except Exception as e:
                return False, f'token check helper failed: {e}'

        # Fallback: if helper not available, check that token file exists
        # (For local development when google packages may not be installed in dashboard venv)
        token_path = os.path.join(os.path.dirname(__file__), '..', 'token.json')
        if not os.path.exists(token_path):
            return False, 'token file not found'
        
        # Token file exists, assume OK for local dev
        return True, 'Token file exists (google packages not available for validation)'
    except Exception as e:
        return False, str(e)


def is_run_once_locked():
    """Check whether a run-once lock exists and is still valid.

    If the lock file exists but the PID listed inside is not running, the lock
    is considered stale and removed.
    """
    if not os.path.exists(RUN_ONCE_LOCK):
        return False
    try:
        with open(RUN_ONCE_LOCK, 'r') as f:
            content = f.read().strip()
        if not content:
            # Empty lock file, treat as stale
            os.remove(RUN_ONCE_LOCK)
            return False
        parts = content.split(',')
        pid = int(parts[0]) if parts[0].isdigit() else None
        if pid is None:
            # Unknown content, remove stale lock
            os.remove(RUN_ONCE_LOCK)
            return False
        # Check if process exists
        try:
            if os.name == 'nt':
                os.kill(pid, 0)
            else:
                os.kill(pid, 0)
            # no exception -> process exists
            return True
        except (ProcessLookupError, OSError):
            # Process not running -> stale lock
            try:
                os.remove(RUN_ONCE_LOCK)
            except OSError:
                pass
            return False
    except Exception as e:
        logger.warning(f"Error checking run-once lock: {e}")
        try:
            os.remove(RUN_ONCE_LOCK)
        except Exception:
            pass
        return False


def acquire_run_once_lock(owner_pid=None):
    """Try to create the lock file atomically. Return True if acquired."""
    if is_run_once_locked():
        return False
    try:
        # Write own PID and timestamp
        pid = owner_pid if owner_pid is not None else os.getpid()
        ts = str(int(time.time()))
        # Use exclusive creation to avoid races
        with open(RUN_ONCE_LOCK, 'x') as f:
            f.write(f"{pid},{ts}")
        return True
    except FileExistsError:
        # Someone else created it concurrently
        return False
    except Exception as e:
        logger.error(f"Failed to acquire run-once lock: {e}")
        return False


def release_run_once_lock():
    try:
        if os.path.exists(RUN_ONCE_LOCK):
            os.remove(RUN_ONCE_LOCK)
    except Exception as e:
        logger.warning(f"Failed to release run-once lock: {e}")


@bp.route('/task', methods=['GET', 'POST'])
def task_control():
    """Task control page and handler."""
    if request.method == 'POST':
        if 'run_once' in request.form:
            if run_once():
                flash('Podcast service ran once successfully!', 'success')
            else:
                flash('Error running podcast service. Check logs for details.', 'danger')
        elif 'toggle_task' in request.form:
            status = get_status()
            if status['running']:
                if stop_task():
                    flash('Background task stopped!', 'success')
                else:
                    flash('Error stopping background task. Check logs.', 'danger')
            else:
                if start_task():
                    flash('Background task started!', 'success')
                else:
                    flash('Error starting background task. Check logs.', 'danger')
        return redirect(url_for('task.task_control'))
    
    status = get_status()
    return render_template('task.html', status=status)

def run_once():
    """Run the podcast service once immediately."""
    # Prevent running if Drive not connected
    connected, msg = is_drive_connected()
    if not connected:
        logger.error(f"Refusing to run: Google Drive not connected: {msg}")
        return False
    # Prevent concurrent runs
    if not acquire_run_once_lock():
        logger.info("Run once requested but another run is already in progress")
        return False
    try:
        result = subprocess.run([PYTHON_EXE, MAIN_PATH, '--once'], 
                              capture_output=True, 
                              text=True,
                              encoding='utf-8',
                              errors='replace',
                              timeout=300)
        if result.returncode != 0:
            logger.error(f"Run once failed: {result.stderr}")
            return False
        logger.info(f"Run once completed: {result.stdout}")
        return True
    except Exception as e:
        logger.error(f"Error running once: {e}")
        return False
    finally:
        release_run_once_lock()

def start_task():
    """Start the background task if not already running."""
    # Ensure Drive is connected before starting background service
    try:
        connected, msg = is_drive_connected()
        if not connected:
            logger.error(f"Refusing to start background task: Google Drive not connected: {msg}")
            return False
    except Exception as e:
        logger.error(f"Error checking drive connection: {e}", exc_info=True)
        return False

    if not get_status()['running']:
        try:
            # Create log file for the background process
            log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'background_task.log')
            
            with open(log_file, 'a', encoding='utf-8') as f:
                proc = subprocess.Popen([PYTHON_EXE, MAIN_PATH], 
                                      stdout=f, 
                                      stderr=f,
                                      creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
                with open(PID_FILE, 'w') as pid_f:
                    pid_f.write(str(proc.pid))
                logger.info(f"Background task started with PID: {proc.pid}")
                return True
        except Exception as e:
            logger.error(f"Error starting task: {e}", exc_info=True)
            return False
    return False

def stop_task():
    """Stop the background task."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read())
            try:
                if os.name == 'nt':  # Windows
                    os.kill(pid, signal.SIGTERM)
                else:  # Unix-like
                    os.kill(pid, signal.SIGTERM)
                logger.info(f"Stopped task with PID: {pid}")
            except ProcessLookupError:
                logger.warning(f"Process {pid} not found")
            except Exception as e:
                logger.error(f"Error killing process {pid}: {e}")
            os.remove(PID_FILE)
            return True
        except Exception as e:
            logger.error(f"Error stopping task: {e}")
            return False
    return False

def get_status():
    """Get the current status of the background task."""
    running = False
    pid = None
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read())
            try:
                # Check if process is actually running
                if os.name == 'nt':  # Windows
                    os.kill(pid, 0)
                else:  # Unix-like
                    os.kill(pid, 0)
                running = True
            except (ProcessLookupError, OSError):
                # Process not running, clean up stale PID file
                logger.warning(f"Stale PID file found for PID {pid}, removing")
                os.remove(PID_FILE)
                running = False
                pid = None
        except Exception as e:
            logger.error(f"Error reading PID file: {e}")
            running = False
            pid = None
    return {'running': running, 'pid': pid}

@bp.route('/task/status', methods=['GET'])
def api_status():
    """API endpoint to get task status."""
    return jsonify(get_status())

@bp.route('/task/run-once', methods=['POST'])
def api_run_once():
    """API endpoint to run the task once."""
    try:
        if is_run_once_locked():
            return jsonify({
                'success': False,
                'message': 'Run once is already in progress.'
            }), 409

        if run_once():
            return jsonify({
                'success': True,
                'message': 'Podcast service ran once successfully!'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error running podcast service. Check logs for details.'
            }), 500
    except Exception as e:
        logger.error(f"API run_once error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@bp.route('/task/run-once-stream', methods=['GET'])
def api_run_once_stream():
    """Stream the output of a single run once execution as Server-Sent Events (SSE).

    The client should connect with EventSource and will receive lines of stdout/stderr
    as 'message' events. When the process completes a final 'done' event will be sent
    with the numeric return code in event.data.
    """
    # Ensure Drive connected before allowing run
    connected, msg = is_drive_connected()
    if not connected:
        def not_connected_gen():
            yield f"data: Google Drive not connected: {msg}\n\n"
            yield f"event: done\ndata: 1\n\n"
        return Response(stream_with_context(not_connected_gen()), mimetype='text/event-stream')

    # Try to acquire lock for streaming run-once. If lock cannot be acquired
    # stream back a quick message and finish.
    if not acquire_run_once_lock():
        def locked_gen():
            yield f"data: Another run is already in progress.\n\n"
            yield f"event: done\ndata: 1\n\n"
        return Response(stream_with_context(locked_gen()), mimetype='text/event-stream')

    def generate():
        try:
            # Start the process and stream combined stdout/stderr
            # Use utf-8 encoding explicitly to handle international characters and emojis
            proc = subprocess.Popen([PYTHON_EXE, MAIN_PATH, '--once'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True,
                                    encoding='utf-8',
                                    errors='replace',  # Replace undecodable bytes with �
                                    bufsize=1)

            # Stream each line as an SSE data message
            if proc.stdout is not None:
                for line in proc.stdout:
                    # Normalize line endings and send as SSE data event
                    text = line.rstrip('\n')
                    yield f"data: {text}\n\n"

            # Wait for process to finish and send done event with returncode
            returncode = proc.wait()
            yield f"event: done\ndata: {returncode}\n\n"
        except Exception as e:
            logger.error(f"Error in run-once stream: {e}")
            # Send an error message and a done with non-zero code
            yield f"data: Error: {str(e)}\n\n"
            yield f"event: done\ndata: 1\n\n"
        finally:
            # Always release the lock when finished
            release_run_once_lock()

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@bp.route('/task/toggle', methods=['POST'])
def api_toggle():
    """API endpoint to toggle the background task."""
    try:
        status = get_status()
        if status['running']:
            if stop_task():
                return jsonify({
                    'success': True,
                    'message': 'Background task stopped successfully!'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Error stopping background task. Check logs.'
                }), 500
        else:
            if start_task():
                return jsonify({
                    'success': True,
                    'message': 'Background task started successfully! Check status indicator.'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Error starting background task. Check logs.'
                }), 500
    except Exception as e:
        logger.error(f"API toggle error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

