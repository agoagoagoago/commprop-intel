"""
Daily scraper cron job - can be triggered via Render Cron Jobs or external scheduler.
Scrapes the latest listings and adds them to the database.
"""
import asyncio
import json
from datetime import date, datetime, timedelta
from scraper.scraper import scrape_all_dates
from extraction.ai_extractor import extract_listings_batch
from geocoding.onemap import geocode_location
from database.models import SessionLocal, Listing, Advertiser, init_db
import re


def extract_location_hints(text: str) -> list:
    """Extract location hints from listing text."""
    hints = []
    patterns = [
        r'^([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3})',
        r'@\s*([A-Za-z][A-Za-z\s]+)',
        r'(?:near|opp|opposite|beside)\s+([A-Za-z][A-Za-z\s]+(?:MRT|Road|Ave|Street|Park|Hub|Centre|Center)?)',
        r'\b(Tuas|Ubi|Tai Seng|Mandai|Woodlands|Jurong|Changi|Paya Lebar|Geylang|Aljunied|Kallang|Bukit Batok|Ang Mo Kio|AMK|Tampines|Bedok|Sim Lim|Bendemeer|Macpherson)\b',
        r'([A-Za-z]+\s*(?:Tech|Industrial|Biz|Business|Logistic|Enterprise)\s*(?:Park|Hub|Centre|Center|Link))',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.I)
        for match in matches:
            hint = match.strip()
            if hint and len(hint) > 2 and hint.lower() not in ['for', 'the', 'and', 'with']:
                hint = hint.replace('AMK', 'Ang Mo Kio')
                if hint not in hints:
                    hints.append(hint)
    return hints[:5]


def try_geocode(hints: list, extracted_data: dict) -> tuple:
    """Try geocoding with multiple hints."""
    search_terms = []
    if extracted_data.get("property_name"):
        search_terms.append(extracted_data["property_name"])
    if extracted_data.get("address"):
        search_terms.append(extracted_data["address"])
    search_terms.extend(hints)
    
    for term in search_terms:
        if not term or len(term) < 3:
            continue
        coords = geocode_location(term)
        if coords:
            return coords
    return None


async def daily_scrape(days: int = 1):
    """Run daily scrape - gets the last N days of listings."""
    print(f"=" * 60)
    print(f"DAILY SCRAPE - {datetime.now().isoformat()}")
    print(f"=" * 60)
    
    init_db()
    db = SessionLocal()
    
    try:
        print(f"\n1. Scraping last {days} day(s)...")
        raw_listings = await scrape_all_dates(days)
        print(f"   Found {len(raw_listings)} raw listings")
        
        if not raw_listings:
            print("   No new listings found.")
            return {"status": "complete", "new": 0}
        
        print("\n2. Batch AI extraction...")
        extracted_list = extract_listings_batch(raw_listings)
        
        print("\n3. Processing and saving...")
        new_count = 0
        updated_count = 0
        
        for raw, extracted in zip(raw_listings, extracted_list):
            listing_id = raw["id"]
            
            # Check if exists
            existing = db.query(Listing).filter(Listing.id == listing_id).first()
            if existing:
                existing.last_seen_date = date.today()
                updated_count += 1
                continue
            
            # Geocode
            hints = extract_location_hints(raw["raw_text"])
            coords = try_geocode(hints, extracted)
            
            first_seen = date.today()
            if raw.get("scrape_date"):
                try:
                    first_seen = datetime.strptime(raw["scrape_date"], "%Y-%m-%d").date()
                except:
                    pass
            
            listing = Listing(
                id=listing_id,
                property_name=extracted.get("property_name"),
                address=extracted.get("address"),
                latitude=coords[0] if coords else None,
                longitude=coords[1] if coords else None,
                property_type=extracted.get("property_type", "Other"),
                transaction_type=extracted.get("transaction_type"),
                price=extracted.get("price"),
                gfa_sqft=extracted.get("gfa_sqft"),
                lease_type=extracted.get("lease_type"),
                features=json.dumps(extracted.get("features", [])),
                contact_name=extracted.get("contact_name"),
                contact_phone=extracted.get("contact_phone"),
                is_owner=extracted.get("is_owner", False),
                is_agent=extracted.get("is_agent", False),
                agency_name=extracted.get("agency_name"),
                raw_text=raw["raw_text"],
                category=raw.get("category"),
                first_seen_date=first_seen,
                last_seen_date=date.today()
            )
            
            try:
                db.add(listing)
                db.commit()
                new_count += 1
                
                # Track advertiser
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
                            total_listings=1,
                            first_seen=first_seen,
                            last_seen=date.today()
                        )
                        db.add(advertiser)
                    db.commit()
            except Exception as e:
                db.rollback()
                print(f"   Error saving: {e}")
        
        result = {
            "status": "complete",
            "new": new_count,
            "updated": updated_count,
            "total": db.query(Listing).count()
        }
        
        print(f"\n✅ COMPLETE: {new_count} new, {updated_count} updated")
        return result
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    asyncio.run(daily_scrape(days))
