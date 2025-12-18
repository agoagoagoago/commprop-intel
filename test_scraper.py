"""Quick test script for scraper"""
import asyncio
from scraper.scraper import scrape_stclassifieds

async def main():
    print("Testing scraper...")
    listings = await scrape_stclassifieds()
    print(f"\nFound {len(listings)} listings\n")
    
    for i, listing in enumerate(listings[:10]):
        print(f"--- Listing {i+1} ---")
        print(f"Category: {listing.get('category', 'N/A')}")
        print(f"Text: {listing['raw_text'][:150]}...")
        print()

if __name__ == "__main__":
    asyncio.run(main())
