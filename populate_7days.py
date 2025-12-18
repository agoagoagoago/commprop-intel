"""
Populate database with last 7 days of listings.
Uses BATCH AI extraction (all listings in single API call).
Improved geocoding with multiple search term attempts.
"""
import asyncio
import json
from datetime import date, datetime
from scraper.scraper import scrape_all_dates
from extraction.ai_extractor import extract_listings_batch
from geocoding.onemap import geocode_location
from database.models import SessionLocal, Listing, Advertiser, init_db
import re


def extract_location_hints(text: str) -> list:
    """
    Extract multiple possible location hints from listing text.
    Returns list of search terms to try for geocoding.
    """
    hints = []
    
    # Common Singapore building/location patterns
    patterns = [
        # Building names (capitalized multi-word at start)
        r'^([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3})',
        # @ location pattern
        r'@\s*([A-Za-z][A-Za-z\s]+)',
        # Near/opp patterns
        r'(?:near|opp|opposite|beside)\s+([A-Za-z][A-Za-z\s]+(?:MRT|Road|Ave|Street|Park|Hub|Centre|Center)?)',
        # Specific areas
        r'\b(Tuas|Ubi|Tai Seng|Mandai|Woodlands|Jurong|Changi|Paya Lebar|Geylang|Aljunied|Kallang|Bukit Batok|Ang Mo Kio|AMK|Tampines|Bedok|Sim Lim|Bendemeer|Macpherson)\b',
        # Industrial park names
        r'([A-Za-z]+\s*(?:Tech|Industrial|Biz|Business|Logistic|Enterprise)\s*(?:Park|Hub|Centre|Center|Link))',
        # Road patterns
        r'([A-Za-z]+\s+(?:Road|Ave|Avenue|Street|Lane|Drive|Crescent|Way|Link)\s*\d*)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.I)
        for match in matches:
            hint = match.strip()
            # Clean up and validate
            if hint and len(hint) > 2 and hint.lower() not in ['for', 'the', 'and', 'with']:
                # Normalize common abbreviations
                hint = hint.replace('AMK', 'Ang Mo Kio')
                if hint not in hints:
                    hints.append(hint)
    
    return hints[:5]  # Return top 5 hints


def try_geocode(hints: list, extracted_data: dict) -> tuple:
    """Try to geocode using multiple hints. Returns (lat, lng) or None."""
    # Build list of search terms to try
    search_terms = []
    
    # Add extracted property name and address first
    if extracted_data.get("property_name"):
        search_terms.append(extracted_data["property_name"])
    if extracted_data.get("address"):
        search_terms.append(extracted_data["address"])
    
    # Add location hints
    search_terms.extend(hints)
    
    # Try each term
    for term in search_terms:
        if not term or len(term) < 3:
            continue
        
        coords = geocode_location(term)
        if coords:
            print(f"      📍 Geocoded '{term}' → {coords}")
            return coords
    
    return None


async def populate_with_batch_extraction(days: int = 7):
    """Populate database with batch AI extraction."""
    print("=" * 60)
    print(f"POPULATING DATABASE WITH LAST {days} DAYS OF LISTINGS")
    print("(Using batch AI extraction - single API call)")
    print("=" * 60)
    
    # Initialize database
    init_db()
    db = SessionLocal()
    
    try:
        # Scrape listings
        print("\n1. Scraping listings...")
        raw_listings = await scrape_all_dates(days)
        print(f"\n   Total raw listings found: {len(raw_listings)}")
        
        if len(raw_listings) == 0:
            print("   No listings found.")
            return
        
        # Batch extract all listings with AI
        print("\n2. Extracting data with Gemini AI (batch mode)...")
        extracted_list = extract_listings_batch(raw_listings)
        print(f"   Extracted data for {len(extracted_list)} listings")
        
        # Process and save to database
        print("\n3. Processing and geocoding...")
        new_count = 0
        geocoded_count = 0
        
        for i, (raw, extracted) in enumerate(zip(raw_listings, extracted_list)):
            listing_id = raw["id"]
            
            # Skip if exists
            if db.query(Listing).filter(Listing.id == listing_id).first():
                continue
            
            print(f"\n   [{i+1}/{len(raw_listings)}] {raw['raw_text'][:50]}...")
            
            # Extract location hints from raw text
            location_hints = extract_location_hints(raw["raw_text"])
            
            # Try to geocode
            coords = try_geocode(location_hints, extracted)
            if coords:
                geocoded_count += 1
            
            # Parse first_seen date
            first_seen = date.today()
            if raw.get("scrape_date"):
                try:
                    first_seen = datetime.strptime(raw["scrape_date"], "%Y-%m-%d").date()
                except:
                    pass
            
            # Create listing
            listing = Listing(
                id=listing_id,
                property_name=extracted.get("property_name"),
                address=extracted.get("address"),
                latitude=coords[0] if coords else None,
                longitude=coords[1] if coords else None,
                property_type=extracted.get("property_type", "Other"),
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
                            agency_name=extracted.get("agency_name"),
                            total_listings=1,
                            first_seen=first_seen,
                            last_seen=date.today()
                        )
                        db.add(advertiser)
                    db.commit()
                    
            except Exception as e:
                db.rollback()
                print(f"      ⚠️ DB error: {e}")
        
        # Summary
        print("\n" + "=" * 60)
        print("COMPLETE!")
        print("=" * 60)
        
        total = db.query(Listing).count()
        with_coords = db.query(Listing).filter(Listing.latitude.isnot(None)).count()
        owners = db.query(Listing).filter(Listing.is_owner == True).count()
        agents = db.query(Listing).filter(Listing.is_agent == True).count()
        
        print(f"\nDatabase Summary:")
        print(f"  New listings added: {new_count}")
        print(f"  Geocoded: {geocoded_count}")
        print(f"  Total listings: {total}")
        print(f"  With coordinates: {with_coords}")
        print(f"  Owner listings: {owners}")
        print(f"  Agent listings: {agents}")
        print(f"  Unknown: {total - owners - agents}")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    asyncio.run(populate_with_batch_extraction(days))
