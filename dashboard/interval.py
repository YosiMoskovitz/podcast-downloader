from flask import Blueprint, render_template, request, redirect, url_for, flash
import json
import os

bp = Blueprint('interval', __name__, template_folder='templates')

PODCASTS_JSON = os.path.join(os.path.dirname(__file__), '..', 'config', 'podcasts.json')

def load_settings():
    with open(PODCASTS_JSON, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('settings', {})

def save_settings(settings):
    with open(PODCASTS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data['settings'] = settings
    with open(PODCASTS_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@bp.route('/interval', methods=['GET', 'POST'])
def interval():
    if request.method == 'POST':
        hours = int(request.form['check_interval_hours'])
        settings = load_settings()
        settings['check_interval_hours'] = hours
        save_settings(settings)
        flash('Interval updated!')
        return redirect(url_for('interval.interval'))
    settings = load_settings()
    return render_template('interval.html', interval=settings.get('check_interval_hours', 2))
