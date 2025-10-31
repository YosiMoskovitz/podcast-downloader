
from flask import Flask, render_template, flash
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add parent src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import PodcastDatabase

from .podcasts import bp as podcasts_bp
from .interval import bp as interval_bp
from .episodes import bp as episodes_bp
from .logs import bp as logs_bp
from .gdrive import bp as gdrive_bp
from .dbviewer import bp as dbviewer_bp
from .task import bp as task_bp
from .runhistory import bp as runhistory_bp

app = Flask(__name__)

# Load .env file at startup so persisted settings are applied to the process environment
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=env_path, override=False)

# Use environment variable for secret key (cloud-safe)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

app.register_blueprint(podcasts_bp)
app.register_blueprint(interval_bp)
app.register_blueprint(episodes_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(gdrive_bp)
app.register_blueprint(dbviewer_bp)
app.register_blueprint(task_bp)
app.register_blueprint(runhistory_bp)


def get_db():
    """Get database instance."""
    return PodcastDatabase()


@app.route('/')
def index():
    """Render a simple dashboard with useful statistics.

    Data provided:
    - Database stats (total episodes, podcasts, size)
    - Recent run history (last 5 entries)
    - Recent logs tail
    - PID file presence (task.pid)
    """
    ctx = {}

    # Database stats
    try:
        db = get_db()
        stats = db.get_stats()
        ctx['total_episodes'] = stats['total_episodes']
        ctx['total_podcasts'] = stats['total_podcasts']
        ctx['total_size_bytes'] = stats['total_size_bytes']

        # Recent run history (if table exists)
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS run_history (
                id SERIAL PRIMARY KEY,
                timestamp TEXT NOT NULL,
                run_type TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT
            )''')
            cursor.execute('SELECT timestamp, run_type, status, message FROM run_history ORDER BY timestamp DESC LIMIT 5')
            rows = cursor.fetchall()
            # normalize rows
            ctx['recent_runs'] = [dict(timestamp=r[0], run_type=r[1], status=r[2], message=r[3]) for r in rows]
            conn.close()
        except Exception:
            ctx['recent_runs'] = []

    except Exception as e:
        flash(f"Error reading DB stats: {e}", 'danger')
        ctx['total_episodes'] = 0
        ctx['total_podcasts'] = 0
        ctx['total_size_bytes'] = 0
        ctx['recent_runs'] = []

    # Logs tail
    try:
        log_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'podcast_service.log')
        log_content = ''
        if os.path.exists(log_file):
            try:
                with open(log_file, encoding='utf-8') as f:
                    log_content = f.read()[-8000:]
            except UnicodeDecodeError:
                try:
                    with open(log_file, encoding='cp1252') as f:
                        log_content = f.read()[-8000:]
                except Exception:
                    with open(log_file, encoding='utf-8', errors='replace') as f:
                        log_content = f.read()[-8000:]
        ctx['logs_tail'] = log_content
    except Exception:
        ctx['logs_tail'] = ''

    # Downloads folder stats (may not exist in cloud mode)
    try:
        downloads_dir = os.path.join(os.path.dirname(__file__), '..', 'downloads')
        total_files = 0
        total_bytes = 0
        if os.path.exists(downloads_dir):
            for root, dirs, files in os.walk(downloads_dir):
                for fn in files:
                    total_files += 1
                    try:
                        total_bytes += os.path.getsize(os.path.join(root, fn))
                    except Exception:
                        pass
        ctx['downloads_files'] = total_files
        ctx['downloads_bytes'] = total_bytes
    except Exception:
        ctx['downloads_files'] = 0
        ctx['downloads_bytes'] = 0

    # PID / task status
    try:
        pid_file = os.path.join(os.path.dirname(__file__), '..', 'task.pid')
        pid_info = None
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid_info = f.read().strip()
            except Exception:
                pid_info = 'unknown'
        ctx['pid'] = pid_info
    except Exception:
        ctx['pid'] = None

    # Misc
    ctx['generated_at'] = datetime.utcnow().isoformat() + 'Z'

    return render_template('index.html', **ctx)


if __name__ == '__main__':
    # Get port from environment variable (cloud deployment) or use default
    port = int(os.environ.get('PORT', 5000))
    # Bind to 0.0.0.0 for cloud deployment
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')