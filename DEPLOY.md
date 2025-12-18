# CommProp Intel Map - Render Deployment Guide

## Quick Deploy to Render

### 1. Push to GitHub

```bash
# Initialize git if needed
git init
git add .
git commit -m "CommProp Intel Map - initial deploy"

# Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/commprop-intel.git
git push -u origin main
```

### 2. Deploy on Render

1. Go to [render.com](https://render.com) and sign up/login
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repo
4. Render will auto-detect `render.yaml` settings:
   - Name: `commprop-intel`
   - Runtime: Python
   - Build: `pip install -r requirements.txt && playwright install chromium && playwright install-deps`
   - Start: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`

### 3. Set Environment Variables

In Render dashboard → Environment:

| Key | Value |
|-----|-------|
| `GEMINI_API_KEY` | Your Google AI API key |

### 4. Set Up Daily Scraping (Cron Job)

Render offers [Cron Jobs](https://render.com/docs/cronjobs) for scheduled tasks.

1. In Render, create a new **Cron Job**
2. Connect same GitHub repo
3. Settings:
   - Schedule: `0 8 * * *` (8 AM daily)
   - Command: `python cron_daily_scrape.py 1`
4. Add same environment variables

### 5. Initialize Database with Historical Data

After first deploy, run a one-time scrape of 30 days:

```bash
# SSH into Render shell or run locally
python cron_daily_scrape.py 30
```

---

## Files Created for Deployment

| File | Purpose |
|------|---------|
| `render.yaml` | Render service configuration |
| `Procfile` | Web process command |
| `.python-version` | Python version (3.11) |
| `cron_daily_scrape.py` | Daily scraping script |
| `requirements.txt` | Python dependencies |

## Notes

- **Free tier**: Render free tier spins down after 15 mins of inactivity
- **Database**: SQLite is stored on disk - use Render's persistent disk or switch to PostgreSQL for production
- **Playwright**: Build includes browser dependencies installation
