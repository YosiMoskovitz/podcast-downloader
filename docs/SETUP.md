# Podcast Downloader - Setup Guide

## Quick Start: Local Development

### 1. Install PostgreSQL

Download from: https://www.postgresql.org/download/windows/

**Installation Settings:**
- Password: Choose and remember it!
- Port: 5432 (default)
- Components: All (Server, pgAdmin, Command Line Tools)

### 2. Create Database

**Option A - Using pgAdmin (GUI):**
1. Open pgAdmin from Start Menu
2. Enter your password
3. Right-click "Databases" → Create → Database
4. Name: `podcast_downloader`
5. Click Save

**Option B - Using Command Line:**
```powershell
psql -U postgres
CREATE DATABASE podcast_downloader;
\q
```

### 3. Configure Environment

Create a `.env` file in the project root:
```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/podcast_downloader
SECRET_KEY=your-random-secret-key
```

Replace `YOUR_PASSWORD` with your PostgreSQL password.

### 4. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 5. Setup Google Drive OAuth

See [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md) for detailed instructions.

Quick steps:
1. Create Google Cloud project
2. Enable Google Drive API
3. Create OAuth credentials (Desktop app)
4. Download credentials.json to `config/credentials.json`
5. Run OAuth flow via dashboard at http://localhost:5000/gdrive

### 6. Configure Podcasts

Edit `config/podcasts.json`:
```json
{
  "podcasts": [
    {
      "name": "My Podcast",
      "rss_url": "https://feeds.example.com/podcast.rss",
      "folder_name": "My Podcast",
      "enabled": true,
      "keep_count": -1
    }
  ],
  "settings": {
    "check_interval_hours": 6
  }
}
```

### 7. Run the Application

**Dashboard:**
```powershell
python -m flask --app dashboard.app run
```

**Worker (podcast downloader):**
```powershell
python main.py
```

Visit: http://localhost:5000

## Troubleshooting

### PostgreSQL Connection Issues

**"Connection refused":**
```powershell
# Check if service is running
Get-Service postgresql-x64-*

# Start if stopped
Start-Service postgresql-x64-16
```

**"Authentication failed":**
- Verify password in DATABASE_URL
- No extra spaces in .env file

**"Database does not exist":**
- Create the database (see Step 2)

### Google Drive Issues

**"Credentials not found":**
- Place credentials.json in `config/` folder
- Or upload via dashboard at `/gdrive`

**"Token expired":**
- Re-run OAuth flow via dashboard
- Token is automatically saved to database

## Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for cloud deployment instructions.
