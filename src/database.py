import psycopg2
import psycopg2.extras
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

class PodcastDatabase:
    def __init__(self, db_url: str = None):
        """Initialize database connection using PostgreSQL.
        
        Args:
            db_url: PostgreSQL connection string. If None, will use DATABASE_URL env var.
        """
        self.db_url = db_url or os.environ.get('DATABASE_URL')
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable must be set")
        self._create_tables()
    
    def _get_connection(self):
        """Get a new database connection."""
        return psycopg2.connect(self.db_url)
    
    def _create_tables(self):
        """Create necessary database tables if they don't exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Table for tracking downloaded episodes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS episodes (
                    id SERIAL PRIMARY KEY,
                    podcast_name TEXT NOT NULL,
                    episode_title TEXT NOT NULL,
                    episode_url TEXT NOT NULL UNIQUE,
                    episode_guid TEXT,
                    published_date TEXT,
                    downloaded_date TEXT NOT NULL,
                    file_path TEXT,
                    drive_file_id TEXT,
                    file_size BIGINT,
                    status TEXT DEFAULT 'downloaded',
                    in_drive INTEGER DEFAULT 0,
                    drive_file_url TEXT,
                    podcast_seq INTEGER
                )
            ''')
            
            # Table for podcast metadata
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS podcasts (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    rss_url TEXT NOT NULL,
                    folder_name TEXT NOT NULL,
                    last_checked TEXT,
                    drive_folder_id TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    keep_count INTEGER DEFAULT -1
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_episode_url ON episodes(episode_url)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_podcast_name ON episodes(podcast_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_episode_guid ON episodes(episode_guid)')
            
            # Table for storing application settings (including credentials)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
        finally:
            conn.close()
    
    def add_episode(self, podcast_name: str, episode_title: str, episode_url: str, 
                   episode_guid: str = None, published_date: str = None, 
                   file_path: str = None, drive_file_id: str = None, 
                   file_size: int = None, podcast_seq: int = None) -> int:
        """Add a new episode to the database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            downloaded_date = datetime.now().isoformat()

            # Compute podcast_seq if not provided: next sequential number for this podcast
            if podcast_seq is None:
                cursor.execute('SELECT MAX(podcast_seq) FROM episodes WHERE podcast_name = %s', (podcast_name,))
                row = cursor.fetchone()
                max_seq = row[0] if row and row[0] is not None else 0
                podcast_seq = max_seq + 1

            cursor.execute('''
                INSERT INTO episodes 
                (podcast_name, episode_title, episode_url, episode_guid, 
                 published_date, downloaded_date, file_path, drive_file_id, file_size, podcast_seq)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (podcast_name, episode_title, episode_url, episode_guid,
                  published_date, downloaded_date, file_path, drive_file_id, file_size, podcast_seq))

            episode_id = cursor.fetchone()[0]
            conn.commit()
            return episode_id
        finally:
            conn.close()
    
    def episode_exists(self, episode_url: str = None, episode_guid: str = None) -> bool:
        """Check if an episode already exists in the database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if episode_url:
                cursor.execute('SELECT 1 FROM episodes WHERE episode_url = %s', (episode_url,))
            elif episode_guid:
                cursor.execute('SELECT 1 FROM episodes WHERE episode_guid = %s', (episode_guid,))
            else:
                return False
            
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def get_episodes(self, podcast_name: str = None, limit: int = None) -> List[Dict[str, Any]]:
        """Get episodes from the database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            if podcast_name:
                query = 'SELECT * FROM episodes WHERE podcast_name = %s ORDER BY downloaded_date DESC'
                params = (podcast_name,)
            else:
                query = 'SELECT * FROM episodes ORDER BY downloaded_date DESC'
                params = ()
            
            if limit:
                query += f' LIMIT {limit}'
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_episode_by_id(self, episode_id: int) -> Optional[Dict[str, Any]]:
        """Return a single episode row by id."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT * FROM episodes WHERE id = %s', (episode_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    

    def update_episode_drive_info(self, episode_id: int, drive_file_id: str, drive_file_url: str):
        """Update the Google Drive file ID and URL for an episode."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Update drive id/url and mark as present in drive
            cursor.execute(
                'UPDATE episodes SET drive_file_id = %s, drive_file_url = %s, in_drive = 1 WHERE id = %s',
                (drive_file_id, drive_file_url, episode_id)
            )
            conn.commit()
        finally:
            conn.close()

    def mark_episode_in_drive(self, episode_id: int, in_drive: bool):
        """Set the in_drive flag for an episode (1 = present, 0 = deleted)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('UPDATE episodes SET in_drive = %s WHERE id = %s', (1 if in_drive else 0, episode_id))
            conn.commit()
        finally:
            conn.close()

    def get_episodes_with_drive(self, podcast_name: str) -> List[Dict[str, Any]]:
        """Return episodes for a podcast that have drive_file_id set, ordered newest first."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "SELECT id, drive_file_id, drive_file_url, downloaded_date FROM episodes "
                "WHERE podcast_name = %s AND drive_file_id IS NOT NULL AND in_drive = 1 "
                "ORDER BY downloaded_date DESC",
                (podcast_name,)
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
    
    def add_or_update_podcast(self, name: str, rss_url: str, folder_name: str, 
                             drive_folder_id: str = None, keep_count: int = None) -> int:
        """Add or update podcast metadata.
        
        Args:
            name: Podcast name
            rss_url: RSS feed URL
            folder_name: Folder name for organizing episodes
            drive_folder_id: Google Drive folder ID (optional)
            keep_count: Number of episodes to keep (-1 = keep all, None = keep all)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            last_checked = datetime.now().isoformat()
            # Ensure keep_count is never NULL: use -1 for "keep all"
            if keep_count is None:
                keep_count = -1
            cursor.execute('''
                INSERT INTO podcasts 
                (name, rss_url, folder_name, last_checked, drive_folder_id, keep_count)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    rss_url = EXCLUDED.rss_url,
                    folder_name = EXCLUDED.folder_name,
                    last_checked = EXCLUDED.last_checked,
                    drive_folder_id = EXCLUDED.drive_folder_id,
                    keep_count = EXCLUDED.keep_count
                RETURNING id
            ''', (name, rss_url, folder_name, last_checked, drive_folder_id, keep_count))
            
            podcast_id = cursor.fetchone()[0]
            conn.commit()
            return podcast_id
        finally:
            conn.close()
    
    def get_podcast(self, name: str) -> Optional[Dict[str, Any]]:
        """Get podcast metadata by name."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT * FROM podcasts WHERE name = %s', (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    
    def update_podcast_drive_folder_id(self, name: str, drive_folder_id: str):
        """Update the Google Drive folder ID for a podcast."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE podcasts SET drive_folder_id = %s WHERE name = %s',
                (drive_folder_id, name)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM episodes')
            total_episodes = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(DISTINCT podcast_name) FROM episodes')
            total_podcasts = cursor.fetchone()[0]
            
            cursor.execute('SELECT SUM(file_size) FROM episodes WHERE file_size IS NOT NULL')
            total_size = cursor.fetchone()[0] or 0
            
            return {
                'total_episodes': total_episodes,
                'total_podcasts': total_podcasts,
                'total_size_bytes': total_size
            }
        finally:
            conn.close()
    
    def set_setting(self, key: str, value: str):
        """Store or update an application setting."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = CURRENT_TIMESTAMP
            ''', (key, value))
            conn.commit()
        finally:
            conn.close()
    
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Retrieve an application setting."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM app_settings WHERE key = %s', (key,))
            row = cursor.fetchone()
            return row[0] if row else default
        finally:
            conn.close()
    
    def delete_setting(self, key: str):
        """Delete an application setting."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM app_settings WHERE key = %s', (key,))
            conn.commit()
        finally:
            conn.close()
