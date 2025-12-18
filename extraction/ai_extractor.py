"""
AI-powered extraction of structured data from property listings.
Uses Gemini 2.0 Flash for intelligent text parsing.
Optimized with BATCH processing - sends all listings in a single API call.
"""
import os
import json
import re
from typing import Optional, List, Dict
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from project root
PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print(f"✅ Gemini API configured successfully")


# Batch extraction prompt - processes multiple listings at once
BATCH_EXTRACTION_PROMPT = """You are an expert at parsing Singapore commercial/industrial property listings.

I will give you a list of property listings. For EACH listing, extract structured information.
Return a JSON array with one object per listing, in the SAME ORDER as the input.

LISTINGS TO PROCESS:
{listings_json}

For each listing, extract:
{{
    "listing_index": <0-based index matching input order>,
    "property_name": "Building/property name (e.g., 'Ubi Techpark', 'Sim Lim Tower', 'Northstar AMK') or null",
    "address": "Any address or location hint (e.g., 'Tuas Ave 1', 'opp Aljunied MRT', 'near Tai Seng', 'Mandai') or null",
    "property_type": "One of: Factory/Warehouse, Office, Shop, Mixed, Other",
    "transaction_type": "One of: Sale, Rent, Both, or null",
    "price": <numeric price in SGD, e.g. 3550000 for $3.55M, 14000 for $14K, or null>,
    "gfa_sqft": <floor area in sqft as number, or null>,
    "lease_type": "Freehold, 999yr, 99yr, 60yr, 30yr, or null",
    "contact_name": "Contact person name or null",
    "contact_phone": "8-digit Singapore phone number or null",
    "is_owner": <true if text contains 'owner' or 'direct owner', false otherwise>,
    "is_agent": <true if text mentions agency (PropNex, ERA, OrangeTee, Huttons, Dennis Wee) or indicates agent, false otherwise>,
    "agency_name": "Agency name if mentioned, or null"
}}

IMPORTANT GUIDELINES:
- Look for ANY location hints: building names, street names, area names, landmarks like "opp MRT", "near", etc.
- Convert prices: "$3.55M" = 3550000, "$14K" = 14000, "$2.9xM" means approximately 2900000
- Phone numbers are 8 digits starting with 6, 8, or 9
- Return ONLY the JSON array, no other text.

Return the JSON array:"""


class BatchAIExtractor:
    """Extract structured data from multiple listings in a single API call."""
    
    def __init__(self, model_name: str = "gemini-2.0-flash-exp"):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        self.model = genai.GenerativeModel(model_name)
        self.model_name = model_name
    
    def extract_batch(self, listings: List[Dict]) -> List[Dict]:
        """
        Extract structured data from multiple listings in a single API call.
        
        Args:
            listings: List of dicts with 'raw_text' and optional 'category' keys.
            
        Returns:
            List of extracted data dicts, in same order as input.
        """
        if not listings:
            return []
        
        # Prepare input for the prompt
        listings_for_prompt = []
        for i, listing in enumerate(listings):
            listings_for_prompt.append({
                "index": i,
                "text": listing.get("raw_text", ""),
                "category": listing.get("category", "")
            })
        
        prompt = BATCH_EXTRACTION_PROMPT.format(
            listings_json=json.dumps(listings_for_prompt, indent=2)
        )
        
        try:
            print(f"  🤖 Sending {len(listings)} listings to Gemini {self.model_name}...")
            
            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )
            
            # Parse JSON response
            json_text = response.text.strip()
            
            # Clean up potential markdown code blocks
            if json_text.startswith("```"):
                json_text = re.sub(r'^```json?\n?', '', json_text)
                json_text = re.sub(r'\n?```$', '', json_text)
            
            extracted_list = json.loads(json_text)
            
            print(f"  ✅ Successfully extracted {len(extracted_list)} listings")
            
            # Validate and clean each extraction
            result = []
            for ext in extracted_list:
                result.append(self._validate_and_clean(ext))
            
            return result
            
        except Exception as e:
            print(f"  ❌ Batch extraction error: {e}")
            # Fall back to individual regex extraction
            return [self._fallback_extraction(l.get("raw_text", ""), l.get("category")) for l in listings]
    
    def _validate_and_clean(self, data: dict) -> dict:
        """Validate and clean extracted data."""
        # Ensure phone number is 8 digits
        if data.get("contact_phone"):
            phone = re.sub(r'\D', '', str(data["contact_phone"]))
            if len(phone) == 8 and phone[0] in '689':
                data["contact_phone"] = phone
            else:
                data["contact_phone"] = None
        
        # Ensure price is numeric
        if data.get("price"):
            try:
                data["price"] = int(float(data["price"]))
            except (ValueError, TypeError):
                data["price"] = None
        
        # Ensure gfa_sqft is numeric
        if data.get("gfa_sqft"):
            try:
                data["gfa_sqft"] = int(float(data["gfa_sqft"]))
            except (ValueError, TypeError):
                data["gfa_sqft"] = None
        
        # Ensure boolean fields
        data["is_owner"] = bool(data.get("is_owner"))
        data["is_agent"] = bool(data.get("is_agent"))
        
        return data
    
    def _fallback_extraction(self, text: str, category: str = None) -> dict:
        """Fallback regex extraction for single listing."""
        return _fallback_extraction(text, category)


