import json
import os
import base64
from typing import Dict, List, Any, Optional

class Config:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        # Try environment variable first, fall back to file
        self.podcasts_config = self._load_podcasts_config()
        # Initialize database connection for settings (lazy load)
        self._db = None
        
    def _load_podcasts_config(self) -> Dict[str, Any]:
        """Load podcast configuration from environment variable or JSON file."""
        # Try environment variable first (for cloud deployment)
        podcasts_json = os.environ.get('PODCASTS_CONFIG')
        if podcasts_json:
            try:
                return json.loads(podcasts_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in PODCASTS_CONFIG environment variable: {e}")
        
        # Fall back to local file (for development)
        config_path = os.path.join(self.config_dir, "podcasts.json")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # Return default empty config if neither exists
            return {"podcasts": [], "settings": {}}
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
    
    def _get_db(self):
        """Lazy load database connection for settings."""
        if self._db is None:
            try:
                from database import PodcastDatabase
                self._db = PodcastDatabase()
            except Exception:
                # Database not available
                self._db = False
        return self._db if self._db is not False else None
    
    def get_podcasts(self) -> List[Dict[str, Any]]:
        """Get list of enabled podcasts."""
        return [
            podcast for podcast in self.podcasts_config.get("podcasts", [])
            if podcast.get("enabled", True)
        ]
    
    def get_settings(self) -> Dict[str, Any]:
        """Get general settings."""
        return self.podcasts_config.get("settings", {})
    
    def get_check_interval_hours(self) -> int:
        """Get check interval in hours."""
        return self.get_settings().get("check_interval_hours", 6)
    
    def get_max_episodes_per_check(self) -> int:
        """Get maximum episodes to download per check."""
        return self.get_settings().get("max_episodes_per_check", 5)
    
    def get_download_quality(self) -> str:
        """Get preferred download quality."""
        return self.get_settings().get("download_quality", "high")
    
    def get_credentials_json(self) -> Dict[str, Any]:
        """Get Google Drive credentials from environment variable, database, or file.
        
        Priority: env var (base64) > env var (json) > database > file
        Returns credentials as a dictionary.
        """
        # 1. Try environment variable first (base64 encoded for cloud deployment)
        creds_b64 = os.environ.get('GOOGLE_CREDENTIALS_BASE64')
        if creds_b64:
            try:
                creds_json = base64.b64decode(creds_b64).decode('utf-8')
                return json.loads(creds_json)
            except Exception as e:
                raise ValueError(f"Invalid GOOGLE_CREDENTIALS_BASE64: {e}")
        
        # 2. Try plain JSON environment variable
        creds_json = os.environ.get('GOOGLE_CREDENTIALS')
        if creds_json:
            try:
                return json.loads(creds_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid GOOGLE_CREDENTIALS JSON: {e}")
        
        # 3. Try database (for dashboard uploads in production)
        db = self._get_db()
        if db:
            try:
                creds_str = db.get_setting('google_credentials')
                if creds_str:
                    return json.loads(creds_str)
            except Exception:
                pass  # Fall through to file
        
        # 4. Fall back to file (for development)
        credentials_path = os.path.join(self.config_dir, "credentials.json")
        if os.path.exists(credentials_path):
            with open(credentials_path, 'r') as f:
                return json.load(f)
        
        raise ValueError("No Google credentials found. Set GOOGLE_CREDENTIALS_BASE64 environment variable or upload via dashboard.")
    
    def get_token_json(self) -> Dict[str, Any]:
        """Get OAuth token from environment variable, database, or file.
        
        Priority: env var (base64) > env var (json) > database > file
        """
        # 1. Try environment variable first
        token_b64 = os.environ.get('GOOGLE_TOKEN_BASE64')
        if token_b64:
            try:
                token_json = base64.b64decode(token_b64).decode('utf-8')
                return json.loads(token_json)
            except Exception as e:
                raise ValueError(f"Invalid GOOGLE_TOKEN_BASE64: {e}")
        
        # 2. Try plain JSON environment variable
        token_json = os.environ.get('GOOGLE_TOKEN')
        if token_json:
            try:
                return json.loads(token_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid GOOGLE_TOKEN JSON: {e}")
        
        # 3. Try database (for dashboard uploads in production)
        db = self._get_db()
        if db:
            try:
                token_str = db.get_setting('google_token')
                if token_str:
                    return json.loads(token_str)
            except Exception:
                pass  # Fall through to file
        
        # 4. Fall back to file (JSON format only, for development)
        token_path = 'token.json'
        if os.path.exists(token_path):
            try:
                with open(token_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise ValueError(f"Failed to load token from {token_path}: {e}")
        
        return None  # No token available yet
    
    def credentials_exist(self) -> bool:
        """Check if credentials are available (from env or file)."""
        try:
            self.get_credentials_json()
            return True
        except ValueError:
            return False
