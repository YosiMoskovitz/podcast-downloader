import requests
import os
import io
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import logging
from urllib.parse import urlparse, unquote

class PodcastDownloader:
    def __init__(self, download_dir: str = None):
        """Initialize podcast downloader.
        
        Args:
            download_dir: Optional local download directory (for development only).
                         If None, will stream directly without saving locally.
        """
        self.download_dir = Path(download_dir) if download_dir else None
        if self.download_dir:
            self.download_dir.mkdir(exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_latest_episodes(self, episodes: list) -> list:
        """Parse episode dates, filter out unparseable, sort by date descending, and return the latest 5."""
        from dateutil import parser as dateparser
        eps_with_dates = []
        for ep in episodes:
            date_str = ep.get('published', '')
            parsed = None
            if date_str:
                try:
                    parsed = dateparser.parse(date_str)
                except Exception:
                    parsed = None
            if parsed:
                eps_with_dates.append((parsed, ep))
        eps_with_dates.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in eps_with_dates[:5]]
    
    def download_episode_stream(self, episode: Dict[str, Any], podcast_name: str) -> Optional[Tuple[io.BytesIO, str, int]]:
        """Download episode to memory as a stream (no local file).
        
        Args:
            episode: Episode dictionary with audio_url
            podcast_name: Name of the podcast
            
        Returns:
            Tuple of (BytesIO stream, filename, file_size) or None on error
        """
        audio_url = episode.get('audio_url')
        if not audio_url:
            self.logger.error(f"No audio URL found for episode: {episode.get('title', 'Unknown')}")
            return None
        
        try:
            # Generate filename
            filename = self._generate_filename(episode, audio_url)
            
            self.logger.info(f"Streaming: {episode.get('title', 'Unknown')} -> {filename}")
            
            # Download to memory stream
            stream_result = self._download_to_stream(audio_url)
            
            if stream_result:
                stream, file_size = stream_result
                self.logger.info(f"Successfully streamed: {filename} ({file_size} bytes)")
                return (stream, filename, file_size)
            else:
                self.logger.error(f"Failed to stream: {filename}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error streaming episode {episode.get('title', 'Unknown')}: {e}")
            return None
    
    def _download_to_stream(self, url: str, chunk_size: int = 8192) -> Optional[Tuple[io.BytesIO, int]]:
        """Download file directly to memory stream.
        
        Returns:
            Tuple of (BytesIO stream, file_size) or None on error
        """
        try:
            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Get total file size
            content_length = response.headers.get('content-length')
            total_size = int(content_length) if content_length else 0
            
            # Create in-memory stream
            stream = io.BytesIO()
            downloaded = 0
            
            # Download in chunks
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    stream.write(chunk)
                    downloaded += len(chunk)
                    
                    # Log progress
                    if total_size and downloaded % (1024 * 1024) == 0:  # Every MB
                        progress = (downloaded / total_size) * 100
                        self.logger.debug(f"Download progress: {progress:.1f}%")
            
            # Reset stream position to beginning
            stream.seek(0)
            
            return (stream, downloaded)
            
        except requests.RequestException as e:
            self.logger.error(f"Network error downloading from {url}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error downloading to stream from {url}: {e}")
            return None
    
    def _generate_filename(self, episode: Dict[str, Any], audio_url: str) -> str:
        """Generate a safe filename for the episode, using the database id as a prefix (highest is latest)."""
        parsed_url = urlparse(audio_url)
        path = unquote(parsed_url.path)
        extension = Path(path).suffix
        if not extension or len(extension) > 5:
            extension = '.mp3'
        title = episode.get('title', 'Untitled Episode')
        safe_title = self._sanitize_filename(title)
        # Use the per-podcast sequence id as a prefix if available
        # Fallback to upload_num then to db_id
        prefix = None
        if episode.get('podcast_seq') is not None:
            prefix = episode['podcast_seq']
        elif episode.get('upload_num') is not None:
            prefix = episode['upload_num']
        elif episode.get('db_id') is not None:
            prefix = episode['db_id']
        if prefix is not None:
            filename = f"{prefix}-{safe_title}{extension}"
        else:
            filename = f"{safe_title}{extension}"
        if len(filename) > 200:
            max_title_length = 200 - len(extension) - (len(str(prefix)) + 1 if prefix is not None else 0)
            safe_title = safe_title[:max_title_length]
            if prefix is not None:
                filename = f"{prefix}-{safe_title}{extension}"
            else:
                filename = f"{safe_title}{extension}"
        return filename
    
    def _sanitize_filename(self, filename: str) -> str:
        """Remove or replace characters that are invalid in filenames."""
        # Characters not allowed in Windows filenames
        invalid_chars = '<>:"/\\|?*'
        
        # Replace invalid characters with underscores
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Replace multiple spaces/underscores with single ones
        filename = ' '.join(filename.split())
        filename = '_'.join(part for part in filename.split('_') if part)
        
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        
        # Ensure filename is not empty
        if not filename:
            filename = 'untitled'
        
        return filename
    
    def get_download_stats(self) -> Dict[str, Any]:
        """Get statistics about downloaded files."""
        total_files = 0
        total_size = 0
        podcasts = {}
        
        # Return empty stats if no download directory (streaming mode)
        if not self.download_dir:
            return {
                'total_files': 0,
                'total_size': 0,
                'podcasts': {},
                'download_dir': None
            }
        
        try:
            for podcast_dir in self.download_dir.iterdir():
                if podcast_dir.is_dir():
                    podcast_name = podcast_dir.name
                    podcast_files = list(podcast_dir.glob('*'))
                    podcast_size = sum(f.stat().st_size for f in podcast_files if f.is_file())
                    
                    podcasts[podcast_name] = {
                        'file_count': len(podcast_files),
                        'total_size': podcast_size
                    }
                    
                    total_files += len(podcast_files)
                    total_size += podcast_size
        except Exception as e:
            self.logger.error(f"Error calculating download stats: {e}")
        
        return {
            'total_files': total_files,
            'total_size': total_size,
            'podcasts': podcasts,
            'download_dir': str(self.download_dir)
        }
    
    def __del__(self):
        """Close the session when the object is destroyed."""
        if hasattr(self, 'session'):
            self.session.close()
