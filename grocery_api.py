import sys
import asyncio
import json
import pandas as pd
import uvicorn
import nest_asyncio
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel

# Allow nested event loops (Critical for Playwright + FastAPI)
nest_asyncio.apply()
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# IMPORT YOUR MODULES
# Ensure retailer_scraper.py is in the same folder
from retailer_scraper import scrape_search, find_best_deals
from ai_matcher import SmartMatcher

# ==========================================
# 🔧 CONFIG
# ==========================================
TARGETS = [
    {
        "name": "BigC",
        "search_url": "https://www.bigc.co.th/en/search?q={q}",
        "selectors": {"product_card": 'div.productItem, div[data-testid="product-card"]', "name": ".product-name", "price": ".product-price"},
    },
    {
        "name": "Tops",
        "search_url": "https://www.tops.co.th/en/search/{q}",
        "selectors": {"product_card": ".product-item-info", "name": ".product-item-link", "price": ".price"},
    },
    {
        "name": "Makro",
        "search_url": "https://www.makro.pro/en/c/search?q={q}",
        "selectors": {"product_card": 'div[class*="product-card"]', "name": 'span[class*="name"]', "price": 'span[class*="price"]'},
    },
]

app = FastAPI()

class CompareRequest(BaseModel):
    items: List[str]

# ==========================================
# 🧠 HELPER FUNCTIONS
# ==========================================
def best_per_retailer(item: str, deals: List[dict]) -> List[dict]:
    """
    Groups results by Retailer (BigC, Tops, Makro) and picks the ONE best option for each.
    """
    best = {}
    for d in deals:
        retailer = d.get("WINNER", "Unknown")
        try: unit_price = float(d.get("Unit Price", 999999))
        except: unit_price = 999999.0

        # Logic: If we haven't seen this retailer yet, OR this item is cheaper -> Pick it
        if retailer not in best or unit_price < float(best[retailer].get("Unit Price", 999999)):
            best[retailer] = d

    out = []
    for retailer, d in best.items():
        # Re-format for the Frontend/JSON response
        unit = d.get("BaseUnit", "unit")
        try: raw_price = float(d.get("Price", 0))
        except: raw_price = 0.0
        try: raw_unit_price = float(d.get("Unit Price", 0))
        except: raw_unit_price = 0.0
        try: original_price = float(d.get("Original Price", raw_price))
        except: original_price = raw_price
        
        is_promo = original_price > raw_price

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
    
    # Sort final list by Unit Price (Cheapest first)
    out.sort(key=lambda x: float(x.get("_raw_unit_price", 999999)))
    return out

# ==========================================
# 🚀 MAIN PROCESS
# ==========================================
async def process_single_item(item: str) -> List[dict]:
    print(f"🔎 Processing: {item}")
    
    # 1. SCRAPE (Parallel Requests)
    scrape_tasks = []
    for t in TARGETS:
        scrape_tasks.append(scrape_search(t["name"], t["search_url"], item, t["selectors"]))

    # Wait for all scrapers to finish
    results_lists = await asyncio.gather(*scrape_tasks, return_exceptions=True)
    
    # Flatten list of lists
    raw_data = []
    for res in results_lists:
        if isinstance(res, list): 
            raw_data.extend(res)

    if not raw_data: 
        print(f"⚠️ No results found for {item}")
        return []

    try:
        # Convert to Pandas
        df = pd.DataFrame(raw_data)
        
        # 2. PRE-PROCESS (Unit Normalization)
        # Using the regex logic in retailer_scraper.py
        processed = find_best_deals(df)
        candidates = json.loads(processed.to_json(orient="records"))
        
        # 3. AI MATCHING & FILTERING
        # Initialize the AI Brain with the candidates
        engine = SmartMatcher(candidates)
        
        # Ask AI to filter matches (using Vectors + Meat Rules + Trap Checks)
        matches = engine.find_matches(item, threshold=0.42) 

        # 4. GROUPING
        # Return the best single item per retailer
        return best_per_retailer(item, matches[:30])
        
    except Exception as e:
        print(f"❌ Core Logic Error: {e}")
        import traceback
        traceback.print_exc()
        return []

# ==========================================
# 🔌 API ENDPOINTS
# ==========================================
@app.post("/api/compare")
async def compare_prices(req: CompareRequest):
    """
    Receives: {"items": ["Pork Belly", "Coke Zero"]}
    Returns: JSON with best deals per item per retailer.
    """
    final_results = []
    for item in req.items:
        clean_item = (item or "").strip()
        if not clean_item: continue
        
        results = await process_single_item(clean_item)
        final_results.extend(results)
        
    return {
        "status": "success", 
        "message": "Comparison complete", 
        "data": final_results
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)