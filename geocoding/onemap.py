"""
Geocoding service using Singapore's OneMap API.
Converts addresses and property names to coordinates.
"""
import httpx
import re
from typing import Optional, Tuple
import json
import os

# Cache file for geocoding results
CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "geocode_cache.json")


class OneMapGeocoder:
    """Geocoder using Singapore's OneMap API."""
    
    API_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
    
    def __init__(self):
        self._cache = self._load_cache()
    
    def _load_cache(self) -> dict:
        """Load geocoding cache from file."""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading geocode cache: {e}")
        return {}
    
    def _save_cache(self):
        """Save geocoding cache to file."""
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, 'w') as f:
                json.dump(self._cache, f)
        except Exception as e:
            print(f"Error saving geocode cache: {e}")
    
    def geocode(self, query: str) -> Optional[Tuple[float, float]]:
        """
        Geocode an address or property name to coordinates.
        
        Args:
            query: Address or property name to geocode.
            
        Returns:
            Tuple of (latitude, longitude) or None if not found.
        """
        if not query:
            return None
        
        # Normalize query for cache
        cache_key = query.lower().strip()
        
        # Check cache
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if cached:
                return tuple(cached)
            return None
        
        # Query OneMap API
        try:
            result = self._query_onemap(query)
            
            if result:
                self._cache[cache_key] = list(result)
                self._save_cache()
                return result
            
            # Try simplified query (remove common suffixes)
            simplified = self._simplify_query(query)
            if simplified != query:
                result = self._query_onemap(simplified)
                if result:
                    self._cache[cache_key] = list(result)
                    self._save_cache()
                    return result
            
            # Mark as not found in cache
            self._cache[cache_key] = None
            self._save_cache()
            return None
            
        except Exception as e:
            print(f"Geocoding error for '{query}': {e}")
            return None
    
    def _query_onemap(self, query: str) -> Optional[Tuple[float, float]]:
        """Query OneMap API."""
        params = {
            "searchVal": query,
            "returnGeom": "Y",
            "getAddrDetails": "Y",
            "pageNum": 1
        }
        
        response = httpx.get(self.API_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("found", 0) > 0 and data.get("results"):
            result = data["results"][0]
            lat = float(result.get("LATITUDE", 0))
            lng = float(result.get("LONGITUDE", 0))
            
            if lat and lng:
                return (lat, lng)
        
        return None
    
    def _simplify_query(self, query: str) -> str:
        """Simplify a query for better matching."""
        # Remove common property suffixes
        simplified = re.sub(
            r'\b(industrial|park|centre|center|tower|building|complex|hub|bldg)\b',
            '',
            query,
            flags=re.I
        )
        # Remove extra spaces
        simplified = ' '.join(simplified.split())
        return simplified


# Known Singapore industrial/commercial locations with their coordinates
KNOWN_LOCATIONS = {
    "ubi techpark": (1.3307, 103.8990),
    "ubi": (1.3307, 103.8990),
    "sim lim tower": (1.3025, 103.8463),
    "sim lim": (1.3025, 103.8463),
    "tuas": (1.3200, 103.6400),
    "tuas south": (1.2800, 103.6200),
    "jurong": (1.3329, 103.7436),
    "jurong east": (1.3329, 103.7436),
    "jurong west": (1.3400, 103.7000),
    "pioneer": (1.3151, 103.6975),
    "henderson": (1.2820, 103.8189),
    "henderson road": (1.2820, 103.8189),
    "bukit merah": (1.2819, 103.8239),
    "alexandra": (1.2897, 103.8067),
    "paya lebar": (1.3187, 103.8930),
    "macpherson": (1.3266, 103.8867),
    "tai seng": (1.3360, 103.8880),
    "kaki bukit": (1.3355, 103.9055),
    "eunos": (1.3201, 103.9016),
    "changi": (1.3600, 103.9800),
    "loyang": (1.3700, 103.9700),
    "tampines": (1.3525, 103.9447),
    "woodlands": (1.4400, 103.7867),
    "yishun": (1.4294, 103.8354),
    "sembawang": (1.4491, 103.8185),
    "admiralty": (1.4406, 103.8009),
    "kranji": (1.4251, 103.7620),
    "sungei kadut": (1.4140, 103.7490),
    "mandai": (1.4167, 103.7700),
    "ang mo kio": (1.3691, 103.8454),
    "bishan": (1.3526, 103.8352),
    "toa payoh": (1.3343, 103.8563),
    "balestier": (1.3267, 103.8506),
    "novena": (1.3204, 103.8438),
    "orchard": (1.3048, 103.8318),
    "river valley": (1.2940, 103.8300),
    "boat quay": (1.2867, 103.8498),
    "raffles place": (1.2830, 103.8513),
    "tanjong pagar": (1.2744, 103.8425),
    "chinatown": (1.2833, 103.8432),
    "clarke quay": (1.2888, 103.8463),
    "bugis": (1.3008, 103.8553),
    "little india": (1.3066, 103.8518),
    "geylang": (1.3188, 103.8836),
    "marine parade": (1.3026, 103.9049),
    "east coast": (1.3050, 103.9300),
    "katong": (1.3050, 103.9000),
    "siglap": (1.3150, 103.9250),
    "bedok": (1.3236, 103.9273),
    "pasir ris": (1.3730, 103.9497),
    "serangoon": (1.3502, 103.8716),
    "hougang": (1.3612, 103.8863),
    "punggol": (1.3984, 103.9072),
    "sengkang": (1.3868, 103.8914),
    "commonwealth": (1.3024, 103.7980),
    "queenstown": (1.2942, 103.8060),
    "clementi": (1.3150, 103.7636),
    "bukit timah": (1.3294, 103.8021),
    "upper bukit timah": (1.3600, 103.7700),
    "jalan besar": (1.3080, 103.8560),
    "arab street": (1.3020, 103.8590),
    "beach road": (1.2990, 103.8610),
    "peninsula plaza": (1.2937, 103.8522),
}


def geocode_location(query: str) -> Optional[Tuple[float, float]]:
    """
    Main geocoding function. Checks known locations first, then uses OneMap API.
    
    Args:
        query: Address or property name.
        
    Returns:
        Tuple of (latitude, longitude) or None.
    """
    if not query:
        return None
    
    # Check known locations first
    query_lower = query.lower()
    for location, coords in KNOWN_LOCATIONS.items():
        if location in query_lower:
            return coords
    
    # Use OneMap API
    geocoder = OneMapGeocoder()
    return geocoder.geocode(query)


# For testing
if __name__ == "__main__":
    test_queries = [
        "Ubi Techpark",
        "Sim Lim Tower",
        "23 Tampines Street 92",
        "Pioneer Road",
        "Henderson Road"
    ]
    
    for query in test_queries:
        coords = geocode_location(query)
        print(f"{query}: {coords}")
