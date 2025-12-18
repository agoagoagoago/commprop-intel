# CommProp Intel Map

A commercial/industrial property intelligence application for Singapore agents. Scrapes stclassifieds.sg listings, uses AI to extract structured data, and visualizes on an interactive map.

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY
   ```

3. **Run the application**:
   ```bash
   python run.py
   ```

4. **Open in browser**: http://localhost:8000

## Features

- 🗺️ Interactive Singapore map with property markers
- 🤖 AI-powered extraction of property details from unstructured ads
- 📊 Owner vs Agent classification
- 📈 Advertiser frequency tracking
- 🔍 Filter by property type, price, owner/agent status
- 📅 Historical trend tracking

## Project Structure

```
├── scraper/          # Web scraping logic
├── extraction/       # AI extraction with Gemini
├── geocoding/        # OneMap API integration
├── database/         # SQLite models and setup
├── api/              # FastAPI backend
├── frontend/         # HTML/JS map interface
├── data/             # SQLite database storage
└── run.py            # Main entry point
```

## API Endpoints

- `GET /` - Main map interface
- `GET /api/listings` - All listings with filters
- `GET /api/analytics/advertisers` - Top advertisers
- `GET /api/analytics/trends` - Price/volume trends
- `POST /api/scrape` - Trigger manual scrape
