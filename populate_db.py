"""
Manual population script - bypasses API and directly populates database
Run this to populate your database with listings from the past 30 days.
"""
import asyncio
import json
from datetime import date, datetime
from scraper.scraper import scrape_stclassifieds, scrape_all_dates
from extraction.ai_extractor import extract_listing_data
from geocoding.onemap import geocode_location
from database.models import SessionLocal, Listing, Advertiser, init_db


async def populate_single_day():
    """Populate database with today's listings."""
    print("=" * 50)
    print("POPULATING DATABASE WITH TODAY'S LISTINGS")
    print("=" * 50)
    
    # Initialize database
    init_db()
    db = SessionLocal()
    
    try:
        # Scrape listings
        print("\n1. Scraping listings...")
        raw_listings = await scrape_stclassifieds()
        print(f"   Found {len(raw_listings)} raw listings")
        
        new_count = 0
        for i, raw in enumerate(raw_listings):
            print(f"\n2. Processing listing {i+1}/{len(raw_listings)}...")
            print(f"   Raw text: {raw['raw_text'][:80]}...")
            
            # Extract structured data
            try:
                extracted = extract_listing_data(raw["raw_text"], raw.get("category"))
                print(f"   Extracted: price={extracted.get('price')}, phone={extracted.get('contact_phone')}")
            except Exception as e:
                print(f"   Extraction error: {e}")
                continue
            
            # Check if listing exists
            existing = db.query(Listing).filter(Listing.id == raw["id"]).first()
            if existing:
                print("   Listing already exists, skipping")
                continue
            
            # Get coordinates
            coords = None
            if extracted.get("property_name"):
                coords = geocode_location(extracted["property_name"])
                print(f"   Geocoded '{extracted['property_name']}': {coords}")
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
            print(f"   Added to database!")
            
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
        
        db.commit()
        print(f"\n" + "=" * 50)
        print(f"COMPLETE! Added {new_count} new listings to database.")
        print("=" * 50)
        
        # Show summary
        total = db.query(Listing).count()
        with_coords = db.query(Listing).filter(Listing.latitude.isnot(None)).count()
        owners = db.query(Listing).filter(Listing.is_owner == True).count()
        
        print(f"\nDatabase Summary:")
        print(f"  Total listings: {total}")
        print(f"  With coordinates: {with_coords}")
        print(f"  Owner listings: {owners}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(populate_single_day())
