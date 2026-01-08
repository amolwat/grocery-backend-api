from fastapi import FastAPI, Request
from ai_matcher import SmartMatcher
import retailer_scraper
import time

app = FastAPI()

# ==========================================
# 🧠 MEMORY CACHE (The Speed Secret)
# ==========================================
# Stores results for 1 hour so repeat searches are INSTANT
SEARCH_CACHE = {} 
CACHE_DURATION = 3600  # 1 hour in seconds

@app.get("/")
def home():
    return {"message": "Grocery AI Backend is Running!"}

@app.post("/api/compare")
async def compare_prices(request: Request):
    data = await request.json()
    items = data.get("items", [])
    
    if not items:
        return {"status": "error", "message": "No items provided"}

    query = items[0]  # We focus on the first item for now
    current_time = time.time()

    # 1. CHECK CACHE FIRST
    if query in SEARCH_CACHE:
        cached_data, timestamp = SEARCH_CACHE[query]
        age = current_time - timestamp
        if age < CACHE_DURATION:
            print(f"⚡ CACHE HIT: Serving '{query}' instantly!")
            return {"status": "success", "data": cached_data}

    # 2. IF NOT IN CACHE, SCRAPE (New Fast Method)
    print(f"🐢 CACHE MISS: Scraping fresh data for '{query}'...")
    
    # Calls the new 'scrape_all_retailers' which does BigC+Tops+Makro in one go
    raw_data = await retailer_scraper.scrape_all_retailers(query)
    
    # 3. RUN AI FILTER
    matcher = SmartMatcher(raw_data)
    best_deals = matcher.find_matches(query)
    
    # 4. SAVE TO CACHE
    SEARCH_CACHE[query] = (best_deals, current_time)
    
    return {"status": "success", "data": best_deals}