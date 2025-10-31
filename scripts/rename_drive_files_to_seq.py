"""
Rename existing Google Drive files to the `{podcast_seq}-{rest}` convention.

Dry-run by default: shows proposed renames. Use --apply to actually rename files.
Optionally pass --podcast "Podcast Name" to limit to a single podcast.
"""
import os
import sys
import argparse
import sqlite3

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.google_drive_uploader import GoogleDriveUploader
from src.database import PodcastDatabase


def strip_leading_numeric_prefix(name: str) -> str:
    if not name:
        return name
    if '-' in name:
        first, rest = name.split('-', 1)
        if first.isdigit():
            return rest
    return name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Perform the renames on Drive')
    parser.add_argument('--podcast', help='Limit to a single podcast name')
    args = parser.parse_args()

    creds_path = os.path.join(ROOT, 'config', 'credentials.json')
    token_path = os.path.join(ROOT, 'token.json')
    db_path = os.path.join(ROOT, 'podcast_data.db')

    if not os.path.exists(creds_path):
        print('Google credentials not found at', creds_path)
        return
    if not os.path.exists(db_path):
        print('Database not found at', db_path)
        return

    uploader = GoogleDriveUploader(credentials_path=creds_path, token_path=token_path)
    db = PodcastDatabase(db_path=db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    query = 'SELECT id, podcast_name, episode_title, drive_file_id, podcast_seq FROM episodes WHERE drive_file_id IS NOT NULL'
    params = ()
    if args.podcast:
        query += ' AND podcast_name = ?'
        params = (args.podcast,)

    cur.execute(query, params)
    rows = cur.fetchall()

    to_rename = []
    for row in rows:
        ep_id, podcast_name, ep_title, drive_id, podcast_seq = row
        if not podcast_seq:
            # If no podcast_seq, skip — you should backfill first
            continue
        try:
            # Fetch current Drive file metadata to get its actual name
            meta = uploader.service.files().get(fileId=drive_id, fields='name').execute()
            current_name = meta.get('name')
        except Exception as e:
            print(f"Failed to fetch metadata for file id={drive_id}: {e}")
            continue

        rest = strip_leading_numeric_prefix(current_name)
        desired_name = f"{podcast_seq}-{rest}"
        if current_name != desired_name:
            to_rename.append({
                'episode_id': ep_id,
                'podcast': podcast_name,
                'drive_id': drive_id,
                'current_name': current_name,
                'desired_name': desired_name
            })

    if not to_rename:
        print('No files require renaming.')
        return

    print(f'Found {len(to_rename)} files that would be renamed:')
    for t in to_rename:
        print(f"[{t['podcast']}] {t['current_name']} -> {t['desired_name']} (drive id={t['drive_id']})")

    if not args.apply:
        print('\nDry-run complete. Re-run with --apply to perform the renames.')
        return

    # Apply renames
    applied = 0
    for t in to_rename:
        res = uploader.rename_file(t['drive_id'], t['desired_name'])
        if res:
            applied += 1
        else:
            print(f"Failed to rename: {t['drive_id']}")

    print(f'Applied renames: {applied}/{len(to_rename)}')


if __name__ == '__main__':
    main()
