# Podcast Downloader and Google Drive Uploader

An automated service that downloads podcast episodes from RSS feeds and uploads them to Google Drive in organized folders.

## Features

- **Automated Downloads**: Downloads new episodes from configured podcast RSS feeds
- **Google Drive Integration**: Automatically uploads episodes to organized folders in Google Drive
- **Duplicate Detection**: Prevents downloading the same episode multiple times
- **Scheduling**: Runs on a configurable schedule to check for new episodes
- **Resume Downloads**: Can resume interrupted downloads
- **Storage Management**: Cleanup old files to manage storage space
- **Comprehensive Logging**: Detailed logs for monitoring and troubleshooting
- **Statistics**: Track download and upload statistics

## Project Structure

```
podcast-downloader/
├── src/
│   ├── config.py              # Configuration management
│   ├── database.py            # SQLite database operations
│   ├── feed_parser.py         # RSS feed parsing
│   ├── podcast_downloader.py  # Episode downloading
│   └── google_drive_uploader.py # Google Drive integration
├── config/
│   ├── podcasts.json          # Podcast configuration
│   └── credentials_template.json # Google Drive API credentials template
├── requirements.txt           # Python dependencies
├── main.py                   # Main application entry point
└── README.md                 # This file
```

## Setup Instructions

### 1. Install Dependencies

```bash
cd podcast-downloader
pip install -r requirements.txt
```

### 2. Configure Google Drive API

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Drive API
4. Create a service account:
   - Go to "IAM & Admin" > "Service Accounts"
   - Click "Create Service Account"
   - Fill in the details and create
   - Click on the service account and go to "Keys" tab
   - Click "Add Key" > "Create New Key" > "JSON"
   - Download the JSON file
5. Copy the downloaded JSON file to `config/credentials.json`
6. Share your Google Drive folder with the service account email address

### 3. Configure Podcasts

Edit `config/podcasts.json` to add your favorite podcasts:

```json
{
  "podcasts": [
    {
      "name": "Your Favorite Podcast",
      "rss_url": "https://feeds.example.com/your-podcast",
      "folder_name": "Your Podcast Folder",
      "enabled": true
    }
  ],
  "settings": {
    "check_interval_hours": 6,
    "max_episodes_per_check": 5,
    "download_quality": "high"
  }
}
```

## Usage

### Run Once (Test Mode)
```bash
python main.py --once
```

### Run on Schedule (Continuous Mode)
```bash
python main.py
```

### Show Statistics
```bash
python main.py --stats
```

### Clean Up Old Files
```bash
python main.py --cleanup 10  # Keep 10 most recent episodes per podcast
```

## Configuration Options

### Podcast Configuration (`config/podcasts.json`)

- **name**: Display name for the podcast
- **rss_url**: RSS feed URL
- **folder_name**: Folder name in Google Drive
- **enabled**: Whether to process this podcast

### Settings

- **check_interval_hours**: How often to check for new episodes (default: 6 hours)
- **max_episodes_per_check**: Maximum episodes to download per check (default: 5)
- **download_quality**: Preferred download quality (currently unused, for future enhancement)

## File Organization

### Local Storage
Episodes are downloaded to:
```
downloads/
├── Podcast Name 1/
│   ├── 2023-10-01 - Episode Title.mp3
│   └── 2023-10-02 - Another Episode.mp3
└── Podcast Name 2/
    └── 2023-10-01 - Episode Title.mp3
```

### Google Drive
Episodes are uploaded to:
```
Google Drive/
└── Podcasts/
    ├── Podcast Name 1/
    │   ├── 2023-10-01 - Episode Title.mp3
    │   └── 2023-10-02 - Another Episode.mp3
    └── Podcast Name 2/
        └── 2023-10-01 - Episode Title.mp3
```

## Database

The service uses SQLite to track:
- Downloaded episodes (prevents duplicates)
- Podcast metadata
- Google Drive file IDs
- Download statistics

Database file: `podcast_data.db`

## Logging

Logs are stored in the `logs/` directory:
- `podcast_service.log`: Main application log
- Console output for real-time monitoring

Log levels:
- INFO: General operations
- WARNING: Non-critical issues
- ERROR: Failed operations
- DEBUG: Detailed troubleshooting information

## Troubleshooting

### Common Issues

1. **Google Drive Authentication Failed**
   - Verify credentials.json is valid and in the correct location
   - Ensure the service account has access to your Google Drive
   - Check that the Google Drive API is enabled

2. **No Episodes Downloaded**
   - Verify RSS feed URLs are correct and accessible
   - Check if episodes already exist in the database
   - Review logs for specific error messages

3. **Download Failures**
   - Check internet connectivity
   - Verify podcast URLs are accessible
   - Some feeds may block automated downloads

4. **Upload Failures**
   - Check Google Drive storage quota
   - Verify folder permissions
   - Review Google Drive API quotas

### Debug Mode

For detailed debugging, modify the logging level in `main.py`:
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## Automation

### Windows Task Scheduler
1. Create a basic task
2. Set trigger (e.g., daily at specific time)
3. Action: Start a program
4. Program: `python`
5. Arguments: `"C:\path\to\podcast-downloader\main.py"`
6. Start in: `"C:\path\to\podcast-downloader"`

### Linux/macOS Cron
```bash
# Run every 6 hours
0 */6 * * * cd /path/to/podcast-downloader && python main.py --once
```

### Docker (Future Enhancement)
A Dockerfile could be added for containerized deployment.

## Security Considerations

- Keep `credentials.json` secure and never commit it to version control
- Service account should have minimal required permissions
- Consider using environment variables for sensitive configuration
- Regularly rotate service account keys

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is open source. Please check the license file for details.

## Future Enhancements

- Web interface for configuration and monitoring
- Support for podcast authentication
- Advanced filtering options
- Multiple cloud storage providers
- Podcast recommendations based on listening history
- Mobile app for remote monitoring
