# yt-dlp API for Railway

## Deploy to Railway

1. Go to [Railway](https://railway.app)
2. Create a new project → Deploy from GitHub repo or upload this folder
3. Or use Railway CLI:
   ```bash
   cd railway-ytdlp
   railway login
   railway init
   railway up
   ```
4. Set environment variable `API_KEY` to a secret token for authentication
5. Copy the Railway URL (e.g., `https://your-app.up.railway.app`)

## Endpoints

### POST /download
Download a video/audio with options.

### POST /formats
List all available formats for a URL.

### GET /health
Health check.

## Authentication
Set `API_KEY` env var. Pass it as `Authorization: Bearer <key>` header.
