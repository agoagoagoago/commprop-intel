"""
FastAPI backend for CommProp Intel Map.
Provides REST API endpoints for listings, analytics, and scraping.
"""
import asyncio
import json
from datetime import date, datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import os

# Add parent directory to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import SessionLocal, Listing, ListingSnapshot, Advertiser, ScrapeLog, init_db
from scraper.scraper import scrape_stclassifieds, scrape_all_dates
from extraction.ai_extractor import extract_listing_data
from geocoding.onemap import geocode_location

app = FastAPI(
    title="CommProp Intel Map",
    description="Commercial/Industrial Property Intelligence for Singapore Agents",
    version="1.0.0"
)

# Serve frontend static files
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main frontend page."""
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Frontend not found. Run the scraper first.</h1>")


@app.get("/api/listings")
async def get_listings(
    property_type: Optional[str] = Query(None, description="Filter by property type"),
    transaction_type: Optional[str] = Query(None, description="Filter by Sale/Rent"),
    is_owner: Optional[bool] = Query(None, description="Filter by owner listings"),
    is_agent: Optional[bool] = Query(None, description="Filter by agent listings"),
    min_price: Optional[int] = Query(None, description="Minimum price"),
    max_price: Optional[int] = Query(None, description="Maximum price"),
    has_coords: Optional[bool] = Query(None, description="Only show listings with coordinates")
):
    """Get all listings with optional filters."""
    db = SessionLocal()
    try:
        query = db.query(Listing)
        
        if property_type:
            query = query.filter(Listing.property_type == property_type)
        if transaction_type:
            query = query.filter(Listing.transaction_type == transaction_type)
        if is_owner is not None:
            query = query.filter(Listing.is_owner == is_owner)
        if is_agent is not None:
            query = query.filter(Listing.is_agent == is_agent)
        if min_price:
            query = query.filter(Listing.price >= min_price)
        if max_price:
            query = query.filter(Listing.price <= max_price)
        if has_coords:
            query = query.filter(Listing.latitude.isnot(None), Listing.longitude.isnot(None))
        
        listings = query.all()
        return [listing.to_dict() for listing in listings]
    finally:
        db.close()


@app.get("/api/listings/{listing_id}")
async def get_listing(listing_id: str):
    """Get a single listing by ID."""
    db = SessionLocal()
    try:
        listing = db.query(Listing).filter(Listing.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        return listing.to_dict()
    finally:
        db.close()


@app.get("/api/analytics/advertisers")
async def get_top_advertisers(
    limit: int = Query(20, description="Number of advertisers to return"),
    is_owner: Optional[bool] = Query(None, description="Filter by owner status")
):
    """Get top advertisers by listing count."""
    db = SessionLocal()
    try:
        query = db.query(Advertiser).order_by(Advertiser.total_listings.desc())
        
        if is_owner is not None:
            query = query.filter(Advertiser.is_owner == is_owner)
        
        advertisers = query.limit(limit).all()
        return [adv.to_dict() for adv in advertisers]
    finally:
        db.close()


@app.get("/api/analytics/trends")
async def get_trends():
    """Get market trends and statistics."""
    db = SessionLocal()
    try:
        # Get total listings
        total_listings = db.query(Listing).count()
        
        # Get listings by type
        by_type = db.query(
            Listing.property_type, 
            func.count(Listing.id)
        ).group_by(Listing.property_type).all()
        
        # Get owner vs agent breakdown
        owner_count = db.query(Listing).filter(Listing.is_owner == True).count()
        agent_count = db.query(Listing).filter(Listing.is_agent == True).count()
        unknown_count = total_listings - owner_count - agent_count
        
        # Get average price per sqft (for listings with both price and sqft)
        listings_with_psf = db.query(Listing).filter(
            Listing.price.isnot(None),
            Listing.gfa_sqft.isnot(None),
            Listing.gfa_sqft > 0
        ).all()
        
        avg_psf = None
        if listings_with_psf:
            total_psf = sum(l.price / l.gfa_sqft for l in listings_with_psf)
            avg_psf = round(total_psf / len(listings_with_psf), 2)
        
        # Get listings over time (by first_seen_date)
        by_date = db.query(
            Listing.first_seen_date,
            func.count(Listing.id)
        ).group_by(Listing.first_seen_date).order_by(Listing.first_seen_date).all()
        
        return {
            "total_listings": total_listings,
            "by_property_type": {t: c for t, c in by_type if t},
            "owner_vs_agent": {
                "owner": owner_count,
                "agent": agent_count,
                "unknown": unknown_count
            },
            "average_psf": avg_psf,
            "listings_by_date": [
                {"date": d.isoformat() if d else None, "count": c} 
                for d, c in by_date
            ]
        }
    finally:
        db.close()


@app.get("/api/analytics/summary")
async def get_summary():
    """Get quick summary statistics."""
    db = SessionLocal()
    try:
        total = db.query(Listing).count()
        with_coords = db.query(Listing).filter(
            Listing.latitude.isnot(None)
        ).count()
        owners = db.query(Listing).filter(Listing.is_owner == True).count()
        
        return {
            "total_listings": total,
            "with_coordinates": with_coords,
            "owner_listings": owners,
            "agent_listings": total - owners
        }
    finally:
        db.close()


async def run_scrape_task(target_date: Optional[str] = None):
    """Background task to run the scraper."""
    db = SessionLocal()
    
    # Create scrape log
    log = ScrapeLog(
        scrape_date=datetime.utcnow(),
        status="running"
    )
    db.add(log)
    db.commit()
    
    try:
        # Run scraper
        raw_listings = await scrape_stclassifieds(target_date)
        log.listings_found = len(raw_listings)
        
        new_count = 0
        updated_count = 0
        
        for raw in raw_listings:
            # Extract structured data
            extracted = extract_listing_data(raw["raw_text"], raw.get("category"))
            
            # Check if listing exists
            existing = db.query(Listing).filter(Listing.id == raw["id"]).first()
            
            if existing:
                # Update last seen date
                existing.last_seen_date = date.today()
                
                # Create snapshot for trend tracking
                snapshot = ListingSnapshot(
                    listing_id=raw["id"],
                    seen_date=date.today(),
                    price=extracted.get("price"),
                    raw_text=raw["raw_text"]
                )
                db.add(snapshot)
                updated_count += 1
            else:
                # Get coordinates
                coords = None
                if extracted.get("property_name"):
                    coords = geocode_location(extracted["property_name"])
                if not coords and extracted.get("address"):
                    coords = geocode_location(extracted["address"])
                
                # Create new listing
                listing = Listing(
                    id=raw["id"],
                    property_name=extracted.get("property_name"),
                    address=extracted.get("address"),
                    latitude=coords[0] if coords else None,
                    longitude=coords[1] if coords else None,
                    property_type=extracted.get("property_type"),
                    property_subtype=extracted.get("property_subtype"),
                    transaction_type=extracted.get("transaction_type"),
                    price=extracted.get("price"),
                    price_type=extracted.get("price_type"),
                    gfa_sqft=extracted.get("gfa_sqft"),
                    lease_type=extracted.get("lease_type"),
                    lease_balance_years=extracted.get("lease_balance_years"),
                    features=json.dumps(extracted.get("features", [])),
                    contact_name=extracted.get("contact_name"),
                    contact_phone=extracted.get("contact_phone"),
                    is_owner=extracted.get("is_owner", False),
                    is_agent=extracted.get("is_agent", False),
                    agency_name=extracted.get("agency_name"),
                    cobroke_allowed=extracted.get("cobroke_allowed"),
                    raw_text=raw["raw_text"],
                    category=raw.get("category"),
                    first_seen_date=date.today(),
                    last_seen_date=date.today()
                )
                db.add(listing)
                new_count += 1
                
                # Update advertiser tracking
                if extracted.get("contact_phone"):
                    phone = extracted["contact_phone"]
                    advertiser = db.query(Advertiser).filter(Advertiser.phone == phone).first()
                    
                    if advertiser:
                        advertiser.total_listings += 1
                        advertiser.last_seen = date.today()
                    else:
                        advertiser = Advertiser(
                            phone=phone,
                            name=extracted.get("contact_name"),
                            is_owner=extracted.get("is_owner", False),
                            is_agent=extracted.get("is_agent", False),
                            agency_name=extracted.get("agency_name"),
                            total_listings=1,
                            first_seen=date.today(),
                            last_seen=date.today()
                        )
                        db.add(advertiser)
        
        log.listings_new = new_count
        log.listings_updated = updated_count
        log.status = "completed"
        db.commit()
        
        return {
            "status": "completed",
            "listings_found": len(raw_listings),
            "new": new_count,
            "updated": updated_count
        }
        
    except Exception as e:
        log.status = "failed"
        log.error_message = str(e)
        db.commit()
        raise
    finally:
        db.close()


@app.post("/api/scrape")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    target_date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")
):
    """Trigger a scrape of stclassifieds.sg."""
    # Run synchronously for now to show results immediately
    result = await run_scrape_task(target_date)
    return result


@app.get("/api/scrape/status")
async def get_scrape_status():
    """Get the status of the most recent scrape."""
    db = SessionLocal()
    try:
        log = db.query(ScrapeLog).order_by(ScrapeLog.scrape_date.desc()).first()
        if not log:
            return {"status": "no_scrapes_yet"}
        return {
            "status": log.status,
            "date": log.scrape_date.isoformat() if log.scrape_date else None,
            "listings_found": log.listings_found,
            "new": log.listings_new,
            "updated": log.listings_updated,
            "error": log.error_message
        }
    finally:
        db.close()


@app.post("/api/scrape/all")
async def trigger_scrape_all(
    days_back: int = Query(30, description="Number of days to scrape back")
):
    """
    Scrape listings from the past N days. 
    This can take several minutes for 30 days of data.
    """
    db = SessionLocal()
    
    # Create scrape log
    log = ScrapeLog(
        scrape_date=datetime.utcnow(),
        status="running"
    )
    db.add(log)
    db.commit()
    
    try:
        # Run multi-date scraper
        print(f"Starting multi-date scrape for {days_back} days...")
        raw_listings = await scrape_all_dates(days_back)
        log.listings_found = len(raw_listings)
        
        new_count = 0
        updated_count = 0
        
        for raw in raw_listings:
            # Extract structured data using AI
            extracted = extract_listing_data(raw["raw_text"], raw.get("category"))
            
            # Check if listing exists by ID
            existing = db.query(Listing).filter(Listing.id == raw["id"]).first()
            
            if existing:
                # Update last seen date
                existing.last_seen_date = date.today()
                updated_count += 1
            else:
                # Get coordinates
                coords = None
                if extracted.get("property_name"):
                    coords = geocode_location(extracted["property_name"])
                if not coords and extracted.get("address"):
                    coords = geocode_location(extracted["address"])
                
                # Parse the scrape_date if available
                first_seen = date.today()
                if raw.get("scrape_date"):
                    try:
                        first_seen = datetime.strptime(raw["scrape_date"], "%Y-%m-%d").date()
                    except:
                        pass
                
                # Create new listing
                listing = Listing(
                    id=raw["id"],
                    property_name=extracted.get("property_name"),
                    address=extracted.get("address"),
                    latitude=coords[0] if coords else None,
                    longitude=coords[1] if coords else None,
                    property_type=extracted.get("property_type"),
                    property_subtype=extracted.get("property_subtype"),
                    transaction_type=extracted.get("transaction_type"),
                    price=extracted.get("price"),
                    price_type=extracted.get("price_type"),
                    gfa_sqft=extracted.get("gfa_sqft"),
                    lease_type=extracted.get("lease_type"),
                    lease_balance_years=extracted.get("lease_balance_years"),
                    features=json.dumps(extracted.get("features", [])),
                    contact_name=extracted.get("contact_name"),
                    contact_phone=extracted.get("contact_phone"),
                    is_owner=extracted.get("is_owner", False),
                    is_agent=extracted.get("is_agent", False),
                    agency_name=extracted.get("agency_name"),
                    cobroke_allowed=extracted.get("cobroke_allowed"),
                    raw_text=raw["raw_text"],
                    category=raw.get("category"),
                    first_seen_date=first_seen,
                    last_seen_date=date.today()
                )
                db.add(listing)
                new_count += 1
                
                # Update advertiser tracking
                if extracted.get("contact_phone"):
                    phone = extracted["contact_phone"]
                    advertiser = db.query(Advertiser).filter(Advertiser.phone == phone).first()
                    
                    if advertiser:
                        advertiser.total_listings += 1
                        advertiser.last_seen = date.today()
                    else:
                        advertiser = Advertiser(
                            phone=phone,
                            name=extracted.get("contact_name"),
                            is_owner=extracted.get("is_owner", False),
                            is_agent=extracted.get("is_agent", False),
                            agency_name=extracted.get("agency_name"),
                            total_listings=1,
                            first_seen=first_seen,
                            last_seen=date.today()
                        )
                        db.add(advertiser)
        
        log.listings_new = new_count
        log.listings_updated = updated_count
        log.status = "completed"
        db.commit()
        
        return {
            "status": "completed",
            "days_scraped": days_back,
            "listings_found": len(raw_listings),
            "new": new_count,
            "updated": updated_count
        }
        
    except Exception as e:
        log.status = "failed"
        log.error_message = str(e)
        db.commit()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

