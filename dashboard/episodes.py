from flask import Blueprint, render_template
import os
from .db_helper import get_connection

bp = Blueprint('episodes', __name__, template_folder='templates')

@bp.route('/episodes')
def episodes():
    podcasts = {}
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Prefer using the DB's id and downloaded_date (uploaded time) so the
        # episodes page aligns with the stored records and upload ordering.
        try:
            # Try drive_file_url first and order by downloaded_date (uploaded time)
            cursor.execute('''
                SELECT podcast_seq, podcast_name, episode_title, downloaded_date, drive_file_url
                FROM episodes
                WHERE drive_file_url IS NOT NULL
                ORDER BY podcast_name, downloaded_date DESC
            ''')
            rows = cursor.fetchall()
            for row in rows:
                _id, podcast_name, title, downloaded, url = row
                if podcast_name not in podcasts:
                    podcasts[podcast_name] = []
                podcasts[podcast_name].append({'id': _id, 'title': title, 'uploaded': downloaded, 'url': url})
        except Exception:
            # Fallback: use drive_file_id
            try:
                cursor.execute('''
                    SELECT podcast_seq, podcast_name, episode_title, downloaded_date, drive_file_id
                    FROM episodes
                    WHERE drive_file_id IS NOT NULL
                    ORDER BY podcast_name, downloaded_date DESC
                ''')
                for row in cursor.fetchall():
                    _id, podcast_name, title, downloaded, drive_id = row
                    if podcast_name not in podcasts:
                        podcasts[podcast_name] = []
                    url = None
                    if drive_id:
                        url = f'https://drive.google.com/file/d/{drive_id}/view'
                    podcasts[podcast_name].append({'id': _id, 'title': title, 'uploaded': downloaded, 'url': url})
            except Exception:
                podcasts = {}
        finally:
            conn.close()
    except Exception as e:
        # Log nothing here to avoid introducing a logging dependency in the dashboard
        podcasts = {}
    return render_template('episodes.html', podcasts=podcasts)
