#!/usr/bin/env python3
"""
Podcast Downloader and Google Drive Uploader Service

This service automatically downloads podcast episodes from RSS feeds
and uploads them to Google Drive in organized folders.
"""

import os
import sys
import logging
import schedule
import time
import io
from datetime import datetime
from typing import List, Dict, Any
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from config import Config
from database import PodcastDatabase
from feed_parser import PodcastFeedParser
from podcast_downloader import PodcastDownloader
from google_drive_uploader import GoogleDriveUploader, token_is_valid

class PodcastService:
    def __init__(self):
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        
        try:
            # Initialize components
            self.config = Config()
            self.database = PodcastDatabase()
            self.feed_parser = PodcastFeedParser()
            # No download_dir = streaming mode (cloud deployment)
            # With download_dir = local mode (development)
            download_dir = os.environ.get('DOWNLOAD_DIR', None)
            self.downloader = PodcastDownloader(download_dir=download_dir)
            
            # Initialize Google Drive uploader with credentials from config
            self.drive_uploader = None
            if self.config.credentials_exist():
                try:
                    credentials = self.config.get_credentials_json()
                    token = self.config.get_token_json()
                    
                    # Validate token if exists
                    if token:
                        valid, msg = token_is_valid(credentials, token)
                        if not valid:
                            self.logger.warning(f"Token invalid: {msg}. Will attempt to refresh on first use.")
                    
                    # Pass database instance for token persistence
                    self.drive_uploader = GoogleDriveUploader(credentials, token, db=self.database)
                    self.logger.info("Google Drive uploader initialized")
                except Exception as e:
                    self.logger.warning(f"Failed to initialize Drive uploader: {e}")
                    self.logger.info("Upload functionality disabled until Drive is authenticated via dashboard.")
            else:
                self.logger.warning("Google Drive credentials not found. Upload functionality disabled.")
                self.logger.info("Set GOOGLE_CREDENTIALS_BASE64 or GOOGLE_CREDENTIALS environment variable.")
            
            self.logger.info("Podcast service initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize podcast service: {e}")
            raise
    
    def setup_logging(self):
        """Configure logging for the application."""
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Create a stream handler with UTF-8 encoding and error handling for Windows console
        stream_handler = logging.StreamHandler(sys.stdout)
        # Set errors='replace' to handle characters that can't be encoded
        if hasattr(stream_handler.stream, 'reconfigure'):
            # Python 3.7+ on Windows - reconfigure stream to UTF-8
            try:
                stream_handler.stream.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                # If reconfigure fails, the handler will use default encoding with error handling
                pass
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/podcast_service.log', encoding='utf-8'),
                stream_handler
            ]
        )
    
    def log_run_history(self, run_type: str, status: str, message: str = None):
        """Log a run to the run_history table in the database."""
        try:
            conn = self.database._get_connection()
            cursor = conn.cursor()
            
            # Ensure table exists
            cursor.execute('''CREATE TABLE IF NOT EXISTS run_history (
                id SERIAL PRIMARY KEY,
                timestamp TEXT NOT NULL,
                run_type TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT
            )''')
            
            # Insert run record
            timestamp = datetime.now().isoformat()
            cursor.execute('INSERT INTO run_history (timestamp, run_type, status, message) VALUES (%s, %s, %s, %s)',
                     (timestamp, run_type, status, message))
            
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Error logging run history: {e}")
    
    def process_podcasts(self):
        """Main method to process all configured podcasts."""
        self.logger.info("Starting podcast processing...")
        self.log_run_history('process', 'started', 'Starting podcast processing')
        
        podcasts = self.config.get_podcasts()
        if not podcasts:
            self.logger.warning("No podcasts configured")
            self.log_run_history('process', 'completed', 'No podcasts configured')
            return
        
        # Setup Google Drive folders if uploader is available
        folder_mapping = {}
        if self.drive_uploader:
            podcast_names = [podcast['folder_name'] for podcast in podcasts]
            folder_mapping = self.drive_uploader.setup_podcast_folders(podcast_names)
        
        total_downloaded = 0
        total_uploaded = 0
        errors = []
        
        for podcast_config in podcasts:
            try:
                result = self.process_single_podcast(podcast_config, folder_mapping)
                total_downloaded += result.get('downloaded', 0)
                total_uploaded += result.get('uploaded', 0)
                
            except Exception as e:
                error_msg = f"Error processing podcast {podcast_config.get('name', 'Unknown')}: {e}"
                self.logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        status_msg = f"Downloaded: {total_downloaded}, Uploaded: {total_uploaded}"
        if errors:
            status_msg += f", Errors: {len(errors)}"
        
        self.logger.info(f"Processing complete. {status_msg}")
        self.log_run_history('process', 'completed', status_msg)
        self.log_statistics()
    
    def process_single_podcast(self, podcast_config: Dict[str, Any], 
                             folder_mapping: Dict[str, str]) -> Dict[str, int]:
        """Process a single podcast."""
        podcast_name = podcast_config['name']
        rss_url = podcast_config['rss_url']
        folder_name = podcast_config['folder_name']
        
        self.logger.info(f"Processing podcast: {podcast_name}")
        
        # Update podcast metadata in database
        drive_folder_id = folder_mapping.get(folder_name)
        # Pass keep_count from config (if present) into the DB record as well
        # Convert None to -1 for consistency (keep all)
        keep_count = podcast_config.get('keep_count')
        if keep_count is None:
            keep_count = -1
        self.database.add_or_update_podcast(
            podcast_name, rss_url, folder_name, drive_folder_id, keep_count
        )
        
        downloaded_count = 0
        uploaded_count = 0
        
        try:
            # Get latest episodes (fetch all, then sort and take 5)
            episodes = self.feed_parser.get_latest_episodes(rss_url, 50)  # fetch more to ensure we have enough
            if not episodes:
                self.logger.warning(f"No episodes found for {podcast_name}")
                return {'downloaded': 0, 'uploaded': 0}

            # Always sort and take the latest 5
            episodes = self.downloader.get_latest_episodes(episodes)
            self.logger.info(f"Processing {len(episodes)} latest episodes for {podcast_name}")


            # Reverse episodes so oldest is first, newest is last
            episodes_reversed = list(reversed(episodes))
            episode_records = []
            for episode in episodes_reversed:
                # Check if episode already exists
                if self.database.episode_exists(
                    episode_url=episode.get('audio_url'),
                    episode_guid=episode.get('guid')
                ):
                    self.logger.debug(f"Episode already exists: {episode.get('title', 'Unknown')}")
                    continue

                # Add to database first to get the id and podcast_seq
                episode_id = self.database.add_episode(
                    podcast_name=podcast_name,
                    episode_title=episode.get('title', ''),
                    episode_url=episode.get('audio_url', ''),
                    episode_guid=episode.get('guid', ''),
                    published_date=episode.get('published', ''),
                    file_path=None,  # Not downloaded yet
                    file_size=None
                )
                episode['db_id'] = episode_id
                # Fetch the inserted row to get the per-podcast sequence (podcast_seq)
                try:
                    ep_row = self.database.get_episode_by_id(episode_id)
                    if ep_row and 'podcast_seq' in ep_row:
                        episode['podcast_seq'] = ep_row.get('podcast_seq')
                except Exception:
                    # If something goes wrong, continue without podcast_seq (fallbacks exist)
                    pass
                episode_records.append({'episode': episode, 'db_id': episode_id})

            # Assign upload_num (1 for oldest, 5 for newest)
            for idx, rec in enumerate(episode_records):
                rec['episode']['upload_num'] = idx + 1

            # Download and upload in upload order (oldest to newest)
            for rec in episode_records:
                episode = rec['episode']
                episode_id = rec['db_id']
                
                # Stream download (no local file)
                stream_result = self.downloader.download_episode_stream(episode, podcast_name)
                if stream_result:
                    stream, filename, file_size = stream_result
                    downloaded_count += 1
                    
                    # Upload to Google Drive if available
                    if self.drive_uploader and drive_folder_id:
                        # Ensure Drive filename is prefixed with the podcast sequence
                        try:
                            # Remove any existing numeric prefix like "123-" so we normalize to podcast_seq
                            rest = filename
                            if '-' in filename:
                                first, rest_candidate = filename.split('-', 1)
                                if first.isdigit():
                                    rest = rest_candidate

                            prefix_for_drive = episode.get('podcast_seq') or episode.get('upload_num') or episode.get('db_id')
                            custom_drive_name = f"{prefix_for_drive}-{rest}" if prefix_for_drive is not None else filename
                        except Exception:
                            # Fallback to using the original filename if anything goes wrong
                            custom_drive_name = filename

                        # Determine MIME type from filename
                        mime_type = self._get_mime_type_from_filename(custom_drive_name)
                        
                        # Upload stream directly to Google Drive
                        upload_result = self.drive_uploader.upload_stream(
                            stream,
                            custom_drive_name,
                            drive_folder_id,
                            mime_type
                        )
                        
                        if upload_result:
                            uploaded_count += 1
                            # Update database with Drive info
                            drive_file_id = upload_result['id']
                            drive_file_url = upload_result.get('url') or f'https://drive.google.com/file/d/{drive_file_id}/view'
                            self.database.update_episode_drive_info(
                                episode_id, drive_file_id, drive_file_url
                            )
                            self.logger.info(f"Uploaded to Google Drive: {episode.get('title', 'Unknown')}")
                        else:
                            self.logger.error(f"Failed to upload: {episode.get('title', 'Unknown')}")
                    else:
                        self.logger.warning(f"Drive uploader not available, skipping upload for: {episode.get('title', 'Unknown')}")
                else:
                    self.logger.error(f"Failed to download: {episode.get('title', 'Unknown')}")

            self.logger.info(f"Completed {podcast_name}: {downloaded_count} downloaded, {uploaded_count} uploaded")

            # After uploads: enforce retention policy (keep_count)
            try:
                # Determine keep_count: prefer config value, else DB value, else -1 (keep all)
                cfg_keep = podcast_config.get('keep_count')
                db_pod = self.database.get_podcast(podcast_name)
                db_keep = db_pod.get('keep_count') if db_pod else None
                
                # Parse effective keep_count value
                effective_keep = None
                if cfg_keep is not None:
                    try:
                        effective_keep = int(cfg_keep)
                    except (ValueError, TypeError):
                        effective_keep = None
                elif db_keep is not None:
                    try:
                        effective_keep = int(db_keep)
                    except (ValueError, TypeError):
                        effective_keep = None

                # Only enforce retention if keep_count is set and > 0 (not -1 = keep all)
                if effective_keep is not None and effective_keep > 0 and self.drive_uploader:
                    self.logger.info(f"Enforcing retention for '{podcast_name}': keeping {effective_keep} newest episodes in Drive")
                    drive_episodes = self.database.get_episodes_with_drive(podcast_name)
                    
                    # drive_episodes is ordered newest first; calculate how many to remove
                    total_episodes = len(drive_episodes)
                    episodes_to_remove = drive_episodes[effective_keep:]
                    
                    if episodes_to_remove:
                        self.logger.info(f"Found {total_episodes} episodes in Drive, removing {len(episodes_to_remove)} old episode(s)")
                        for ep in episodes_to_remove:
                            file_id = ep.get('drive_file_id')
                            ep_id = ep.get('id')
                            if file_id:
                                try:
                                    deleted = self.drive_uploader.delete_file(file_id)
                                    if deleted:
                                        self.database.mark_episode_in_drive(ep_id, False)
                                        self.logger.info(f"Removed old episode id={ep_id} from Drive (file id={file_id})")
                                    else:
                                        self.logger.error(f"Failed to remove episode id={ep_id} from Drive (file id={file_id})")
                                except Exception as e:
                                    self.logger.error(f"Error removing episode id={ep_id}: {e}")
                    else:
                        self.logger.info(f"Retention check: {total_episodes} episode(s) in Drive, all within limit of {effective_keep}")
                elif effective_keep == -1 or effective_keep is None:
                    self.logger.debug(f"Retention policy for '{podcast_name}': keep all episodes (keep_count={effective_keep})")
            except Exception as e:
                self.logger.error(f"Error enforcing retention for {podcast_name}: {e}")

        except Exception as e:
            self.logger.error(f"Error processing episodes for {podcast_name}: {e}")

        return {'downloaded': downloaded_count, 'uploaded': uploaded_count}
    
    def log_statistics(self):
        """Log service statistics."""
        try:
            # Database stats
            db_stats = self.database.get_stats()
            self.logger.info(f"Database stats: {db_stats['total_episodes']} episodes, "
                           f"{db_stats['total_podcasts']} podcasts, "
                           f"{db_stats['total_size_bytes'] / (1024*1024):.1f} MB")
            
            # Download stats
            download_stats = self.downloader.get_download_stats()
            self.logger.info(f"Download stats: {download_stats['total_files']} files, "
                           f"{download_stats['total_size'] / (1024*1024):.1f} MB")
            
            # Google Drive stats (if available)
            if self.drive_uploader:
                storage_info = self.drive_uploader.get_storage_info()
                if storage_info:
                    used_gb = storage_info['used_storage'] / (1024**3)
                    total_gb = storage_info['total_storage'] / (1024**3)
                    self.logger.info(f"Google Drive: {used_gb:.1f} GB used of {total_gb:.1f} GB")
                    
        except Exception as e:
            self.logger.error(f"Error getting statistics: {e}")
    
    def _get_mime_type_from_filename(self, filename: str) -> str:
        """Get MIME type based on file extension."""
        extension = filename.lower().split('.')[-1] if '.' in filename else ''
        
        mime_types = {
            'mp3': 'audio/mpeg',
            'mp4': 'audio/mp4',
            'm4a': 'audio/mp4',
            'wav': 'audio/wav',
            'ogg': 'audio/ogg',
            'aac': 'audio/aac',
            'flac': 'audio/flac'
        }
        
        return mime_types.get(extension, 'application/octet-stream')
    
    def run_once(self):
        """Run the service once."""
        self.logger.info("Running podcast service once...")
        self.log_run_history('manual', 'started', 'Manual run (--once)')
        try:
            self.process_podcasts()
            self.log_run_history('manual', 'completed', 'Manual run completed successfully')
            return 0  # Success
        except Exception as e:
            self.logger.error(f"Error in run_once: {e}")
            self.log_run_history('manual', 'error', f'Manual run failed: {str(e)}')
            raise  # Re-raise the exception so the caller knows it failed
    
    def run_scheduled(self):
        """Run the service on a schedule."""
        interval_hours = self.config.get_check_interval_hours()
        self.logger.info(f"Starting scheduled service (every {interval_hours} hours)")
        self.log_run_history('scheduled', 'started', f'Scheduled service started (every {interval_hours} hours)')
        
        # Schedule the job
        schedule.every(interval_hours).hours.do(self.process_podcasts)
        
        # Also run once immediately
        self.process_podcasts()
        # Track last-known config modified timestamp from dashboard
        self._dashboard_config_mtime = None

        # Keep running
        while True:
            try:
                schedule.run_pending()

                # Poll dashboard API for podcasts config last-modified timestamp
                try:
                    resp = requests.get('http://127.0.0.1:5000/api/podcasts/last_modified', timeout=2)
                    if resp.status_code == 200:
                        last_mod = resp.json().get('last_modified')
                        if last_mod and last_mod != self._dashboard_config_mtime:
                            self.logger.info(f"Detected podcasts config change (dashboard). Reloading config: {last_mod}")
                            try:
                                self.config = Config()  # reload config from file
                                self._dashboard_config_mtime = last_mod
                            except Exception as e:
                                self.logger.error(f"Failed to reload config: {e}")
                except Exception:
                    # Dashboard may not be running; ignore polling errors
                    pass

            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")

            time.sleep(60)  # Check every minute

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Podcast Downloader and Google Drive Uploader')
    parser.add_argument('--once', action='store_true', 
                       help='Run once instead of on schedule')
    parser.add_argument('--stats', action='store_true',
                       help='Show statistics and exit')

    args = parser.parse_args()

    try:
        service = PodcastService()

        if args.stats:
            service.log_statistics()
            sys.exit(0)
        elif args.once:
            exit_code = service.run_once()
            sys.exit(exit_code)
        else:
            service.run_scheduled()
            sys.exit(0)

    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
