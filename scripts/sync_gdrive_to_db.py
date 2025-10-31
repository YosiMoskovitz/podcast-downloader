"""Sync Google Drive files into the local episodes DB.

This script will:
 - Read `config/podcasts.json` to get podcast folder names and podcast names
 - For each podcast, find the corresponding Drive folder (or use saved drive_folder_id)
 - List files in that folder and insert any files not already present in the DB

Notes:
 - episode_url is stored as ``drive://<file_id>`` to ensure uniqueness
 - Requires valid `config/credentials.json` and a working `token.json` (pickled creds)
"""
import json
import os
import sys
import sqlite3
import logging
from typing import Dict, Any

# Ensure project root is on sys.path so we can import src modules
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.google_drive_uploader import GoogleDriveUploader
from src.database import PodcastDatabase

LOG = logging.getLogger('sync_gdrive_to_db')
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def load_podcasts_config(path: str) -> Dict[str, Any]:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def db_has_file(db, file_id: str, podcast_name: str, file_name: str) -> bool:
    """Check if a file is already represented in the episodes table.

    We check drive_file_id, episode_url (drive://...), and as a fallback podcast_name+episode_title.
    """
    conn = db._get_connection()
    try:
        cursor = conn.cursor()
        query = '''SELECT 1 FROM episodes WHERE drive_file_id = %s OR episode_url = %s OR (podcast_name = %s AND episode_title = %s) LIMIT 1'''
        params = (file_id, f"drive://{file_id}", podcast_name, file_name)
        cursor.execute(query, params)
        return cursor.fetchone() is not None
    finally:
        conn.close()


def main():
    repo_root = ROOT
    creds_path = os.path.join(repo_root, 'config', 'credentials.json')
    podcasts_json = os.path.join(repo_root, 'config', 'podcasts.json')
    token_path = os.path.join(repo_root, 'token.json')

    if not os.path.exists(creds_path):
        LOG.error('Google credentials not found at %s', creds_path)
        return
    if not os.path.exists(podcasts_json):
        LOG.error('Podcasts config not found at %s', podcasts_json)
        return

    # Load credentials and token as dicts
    with open(creds_path, 'r', encoding='utf-8') as f:
        credentials = json.load(f)
    
    token = None
    if os.path.exists(token_path):
        try:
            with open(token_path, 'r', encoding='utf-8') as f:
                token = json.load(f)
        except Exception as e:
            LOG.warning(f'Failed to load token: {e}')
    
    config = load_podcasts_config(podcasts_json)
    
    # Initialize database and uploader with new API
    from src.database import PodcastDatabase
    db = PodcastDatabase()
    uploader = GoogleDriveUploader(credentials, token, db=db)

    added_count = 0
    added_items = []

    for p in config.get('podcasts', []):
        podcast_name = p.get('name')
        folder_name = p.get('folder_name')
        enabled = p.get('enabled', True)
        if not enabled:
            LOG.info('Skipping disabled podcast: %s', podcast_name)
            continue

        LOG.info('Processing podcast: %s (folder: %s)', podcast_name, folder_name)

        # Try to get saved drive folder id from DB podcasts table
        saved = db.get_podcast(podcast_name)
        drive_folder_id = None
        if saved and saved.get('drive_folder_id'):
            drive_folder_id = saved.get('drive_folder_id')
            LOG.info('Using saved drive folder id for %s: %s', podcast_name, drive_folder_id)
        else:
            drive_folder_id = uploader.find_folder(folder_name)
            if drive_folder_id:
                LOG.info('Found drive folder id for %s: %s', podcast_name, drive_folder_id)
                try:
                    db.update_podcast_drive_folder_id(podcast_name, drive_folder_id)
                except Exception:
                    # Avoid failing if the podcasts table or column doesn't exist as expected
                    pass

        if not drive_folder_id:
            LOG.warning('No drive folder id found for podcast %s — skipping', podcast_name)
            continue

        files = uploader.list_files(folder_id=drive_folder_id, max_results=1000)
        LOG.info('Found %d files in Drive folder for %s', len(files), podcast_name)

        for f in files:
            # Skip folders
            if f.get('mimeType') == 'application/vnd.google-apps.folder':
                continue

            file_id = f.get('id')
            file_name = f.get('name')
            file_size_raw = f.get('size')
            try:
                file_size = int(file_size_raw) if file_size_raw is not None else None
            except Exception:
                file_size = None

            if db_has_file(db, file_id, podcast_name, file_name):
                LOG.debug('Already in DB: %s (%s)', file_name, file_id)
                continue

            # Insert into DB
            episode_url = f"drive://{file_id}"
            try:
                db.add_episode(
                    podcast_name=podcast_name,
                    episode_title=file_name,
                    episode_url=episode_url,
                    episode_guid=None,
                    published_date=f.get('createdTime'),
                    file_path=None,
                    drive_file_id=file_id,
                    file_size=file_size
                )
                added_count += 1
                added_items.append({'podcast': podcast_name, 'title': file_name, 'id': file_id})
                LOG.info('Added to DB: %s (%s)', file_name, file_id)
            except Exception as e:
                LOG.error('Failed to add %s (%s) to DB: %s', file_name, file_id, e)

    LOG.info('Sync complete — added %d files', added_count)
    if added_items:
        LOG.info('Added items:')
        for it in added_items:
            LOG.info(' - %s / %s', it['podcast'], it['title'])


if __name__ == '__main__':
    main()
