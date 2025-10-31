from flask import Blueprint, render_template
import os
import logging
from .db_helper import get_connection

bp = Blueprint('runhistory', __name__, template_folder='templates')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@bp.route('/runhistory')
def run_history():
    runs = []
    error = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS run_history (
            id SERIAL PRIMARY KEY,
            timestamp TEXT NOT NULL,
            run_type TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT
        )''')
        cursor.execute('SELECT timestamp, run_type, status, message FROM run_history ORDER BY timestamp DESC LIMIT 50')
        runs = cursor.fetchall()
        conn.close()
        logger.info(f"Loaded {len(runs)} run history records")
    except Exception as e:
        error = str(e)
        logger.error(f"Error loading run history: {e}")
        runs = []
    return render_template('runhistory.html', runs=runs, error=error)
