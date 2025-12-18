"""
Web scraper for stclassifieds.sg Commercial/Industrial Properties.
Updated to properly handle date selection via dropdown.
"""
import asyncio
import hashlib
from datetime import date, datetime, timedelta
from typing import Optional, List
from playwright.async_api import async_playwright, Browser, Page
from bs4 import BeautifulSoup
import re


class STClassifiedsScraper:
    """Scraper for stclassifieds.sg property listings."""
    
    BASE_URL = "https://www.stclassifieds.sg/section/sub/list/properties/759"
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._playwright = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def scrape_date(self, target_date: date) -> list[dict]:
        """
        Scrape listings for a specific date by clicking the date dropdown.
        
        Args:
            target_date: The date to scrape.
            
        Returns:
            List of raw listing dictionaries.
        """
        # Format the date as it appears in the dropdown: "2025-12-13, Sat"
        date_str = target_date.strftime("%Y-%m-%d, %a")
        
        print(f"  Scraping date: {date_str}")
        
        # Navigate to page
        await self.page.goto(self.BASE_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # Click the date dropdown button
        try:
            dropdown_btn = await self.page.wait_for_selector('button.btn-default.dropdown-toggle', timeout=5000)
            if dropdown_btn:
                await dropdown_btn.click()
                await asyncio.sleep(1)
                
                # Find and click the target date in the dropdown
                date_option = await self.page.query_selector(f'a:has-text("{date_str}")')
                if date_option:
                    await date_option.click()
                    await asyncio.sleep(3)  # Wait for page to reload with new date
                else:
                    print(f"    Date option not found: {date_str}")
                    return []
        except Exception as e:
            print(f"    Error selecting date: {e}")
            return []
        
        # Get page content after date selection
        content = await self.page.content()
        
        # Check if there are results
        if "No results found" in content:
            print(f"    No listings for {date_str}")
            return []
        
        return self._parse_listings(content, target_date.isoformat())
    
    async def scrape_weekdays(self, days_back: int = 7) -> list[dict]:
        """
        Scrape listings from the past N days, skipping days with no results.
        
        Args:
            days_back: Number of days to go back.
            
        Returns:
            Combined list of all listings.
        """
        all_listings = []
        today = date.today()
        
        print(f"\nScraping last {days_back} days of listings...")
        
        for i in range(days_back):
            target_date = today - timedelta(days=i+1)  # Start from yesterday
            
            try:
                listings = await self.scrape_date(target_date)
                if listings:
                    print(f"    Found {len(listings)} listings")
                    all_listings.extend(listings)
            except Exception as e:
                print(f"    Error scraping {target_date}: {e}")
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(1)
        
        print(f"\nTotal listings found: {len(all_listings)}")
        return all_listings
    
    def _parse_listings(self, html_content: str, scrape_date: str) -> list[dict]:
        """
        Parse listings from HTML content.
        Look for listing patterns in the page text.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        listings = []
        
        # Find the main content area
        content_div = soup.find('div', class_='listView')
        if not content_div:
            content_div = soup
        
        # Get all text and find phone number patterns as listing markers
        all_text = content_div.get_text(separator='\n')
        
        # Split by "Commercial/ Industrial Properties" which marks category
        parts = re.split(r'(Commercial[/\s]*Industrial\s*Properties)', all_text, flags=re.I)
        
        for i in range(1, len(parts), 2):
            if i + 1 >= len(parts):
                break
                
            category_text = parts[i]
            after_text = parts[i + 1] if i + 1 < len(parts) else ""
            
            # Find the subcategory and listing text
            # Pattern: "Factory/ Warehouse Space - 3963" followed by listing text
            match = re.search(
                r'([A-Za-z/\s]+Space\s*-\s*\d+)\s*(.+?)(?=(?:Commercial[/\s]*Industrial|$))',
                after_text,
                re.DOTALL | re.I
            )
            
            if match:
                subcategory = match.group(1).strip()
                listing_text = match.group(2).strip()
                
                # Clean up the text
                listing_text = ' '.join(listing_text.split())
                
                # Must have 8-digit phone number
                phone_match = re.search(r'(\d{8})', listing_text)
                if phone_match and len(listing_text) > 30:
                    category = f"Commercial/Industrial Properties - {subcategory}"
                    
                    listing = self._create_listing_dict(
                        listing_text[:500],  # Limit length
                        category,
                        scrape_date
                    )
                    if listing:
                        listings.append(listing)
        
        # Fallback: Also try to find listings by looking for phone numbers directly
        if len(listings) < 2:
            # Look for text blocks with phone numbers
            phone_patterns = re.finditer(r'(.{50,300}?)(\d{8})(.{0,100})', all_text, re.DOTALL)
            
            for match in phone_patterns:
                before = match.group(1).strip()
                phone = match.group(2)
                after = match.group(3).strip()
                
                full_text = f"{before} {phone} {after}".strip()
                full_text = ' '.join(full_text.split())
                
                # Skip if too short or doesn't look like property listing
                if len(full_text) < 50:
                    continue
                if not any(word in full_text.lower() for word in ['sqft', 'sf', 'rent', 'sale', 'factory', 'warehouse', 'office', 'shop']):
                    continue
                
                listing = self._create_listing_dict(full_text, None, scrape_date)
                if listing and listing['id'] not in [l['id'] for l in listings]:
                    listings.append(listing)
        
        return listings
    
    def _create_listing_dict(self, raw_text: str, category: str = None, scrape_date: str = None) -> Optional[dict]:
        """Create a listing dictionary from raw text."""
        # Clean up the text
        raw_text = ' '.join(raw_text.split())
        
        # Skip if too short
        if len(raw_text) < 30:
            return None
        
        # Must have phone number
        if not re.search(r'\d{8}', raw_text):
            return None
        
        # Generate unique ID
        id_source = f"{raw_text[:100]}_{scrape_date or date.today().isoformat()}"
        listing_id = hashlib.md5(id_source.encode()).hexdigest()[:16]
        
        return {
            "id": listing_id,
            "raw_text": raw_text,
            "category": category,
            "scrape_date": scrape_date or date.today().isoformat()
        }


async def scrape_stclassifieds(target_date: Optional[str] = None) -> list[dict]:
    """Scrape for a single date (defaults to yesterday if today has no listings)."""
    async with STClassifiedsScraper() as scraper:
        if target_date:
            dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            dt = date.today() - timedelta(days=1)  # Yesterday
        return await scraper.scrape_date(dt)


async def scrape_all_dates(days_back: int = 7) -> list[dict]:
    """Scrape listings from the past N days."""
    async with STClassifiedsScraper() as scraper:
        return await scraper.scrape_weekdays(days_back)


# For testing
if __name__ == "__main__":
    import sys
    
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    print(f"Scraping last {days} days...")
    listings = asyncio.run(scrape_all_dates(days))
    
    print(f"\nTotal listings: {len(listings)}")
    for i, l in enumerate(listings[:10]):
        print(f"\n--- Listing {i+1} ---")
        print(f"Date: {l.get('scrape_date')}")
        print(f"Category: {l.get('category', 'N/A')}")
        print(f"Text: {l['raw_text'][:120]}...")
