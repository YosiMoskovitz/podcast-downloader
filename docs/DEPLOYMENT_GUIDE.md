# Deployment Guide - Railway & Render

## Prerequisites

- PostgreSQL database (provided by platform)
- Google Drive OAuth credentials
- Podcast configuration

## Environment Variables Required

### Essential Variables

```env
DATABASE_URL=postgresql://user:pass@host:5432/dbname
SECRET_KEY=random-secret-string-here
PODCASTS_CONFIG={"podcasts":[...],"settings":{...}}
```

### Optional: Google Credentials as Environment Variables

If not using dashboard upload, encode credentials:

```bash
python scripts/encode_credentials.py
```

Then set:
```env
GOOGLE_CREDENTIALS_BASE64=<base64-encoded-credentials>
GOOGLE_TOKEN_BASE64=<base64-encoded-token>
```

### Podcast Configuration Example

```json
{
  "podcasts": [
    {
      "name": "My Podcast",
      "rss_url": "https://feeds.example.com/podcast.rss",
      "folder_name": "My Podcast Folder",
      "enabled": true,
      "keep_count": -1
    }
  ],
  "settings": {
    "check_interval_hours": 6
  }
}
```

## Railway Deployment

### 1. Create Project
1. Go to [Railway.app](https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Connect your repository

### 2. Add PostgreSQL Database
1. Click "New" → "Database" → "Add PostgreSQL"
2. Railway automatically sets `DATABASE_URL`

### 3. Configure Environment Variables
1. Click on your service
2. Go to "Variables" tab
3. Add required variables:
   - `SECRET_KEY`
   - `PODCASTS_CONFIG`
   - Optional: `GOOGLE_CREDENTIALS_BASE64`, `GOOGLE_TOKEN_BASE64`

### 4. Setup Worker Process
The `Procfile` defines two processes:
```
web: gunicorn dashboard.app:app --bind 0.0.0.0:$PORT --workers 2
worker: python main.py
```

Both processes will be automatically detected by Railway.

### 5. Deploy
- Railway auto-deploys on git push
- Web dashboard will be available at your Railway URL
- Worker runs in background processing podcasts

## Render Deployment

### 1. Create PostgreSQL Database
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New" → "PostgreSQL"
3. Choose free tier
4. Note the "Internal Database URL"

### 2. Create Web Service
1. Click "New" → "Web Service"
2. Connect your GitHub repository
3. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn dashboard.app:app --bind 0.0.0.0:$PORT --workers 2`

### 3. Create Background Worker
1. Click "New" → "Background Worker"
2. Connect same repository
3. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`

### 4. Set Environment Variables
In both services, add:
- `DATABASE_URL` (from PostgreSQL service)
- `SECRET_KEY`
- `PODCASTS_CONFIG`
- Optional: `GOOGLE_CREDENTIALS_BASE64`, `GOOGLE_TOKEN_BASE64`

### 5. Deploy
- Render auto-deploys on git push
- Web service provides dashboard
- Worker service processes podcasts

## Credentials Setup (Two Options)

### Option 1: Dashboard Upload (Recommended for Testing)

1. Deploy app without Google credentials
2. Visit your app's `/gdrive` page
3. Upload `credentials.json`
4. Complete OAuth flow
5. Credentials are saved to PostgreSQL database
6. **Note:** For production, convert to environment variables using the "Generate Environment Variables" button

### Option 2: Environment Variables (Recommended for Production)

1. **Locally, encode credentials:**
   ```bash
   python scripts/encode_credentials.py
   ```

2. **Copy the output and add to platform:**
   - `GOOGLE_CREDENTIALS_BASE64=...`
   - `GOOGLE_TOKEN_BASE64=...`

3. **Advantages:**
   - Persists across all deployments
   - More secure
   - No file storage needed

## Post-Deployment

### Initial Database Setup

The database tables are created automatically on first connection. No manual setup needed.

### Verify Deployment

1. Visit your web dashboard URL
2. Check `/gdrive` for Google Drive status
3. Check `/podcasts` to manage podcasts
4. Check logs for worker process

### Common Issues

**Worker not running:**
- Check logs in platform dashboard
- Verify `DATABASE_URL` is set correctly
- Ensure podcasts are enabled in config

**Credentials not persisting:**
- Use environment variables instead of dashboard upload
- Railway/Render have ephemeral filesystems

**Database connection errors:**
- Verify `DATABASE_URL` format
- Check database is running
- Ensure both web and worker use same `DATABASE_URL`

## Monitoring

Both platforms provide:
- Application logs
- Resource usage metrics
- Deployment history
- Environment variable management

Access these through your platform's dashboard.

## Updating

1. Push changes to your git repository
2. Platform auto-deploys new version
3. Database and environment variables persist
4. Zero-downtime deployment (on paid tiers)

## Cost

**Railway:**
- Free tier: $5 credit/month
- PostgreSQL + Web + Worker typically uses ~$3-5/month

**Render:**
- Free tier available
- Web service: Free (with limitations) or $7/month
- Worker: $7/month
- PostgreSQL: Free (90 days) then $7/month