def extract_listings_batch(listings: List[Dict], model: str = "gemini-2.0-flash-exp") -> List[Dict]:
    """
    Main function to extract data from multiple listings in a single API call.
    
    Args:
        listings: List of dicts with 'raw_text' and optional 'category' keys.
        model: Gemini model to use (default: gemini-2.0-flash-exp)
        
    Returns:
        List of extracted data dicts.
    """
    try:
        extractor = BatchAIExtractor(model)
        return extractor.extract_batch(listings)
    except ValueError as e:
        print(f"⚠️ Batch AI extraction unavailable: {e}. Using regex fallback.")
        return [_fallback_extraction(l.get("raw_text", ""), l.get("category")) for l in listings]


# Keep backward compatibility - single listing extraction
def extract_listing_data(listing_text: str, category: str = None) -> dict:
    """
    Extract data from a single listing. Uses batch extractor with single item.
    """
    result = extract_listings_batch([{"raw_text": listing_text, "category": category}])
    return result[0] if result else _fallback_extraction(listing_text, category)


def _fallback_extraction(text: str, category: str = None) -> dict:
    """Regex-based extraction fallback when AI is unavailable."""
    # Extract phone number
    phone_match = re.search(r'([689]\d{7})', text)
    phone = phone_match.group(1) if phone_match else None
    
    # Extract price
    price = None
    try:
        price_match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*(?:M|mil|million)', text, re.I)
        if price_match and price_match.group(1).replace(',', ''):
            price = int(float(price_match.group(1).replace(',', '')) * 1000000)
        else:
            price_match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*(?:K|k)', text, re.I)
            if price_match and price_match.group(1).replace(',', ''):
                price = int(float(price_match.group(1).replace(',', '')) * 1000)
    except (ValueError, AttributeError):
        price = None
    
    # Extract sqft
    sqft = None
    sqft_match = re.search(r'([\d,]+)\s*(?:sf|sqft|sq\s*ft)', text, re.I)
    if sqft_match:
        try:
            sqft = int(sqft_match.group(1).replace(',', ''))
        except:
            sqft = None
    
    # Detect owner vs agent
    is_owner = bool(re.search(r'\bowner\b|\bdirect\b', text, re.I))
    is_agent = bool(re.search(r'propnex|era\b|orangetee|huttons|dennis wee', text, re.I))
    
    # Try to extract property/location name
    property_name = None
    address = None
    
    # Look for building names (capitalized words at start, or common patterns)
    name_match = re.search(r'^([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})', text)
    if name_match:
        property_name = name_match.group(1)
    
    # Look for location hints
    location_patterns = [
        r'(?:at|@|near|opp|opposite)\s+([A-Za-z\s]+(?:MRT|Road|Ave|Street|Park|Hub|Centre|Center))',
        r'(Tuas|Ubi|Tai Seng|Mandai|Woodlands|Jurong|Changi|Paya Lebar|Geylang|Aljunied|Kallang)',
    ]
    for pattern in location_patterns:
        loc_match = re.search(pattern, text, re.I)
        if loc_match:
            address = loc_match.group(1).strip()
            break
    
    # Infer property type
    property_type = "Other"
    if category:
        if 'factory' in category.lower() or 'warehouse' in category.lower():
            property_type = "Factory/Warehouse"
        elif 'office' in category.lower():
            property_type = "Office"
        elif 'shop' in category.lower():
            property_type = "Shop"
    
    return {
        "property_name": property_name,
        "address": address,
        "property_type": property_type,
        "property_subtype": None,
        "transaction_type": "Sale" if re.search(r'\bsale\b', text, re.I) else "Rent" if re.search(r'\brent\b', text, re.I) else None,
        "price": price,
        "price_type": None,
        "gfa_sqft": sqft,
        "lease_type": None,
        "lease_balance_years": None,
        "floor_level": None,
        "features": [],
        "contact_name": None,
        "contact_phone": phone,
        "is_owner": is_owner,
        "is_agent": is_agent,
        "agency_name": None,
        "cobroke_allowed": None
    }


if __name__ == "__main__":
    # Test batch extraction
    test_listings = [
        {"raw_text": "UBI TECHPARK 3/STY B1 Park 4cars. 7858 sf $3.55M Ground flr. Price to sell. 98183835 Jean Lee"},
        {"raw_text": "TUAS AVE 1 factory/warehouse cum office for rent, approx 7500sf. Owner 91058518"},
        {"raw_text": "FOR SALE/ RENT. B1 Factory unit, 1927 sqft @ Northstar AMK. WhatsApp: 9099 5525"},
    ]
    
    results = extract_listings_batch(test_listings)
    for i, result in enumerate(results):
        print(f"\n--- Listing {i+1} ---")
        print(json.dumps(result, indent=2))
