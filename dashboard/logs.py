from flask import Blueprint, render_template, send_file, request, flash
import os

bp = Blueprint('logs', __name__, template_folder='templates')

LOG_FILE = os.path.join(os.path.dirname(__file__), '..', 'logs', 'podcast_service.log')

@bp.route('/logs')
def logs():
    log_content = ''
    if os.path.exists(LOG_FILE):
        # Try reading as UTF-8 first (preferred). If that fails, fall back to
        # Windows-1252 (common for logs created on Windows). As a final
        # fallback use 'errors="replace"' to avoid crashing the page.
        try:
            with open(LOG_FILE, encoding='utf-8') as f:
                log_content = f.read()[-10000:]  # Show last 10,000 chars
        except UnicodeDecodeError:
            try:
                with open(LOG_FILE, encoding='cp1252') as f:
                    log_content = f.read()[-10000:]
            except Exception:
                # Last resort: decode with replacement for any remaining issues.
                with open(LOG_FILE, encoding='utf-8', errors='replace') as f:
                    log_content = f.read()[-10000:]
    return render_template('logs.html', log_content=log_content)

@bp.route('/logs/download')
def download_log():
    if os.path.exists(LOG_FILE):
        return send_file(LOG_FILE, as_attachment=True)
    flash('Log file not found!')
    return render_template('logs.html', log_content='')
