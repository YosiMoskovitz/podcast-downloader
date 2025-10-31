import os
import io
import json
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

def token_is_valid(credentials_json: dict, token_dict: dict = None) -> Tuple[bool, str]:
    """Check whether an existing token is valid for Drive access.

    Args:
        credentials_json: OAuth client credentials as dict
        token_dict: Token data as dict, or None
        
    Returns (True, message) if valid or refreshed successfully, otherwise (False, reason).
    This function will NOT launch an interactive OAuth flow.
    """
    try:
        if not credentials_json:
            return False, "No credentials provided"
        if not token_dict:
            return False, "No token provided"
        
        try:
            creds = Credentials.from_authorized_user_info(token_dict)
        except Exception as e:
            return False, f"Failed to load token: {e}"

        # If creds appears valid, try to refresh if expired
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                return False, f'Failed to refresh token: {e}'

        # Actually try a Google Drive API call
        try:
            service = build('drive', 'v3', credentials=creds)
            service.about().get(fields="user").execute()
            return True, 'Token is valid and API call succeeded'
        except Exception as e:
            return False, f'Token/API call failed: {e}'
    except Exception as e:
        return False, f'Error checking token: {e}'


class GoogleDriveUploader:
    def __init__(self, credentials_json: dict, token_dict: dict = None, db=None):
        """Initialize Google Drive uploader with credentials from config.
        
        Args:
            credentials_json: OAuth client credentials as dict
            token_dict: Token data as dict, or None (will trigger OAuth flow)
            db: Optional database instance for persisting refreshed tokens
        """
        self.credentials_json = credentials_json
        self.token_dict = token_dict
        self.db = db
        self.logger = logging.getLogger(__name__)
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Google Drive API using OAuth 2.0 user flow."""
        try:
            if not self.credentials_json:
                raise ValueError("No credentials provided")
            
            scopes = ['https://www.googleapis.com/auth/drive']
            creds = None
            
            # Try to use existing token
            if self.token_dict:
                try:
                    creds = Credentials.from_authorized_user_info(self.token_dict, scopes)
                except Exception as e:
                    self.logger.warning(f"Failed to load token: {e}. Will trigger OAuth login.")
                    creds = None
            
            # Refresh or get new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        # Update token_dict with refreshed credentials
                        self.token_dict = json.loads(creds.to_json())
                        self._save_token()
                    except Exception as e:
                        self.logger.warning(f"Failed to refresh token: {e}. Will trigger OAuth login.")
                        creds = None
                
                if not creds or not creds.valid:
                    # Write credentials to temp file for OAuth flow
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                        json.dump(self.credentials_json, f)
                        temp_creds_path = f.name
                    
                    try:
                        flow = InstalledAppFlow.from_client_secrets_file(temp_creds_path, scopes)
                        creds = flow.run_local_server(port=0)
                    finally:
                        # Clean up temp file
                        if os.path.exists(temp_creds_path):
                            os.remove(temp_creds_path)
                    
                    # Update token_dict with new credentials
                    self.token_dict = json.loads(creds.to_json())
                    self._save_token()
            
            self.service = build('drive', 'v3', credentials=creds)
            self.service.about().get(fields="user").execute()
            self.logger.info("Successfully authenticated with Google Drive API (OAuth user)")
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            raise
    
    def _save_token(self):
        """Save the current token to database if available."""
        if self.db and self.token_dict:
            try:
                self.db.set_setting('google_token', json.dumps(self.token_dict))
                self.logger.info("Token saved to database")
            except Exception as e:
                self.logger.warning(f"Failed to save token to database: {e}")
    
    def get_token_dict(self) -> dict:
        """Get the current token as a dictionary (for saving to env/config)."""
        return self.token_dict
    
    def create_folder(self, folder_name: str, parent_folder_id: str = None) -> Optional[str]:
        """Create a folder in Google Drive and return its ID."""
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_folder_id:
                folder_metadata['parents'] = [parent_folder_id]
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            self.logger.info(f"Created folder '{folder_name}' with ID: {folder_id}")
            return folder_id
            
        except HttpError as e:
            self.logger.error(f"Error creating folder '{folder_name}': {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error creating folder '{folder_name}': {e}")
            return None
    
    def find_folder(self, folder_name: str, parent_folder_id: str = None) -> Optional[str]:
        """Find a folder by name and return its ID."""
        try:
            # Escape single quotes in folder name for Google Drive API query
            escaped_name = folder_name.replace("'", "\\'")
            query = f"name='{escaped_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            if parent_folder_id:
                query += f" and '{parent_folder_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                folder_id = folders[0]['id']
                self.logger.info(f"Found folder '{folder_name}' with ID: {folder_id}")
                return folder_id
            else:
                self.logger.info(f"Folder '{folder_name}' not found")
                return None
                
        except HttpError as e:
            self.logger.error(f"Error searching for folder '{folder_name}': {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error searching for folder '{folder_name}': {e}")
            return None
    
    def get_or_create_folder(self, folder_name: str, parent_folder_id: str = None) -> Optional[str]:
        """Get existing folder or create new one."""
        folder_id = self.find_folder(folder_name, parent_folder_id)
        if folder_id:
            return folder_id
        else:
            return self.create_folder(folder_name, parent_folder_id)
    
    def upload_stream(self, file_stream: io.BytesIO, file_name: str, folder_id: str = None,
                     mime_type: str = 'application/octet-stream') -> Optional[Dict[str, Any]]:
        """Upload a file from a stream (no local file needed).
        
        Args:
            file_stream: BytesIO stream containing file data
            file_name: Name for the file in Google Drive
            folder_id: Optional parent folder ID
            mime_type: MIME type of the file
            
        Returns:
            Dict with file info or None on error
        """
        try:
            # Check if file already exists
            existing_file_id = self.find_file(file_name, folder_id)
            if existing_file_id:
                self.logger.info(f"File '{file_name}' already exists in Drive with ID: {existing_file_id}")
                return {
                    'id': existing_file_id,
                    'name': file_name,
                    'status': 'already_exists'
                }
            
            # Prepare file metadata
            file_metadata = {'name': file_name}
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            # Upload from stream
            media = MediaIoBaseUpload(file_stream, mimetype=mime_type, resumable=True)
            
            self.logger.info(f"Uploading file from stream: {file_name}")
            
            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,size,mimeType,webViewLink'
            )
            
            # Execute upload with progress tracking
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress % 10 == 0:  # Log every 10%
                        self.logger.debug(f"Upload progress: {progress}%")
            
            file_id = response.get('id')
            file_size = response.get('size')
            web_view_link = response.get('webViewLink')
            
            self.logger.info(f"Successfully uploaded '{file_name}' with ID: {file_id}")
            
            return {
                'id': file_id,
                'name': file_name,
                'size': file_size,
                'url': web_view_link,
                'status': 'uploaded'
            }
            
        except HttpError as e:
            self.logger.error(f"HTTP error uploading stream for {file_name}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error uploading stream for {file_name}: {e}")
            return None
    
    def find_file(self, file_name: str, folder_id: str = None) -> Optional[str]:
        """Find a file by name and return its ID."""
        try:
            # Escape single quotes in file name for Google Drive API query
            escaped_name = file_name.replace("'", "\\'")
            query = f"name='{escaped_name}' and trashed=false"
            
            if folder_id:
                query += f" and '{folder_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                return files[0]['id']
            else:
                return None
                
        except HttpError as e:
            self.logger.error(f"Error searching for file '{file_name}': {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error searching for file '{file_name}': {e}")
            return None
    
    def delete_file(self, file_id: str) -> bool:
        """Delete a file from Google Drive."""
        try:
            self.service.files().delete(fileId=file_id).execute()
            self.logger.info(f"Deleted file with ID: {file_id}")
            return True
            
        except HttpError as e:
            self.logger.error(f"Error deleting file {file_id}: {e}")
            return False

    def rename_file(self, file_id: str, new_name: str) -> Optional[Dict[str, Any]]:
        """Rename a file in Google Drive. Returns the updated file metadata or None on error."""
        try:
            updated = self.service.files().update(
                fileId=file_id,
                body={'name': new_name},
                fields='id,name'
            ).execute()
            self.logger.info(f"Renamed file id={file_id} to '{new_name}'")
            return updated
        except HttpError as e:
            self.logger.error(f"HTTP error renaming file {file_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error renaming file {file_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error deleting file {file_id}: {e}")
            return False
    
    def list_files(self, folder_id: str = None, max_results: int = 100) -> List[Dict[str, Any]]:
        """List files in a folder or root directory."""
        try:
            query = "trashed=false"
            
            if folder_id:
                query += f" and '{folder_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, size, mimeType, createdTime, modifiedTime)"
            ).execute()
            
            return results.get('files', [])
            
        except HttpError as e:
            self.logger.error(f"Error listing files: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error listing files: {e}")
            return []
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get Google Drive storage information."""
        try:
            about = self.service.about().get(
                fields="storageQuota,user"
            ).execute()
            
            storage_quota = about.get('storageQuota', {})
            user_info = about.get('user', {})
            
            return {
                'total_storage': int(storage_quota.get('limit', 0)),
                'used_storage': int(storage_quota.get('usage', 0)),
                'available_storage': int(storage_quota.get('limit', 0)) - int(storage_quota.get('usage', 0)),
                'user_email': user_info.get('emailAddress', 'Unknown')
            }
            
        except HttpError as e:
            self.logger.error(f"Error getting storage info: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error getting storage info: {e}")
            return {}
    
    def _get_mime_type(self, file_path: Path) -> str:
        """Get MIME type based on file extension."""
        extension = file_path.suffix.lower()
        
        mime_types = {
            '.mp3': 'audio/mpeg',
            '.mp4': 'audio/mp4',
            '.m4a': 'audio/mp4',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.aac': 'audio/aac',
            '.flac': 'audio/flac'
        }
        
        return mime_types.get(extension, 'application/octet-stream')
    
    def setup_podcast_folders(self, podcast_names: List[str], 
                            root_folder_name: str = "Podcasts") -> Dict[str, str]:
        """Set up folder structure for podcasts."""
        folder_mapping = {}
        
        try:
            # Create or get root podcasts folder
            root_folder_id = self.get_or_create_folder(root_folder_name)
            if not root_folder_id:
                self.logger.error("Failed to create root podcasts folder")
                return folder_mapping
            
            folder_mapping['_root'] = root_folder_id
            
            # Create folder for each podcast
            for podcast_name in podcast_names:
                folder_id = self.get_or_create_folder(podcast_name, root_folder_id)
                if folder_id:
                    folder_mapping[podcast_name] = folder_id
                    self.logger.info(f"Set up folder for podcast: {podcast_name}")
                else:
                    self.logger.error(f"Failed to create folder for podcast: {podcast_name}")
            
            return folder_mapping
            
        except Exception as e:
            self.logger.error(f"Error setting up podcast folders: {e}")
            return folder_mapping
