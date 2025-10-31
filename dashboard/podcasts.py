from flask import Blueprint, render_template, request, redirect, url_for, flash
import json
import os
import sys
from flask import jsonify

# Add src directory to path for database imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from database import PodcastDatabase
except Exception:
    PodcastDatabase = None

bp = Blueprint('podcasts', __name__, template_folder='templates')

PODCASTS_JSON = os.path.join(os.path.dirname(__file__), '..', 'config', 'podcasts.json')

def get_db():
    """Get database instance if available."""
    if PodcastDatabase:
        try:
            return PodcastDatabase()
        except Exception:
            return None
    return None

def load_podcasts():
    with open(PODCASTS_JSON, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('podcasts', [])

def save_podcasts(podcasts):
    with open(PODCASTS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data['podcasts'] = podcasts
    with open(PODCASTS_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@bp.route('/podcasts')
def podcasts():
    podcasts = load_podcasts()
    return render_template('podcasts.html', podcasts=podcasts)

@bp.route('/podcasts/add', methods=['POST'])
def add_podcast():
    podcasts = load_podcasts()
    name = request.form['name']
    rss_url = request.form['rss_url']
    folder_name = request.form['folder_name']
    enabled = 'enabled' in request.form
    # keep_count is optional; empty string or missing means keep all
    keep_count_val = request.form.get('keep_count', '').strip()
    try:
        keep_count = int(keep_count_val) if keep_count_val != '' else None
    except Exception:
        keep_count = None
    
    new_podcast = {
        'name': name,
        'rss_url': rss_url,
        'folder_name': folder_name,
        'enabled': enabled,
        'keep_count': keep_count
    }
    podcasts.append(new_podcast)
    save_podcasts(podcasts)
    
    # Also add to database if enabled
    if enabled:
        db = get_db()
        if db:
            try:
                db.add_or_update_podcast(
                    name=name,
                    rss_url=rss_url,
                    folder_name=folder_name,
                    drive_folder_id=None,
                    keep_count=keep_count if keep_count is not None else -1
                )
            except Exception as e:
                flash(f'Podcast added to config but failed to sync to database: {e}', 'warning')
    
    flash('Podcast added!')
    return redirect(url_for('podcasts.podcasts'))

@bp.route('/podcasts/delete/<int:index>', methods=['POST'])
def delete_podcast(index):
    podcasts = load_podcasts()
    if 0 <= index < len(podcasts):
        podcast_name = podcasts[index].get('name')
        podcasts.pop(index)
        save_podcasts(podcasts)
        
        # Also remove from database
        db = get_db()
        if db and podcast_name:
            try:
                conn = db._get_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM podcasts WHERE name = %s', (podcast_name,))
                conn.commit()
                conn.close()
            except Exception as e:
                flash(f'Podcast deleted from config but failed to remove from database: {e}', 'warning')
        
        flash('Podcast deleted!')
    return redirect(url_for('podcasts.podcasts'))

@bp.route('/podcasts/toggle/<int:index>', methods=['POST'])
def toggle_podcast(index):
    podcasts = load_podcasts()
    if 0 <= index < len(podcasts):
        podcast = podcasts[index]
        new_enabled = not podcast.get('enabled', True)
        podcast['enabled'] = new_enabled
        save_podcasts(podcasts)
        
        # Sync with database: add if enabling, optionally remove if disabling
        db = get_db()
        if db:
            try:
                if new_enabled:
                    # Add to database when enabled
                    db.add_or_update_podcast(
                        name=podcast['name'],
                        rss_url=podcast['rss_url'],
                        folder_name=podcast['folder_name'],
                        drive_folder_id=None,
                        keep_count=podcast.get('keep_count') if podcast.get('keep_count') is not None else -1
                    )
                else:
                    # Optionally remove from database when disabled (or leave it for history)
                    # For now, we'll leave it in the database for historical data
                    pass
            except Exception as e:
                flash(f'Podcast toggled but failed to sync to database: {e}', 'warning')
        
        flash('Podcast status updated!')
    return redirect(url_for('podcasts.podcasts'))


@bp.route('/podcasts/edit/<int:index>', methods=['POST'])
def edit_podcast(index):
    """Edit podcast metadata fields exposed in the UI (currently keep_count)."""
    podcasts = load_podcasts()
    if 0 <= index < len(podcasts):
        podcast = podcasts[index]
        keep_count_val = request.form.get('keep_count', '').strip()
        try:
            keep_count = int(keep_count_val) if keep_count_val != '' else None
        except Exception:
            keep_count = None
        # Store None as absent (dashboard uses missing or null to mean keep all)
        if keep_count is None:
            # remove key if present to keep JSON clean
            podcast.pop('keep_count', None)
        else:
            podcast['keep_count'] = keep_count

        save_podcasts(podcasts)
        
        # Also update database if podcast is enabled
        if podcast.get('enabled', True):
            db = get_db()
            if db:
                try:
                    db.add_or_update_podcast(
                        name=podcast['name'],
                        rss_url=podcast['rss_url'],
                        folder_name=podcast['folder_name'],
                        drive_folder_id=None,
                        keep_count=keep_count if keep_count is not None else -1
                    )
                except Exception as e:
                    flash(f'Podcast updated in config but failed to sync to database: {e}', 'warning')
        
        flash('Podcast updated!')

    return redirect(url_for('podcasts.podcasts'))


@bp.route('/podcasts/update/<int:index>', methods=['POST'])
def update_podcast(index):
    """Update multiple podcast fields from the edit modal."""
    podcasts = load_podcasts()
    if 0 <= index < len(podcasts):
        old_name = podcasts[index].get('name')
        name = request.form.get('name', old_name)
        rss_url = request.form.get('rss_url', podcasts[index].get('rss_url'))
        folder_name = request.form.get('folder_name', podcasts[index].get('folder_name'))
        enabled = 'enabled' in request.form
        keep_count_val = request.form.get('keep_count', '').strip()
        try:
            keep_count = int(keep_count_val) if keep_count_val != '' else None
        except Exception:
            keep_count = None

        podcasts[index]['name'] = name
        podcasts[index]['rss_url'] = rss_url
        podcasts[index]['folder_name'] = folder_name
        podcasts[index]['enabled'] = enabled
        if keep_count is None:
            podcasts[index].pop('keep_count', None)
        else:
            podcasts[index]['keep_count'] = keep_count

        save_podcasts(podcasts)
        
        # Also update database if enabled
        if enabled:
            db = get_db()
            if db:
                try:
                    # If name changed, we need to handle it specially
                    if old_name != name:
                        # Delete old entry and create new one
                        conn = db._get_connection()
                        cursor = conn.cursor()
                        cursor.execute('DELETE FROM podcasts WHERE name = %s', (old_name,))
                        conn.commit()
                        conn.close()
                    
                    db.add_or_update_podcast(
                        name=name,
                        rss_url=rss_url,
                        folder_name=folder_name,
                        drive_folder_id=None,
                        keep_count=keep_count if keep_count is not None else -1
                    )
                except Exception as e:
                    flash(f'Podcast updated in config but failed to sync to database: {e}', 'warning')
        
        flash('Podcast updated!')

    return redirect(url_for('podcasts.podcasts'))


@bp.route('/api/podcasts/last_modified')
def api_podcasts_last_modified():
    """Return the last-modified time of the podcasts.json file (ISO format)."""
    try:
        mtime = os.path.getmtime(PODCASTS_JSON)
        from datetime import datetime
        ts = datetime.fromtimestamp(mtime).isoformat()
        return jsonify({'last_modified': ts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
