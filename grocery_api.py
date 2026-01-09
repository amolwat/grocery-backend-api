# grocery_api.py
import sys
import asyncio
import json
import pandas as pd
import uvicorn
import nest_asyncio
from typing import List
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

nest_asyncio.apply()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from retailer_scraper import scrape_all_retailers
from ai_matcher import SmartMatcher
import database

# =============================
# APP INIT
# =============================
app = FastAPI()

# ✅ CORS (FIX FLUTTER WEB)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # dev mode
    allow_credentials=True,
    allow_methods=["*"],        # POST, OPTIONS
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    database.init_db()

class CompareRequest(BaseModel):
    items: List[str]

# =============================
# ROOT (Health Check)
# =============================
@app.get("/")
def home():
    return {"status": "ok", "service": "Grocery AI Compare API"}

# =============================
# CORE LOGIC
# =============================
def best_per_retailer(item: str, deals: List[dict]) -> List[dict]:
    best = {}
    for d in deals:
        r = d.get("WINNER", "Unknown")
        try:
            up = float(d.get("Unit Price", 999999))
        except:
            up = 999999
        if r not in best or up < float(best[r].get("Unit Price", 999999)):
            best[r] = d

    out = []
    for r, d in best.items():
        out.append({
            "WINNER": r,
            "Product Name": d.get("Product Name"),
            "Best Price": f"฿{float(d.get('Price',0)):.2f}",
            "Unit Price": f"฿{float(d.get('Unit Price',0)):.2f}/{d.get('BaseUnit','unit')}",
            "_raw_unit_price": float(d.get("Unit Price",0)),
            "query_item": item
        })
    out.sort(key=lambda x: x["_raw_unit_price"])
    return out

# =============================
# MAIN API
# =============================
@app.post("/api/compare")
async def compare_prices(req: CompareRequest, background_tasks: BackgroundTasks):
    results = []

    for item in req.items:
        item = item.strip()
        if not item:
            continue

        # 1️⃣ Cache
        cached = database.get_cached_data(item, max_age_seconds=60*60*4)
        if cached:
            results.extend(cached)
            continue

        # 2️⃣ Scrape
        raw = await scrape_all_retailers(item)

        if raw:
            df = pd.DataFrame(raw)
            engine = SmartMatcher(json.loads(df.to_json(orient="records")))
            matches = engine.find_matches(item, threshold=0.42)
            best = best_per_retailer(item, matches[:25])
            database.save_to_cache(item, best)
            results.extend(best)

    return {
        "status": "success",
        "data": results
    }

# =============================
# ENTRYPOINT
# =============================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
