import sys
import asyncio
import json
import pandas as pd
import uvicorn
import nest_asyncio
import time
from typing import List
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

# Allow nested event loops
nest_asyncio.apply()
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# IMPORT MODULES
# Note: We now import 'scrape_all_retailers' instead of 'scrape_search'
from retailer_scraper import scrape_all_retailers 
from ai_matcher import SmartMatcher
import database

# ==========================================
# 🔧 CONFIG & INIT
# ==========================================
app = FastAPI()

# Initialize DB on Startup
@app.on_event("startup")
def startup_event():
    database.init_db()

class CompareRequest(BaseModel):
    items: List[str]

# ==========================================
# 🧠 HELPER FUNCTIONS
# ==========================================
def best_per_retailer(item: str, deals: List[dict]) -> List[dict]:
    """
    Groups results by Retailer and picks the ONE best option for each.
    """
    best = {}
    for d in deals:
        retailer = d.get("WINNER", "Unknown")
        try: unit_price = float(d.get("Unit Price", 999999))
        except: unit_price = 999999.0

        if retailer not in best or unit_price < float(best[retailer].get("Unit Price", 999999)):
            best[retailer] = d

    out = []
    for retailer, d in best.items():
        unit = d.get("BaseUnit", "unit")
        try: raw_price = float(d.get("Price", 0))
        except: raw_price = 0.0
        try: raw_unit_price = float(d.get("Unit Price", 0))
        except: raw_unit_price = 0.0
        
        # Simple Promo logic
        original_price = raw_price 
        is_promo = False

        out.append({
            "WINNER": retailer,
            "Product Name": d.get("Product Name", ""),
            "Product Type": "",
            "Best Price": f"฿{raw_price:.2f}",
            "Unit Price": f"฿{raw_unit_price:.2f}/{unit}",
            "_raw_price": raw_price,
            "_raw_unit_price": raw_unit_price,
            "is_promo": is_promo,
            "original_price": original_price if is_promo else None,
            "query_item": item,
        })
    
    out.sort(key=lambda x: float(x.get("_raw_unit_price", 999999)))
    return out

# ==========================================
# 🚀 BACKGROUND UPDATER
# ==========================================
async def update_cache_background(item: str):
    print(f"👷 BACKGROUND: Updating cache for '{item}'...")
    raw_data = await scrape_all_retailers(item)
    
    # Process AI Logic here before saving
    if raw_data:
        try:
            df = pd.DataFrame(raw_data)
            candidates = json.loads(df.to_json(orient="records"))
            engine = SmartMatcher(candidates)
            matches = engine.find_matches(item, threshold=0.42)
            final_best = best_per_retailer(item, matches[:30])
            
            # Save processed results to DB
            database.save_to_cache(item, final_best)
            print(f"✅ BACKGROUND: Saved {len(final_best)} deals for '{item}'")
        except Exception as e:
            print(f"❌ BACKGROUND ERROR: {e}")

# ==========================================
# 🔌 API ENDPOINTS
# ==========================================
@app.post("/api/prime_cache")
async def prime_cache(req: CompareRequest, background_tasks: BackgroundTasks):
    """
    Manually trigger background scraping for a list of items.
    Usage: Call this with ["Pork", "Rice", "Oil"] to pre-load DB.
    """
    for item in req.items:
        background_tasks.add_task(update_cache_background, item)
    return {"status": "success", "message": f"Queued {len(req.items)} items for background scraping"}

@app.post("/api/compare")
async def compare_prices(req: CompareRequest, background_tasks: BackgroundTasks):
    final_results = []
    
    for item in req.items:
        clean_item = (item or "").strip()
        if not clean_item: continue
        
        # 1. CHECK DATABASE (Instant)
        cached_data = database.get_cached_data(clean_item, max_age_seconds=3600*4) # 4 Hours Cache
        
        if cached_data:
            print(f"⚡ DB HIT: Serving '{clean_item}' instantly!")
            final_results.extend(cached_data)
        else:
            # 2. CACHE MISS (Slow Scrape)
            print(f"🐢 DB MISS: Scraping fresh for '{clean_item}'...")
            
            # Scrape
            raw_data = await scrape_all_retailers(clean_item)
            
            # AI Match
            matches = []
            if raw_data:
                df = pd.DataFrame(raw_data)
                candidates = json.loads(df.to_json(orient="records"))
                engine = SmartMatcher(candidates)
                matches = engine.find_matches(clean_item, threshold=0.42)
            
            # Group Best
            best_deals = best_per_retailer(clean_item, matches[:30])
            
            # Save to DB for next time
            database.save_to_cache(clean_item, best_deals)
            
            final_results.extend(best_deals)

    return {
        "status": "success", 
        "message": "Comparison complete", 
        "data": final_results
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)