# retailer_scraper.py
import asyncio
import random
import re
from typing import List, Dict, Any

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-infobars",
    "--ignore-certificate-errors",
    "--disable-dev-shm-usage",
]

HEADLESS = True 

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip() if text else ""

def extract_price(text: str) -> float:
    if not text: return 0.0
    t = text.replace(",", "").strip()
    
    # Promo Price First
    promo_patterns = [
        r"(?:promo|promotion|special|ลดเหลือ|เหลือเพียง)\s*฿?\s*(\d+(?:\.\d+)?)",
        r"฿\s*(\d+(?:\.\d+)?)\s*(?:from|แทน)",
    ]
    for p in promo_patterns:
        m = re.search(p, t, flags=re.I)
        if m: return float(m.group(1))

    # Standard Price
    m = re.search(r"(?:฿|บาท|THB)\s*(\d+(?:\.\d{1,2})?)", t, flags=re.I)
    if m: return float(m.group(1))

    # Fallback
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d{1,2})?", t)]
    nums = [n for n in nums if n >= 5] 
    return min(nums) if nums else 0.0

# Egg Unit Parser
def extract_egg_quantity(text: str) -> float:
    s = text.lower().replace(" ", "")
    m = re.search(r"(\d+)(?:ฟอง|egg|eggs|pcs|ใบ)", s)
    if m: return float(m.group(1))
    m = re.search(r"(?:pack|แพ็ค|x)(\d+)", s)
    if m: return float(m.group(1))
    return 1.0

# ✅ FIXED: Robust Unit Normalizer
def normalize_unit_data(name: str, raw_qty: str, price: float):
    # 1. Clean Duplicate Numbers (Fixes "12 12")
    s = raw_qty.lower()
    s = re.sub(r"\b(\d+)\s+\1\b", r"\1", s)
    s = s.replace(" ", "")
    
    name_lower = name.lower()

    # 2. Egg Logic
    if "egg" in name_lower or "ไข่" in name_lower:
        qty = extract_egg_quantity(name + " " + s)
        unit = "egg"
        unit_price = round(price / qty, 2) if qty > 0 else price
        return qty, unit, unit_price

    # 3. Standard Unit Logic (Updated Regex for Thai KG)
    # Added: กก (no dot), กก., kgs, kg.
    unit_regex = r"(kg|kgs|kilo|g|gm|ml|l|liter|pack|packs|pcs|piece|pieces|ขวด|แพ็ค|แพค|ชิ้น|กระป๋อง|กล่อง|กรัม|ก\.|กิโลกรัม|กิโล|กก\.?|ก\.ก\.?|มล\.?|ลิตร|ล\.?)"

    qty = 1.0
    unit = "pcs"

    # Pattern A: "3 x 100g"
    m1 = re.search(rf"(\d+(?:\.\d+)?)[x\*](\d+(?:\.\d+)?){unit_regex}", s)
    # Pattern B: "100g x 3"
    m2 = re.search(rf"(\d+(?:\.\d+)?){unit_regex}[x\*](\d+(?:\.\d+)?)", s)
    # Pattern C: "100g"
    m3 = re.search(rf"(\d+(?:\.\d+)?){unit_regex}", s)

    if m1: 
        qty = float(m1.group(1)) * float(m1.group(2))
        unit = m1.group(3)
    elif m2:
        qty = float(m2.group(1)) * float(m2.group(3))
        unit = m2.group(2)
    elif m3:
        qty = float(m3.group(1))
        unit = m3.group(2)

    # 4. Convert to Base Units (kg, L, pcs)
    final_qty = qty
    final_unit = "pcs"

    if unit in ["g", "gm", "กรัม", "ก."]: 
        final_qty = qty / 1000.0
        final_unit = "kg"
    elif unit in ["ml", "มล."]: 
        final_qty = qty / 1000.0
        final_unit = "L"
    elif any(u in unit for u in ["kg", "kilo", "กิโล", "กก", "l", "liter", "ลิตร", "ล."]):
        final_qty = qty
        # Detect if it's weight (kg) or volume (L)
        if any(u in unit for u in ["l", "liter", "ลิตร", "ล."]):
            final_unit = "L"
        else:
            final_unit = "kg"
    
    # ✅ 5. FORCE KG FOR MEAT/FISH (The Big Fix)
    # If we failed to find a weight unit, BUT the name implies it's sold by weight
    if final_unit == "pcs":
        is_fresh_food = any(w in name_lower for w in ["pork", "chicken", "salmon", "fish", "meat", "beef", "หมู", "ไก่", "ปลา", "เนื้อ", "แซลมอน"])
        has_kg_keyword = any(w in name_lower for w in ["kg", "kilo", "กก", "กิโล", "/kg", "ต่อกก"])
        
        if is_fresh_food and has_kg_keyword:
            final_unit = "kg"
            final_qty = 1.0 # Assume price is per 1 kg if listed as "Pork ... kg"

    # Avoid division by zero
    if final_qty <= 0: final_qty = 1.0
    
    u_price = round(price / final_qty, 2)
    return final_qty, final_unit, u_price

def clean_product_name(name: str, price: float) -> str:
    if not name: return ""
    x = name
    x = re.sub(r"(?:buy|ซื้อ)\s*[\d,.]+\s*(?:B|฿|บาท)\s*(?:\+\d+)?", " ", x, flags=re.I)
    x = re.sub(r"(?:get|รับ|earn|ฟรี)\s*[\d,.]+\s*(?:points|pts|คะแนน)", " ", x, flags=re.I)
    x = re.sub(r"\bToday\s*[\d,.]*", " ", x, flags=re.I)
    x = re.sub(r"\d+\+\s*units\s*-\d+%", " ", x, flags=re.I)
    x = re.sub(r"^[\d,.]+\s*(?:/|-|บาท|THB|B)\s*(?:pack|pcs|ชิ้น|แพ็ค|kg|g|ขวด|กระป๋อง)?\s*", " ", x, flags=re.I)
    x = re.sub(r"\s+\d{2,}\s*\d*\s*$", "", x)
    x = re.sub(r"(฿|THB|บาท)", "", x, flags=re.I)
    x = re.sub(r"\s+", " ", x).strip()
    x = re.sub(r"^[^a-zA-Z0-9ก-๙\"'(]+", "", x)
    return x[:120].strip()

def heuristic_scrape(soup: BeautifulSoup, retailer: str) -> List[Dict[str, Any]]:
    products = []
    price_nodes = soup.find_all(string=re.compile(r"(฿|บาท|THB)", re.I))
    seen = set()

    for node in price_nodes:
        el = node.parent
        if not el: continue
        block = el
        for _ in range(5):
            if block and len(clean_text(block.get_text(" "))) < 40: block = block.parent
            else: break
        if not block: continue

        text = clean_text(block.get_text(" "))
        if text in seen: continue
        seen.add(text)

        price = extract_price(text)
        if price < 5: continue

        final_name = clean_product_name(text, price)
        # Pass NAME to allow smart unit logic
        qty, unit, u_price = normalize_unit_data(final_name, text, price)

        products.append({
            "WINNER": retailer,
            "Product Name": final_name,
            "Product Type": "",
            "Quantity": "1 Unit",
            "BaseQty": qty,
            "BaseUnit": unit,
            "Price": price,
            "Unit Price": u_price,
        })
    return products

async def scrape_search(retailer_name: str, search_url_template: str, query: str, selector_config: Dict[str, str]) -> List[Dict[str, Any]]:
    from urllib.parse import quote
    q_raw = (query or "").strip()
    if not q_raw: return []
    q_encoded = quote(q_raw, safe="")
    
    if retailer_name.lower() == "bigc":
        has_thai = any("\u0E00" <= ch <= "\u0E7F" for ch in q_raw)
        url = f"https://www.bigc.co.th/th/search?q={q_encoded}" if has_thai else f"https://www.bigc.co.th/en/search?q={q_encoded}"
    else:
        url = search_url_template.format(q=q_encoded)

    print(f"🔎 {retailer_name} searching: {url}")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, args=BROWSER_ARGS)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            locale="th-TH",
        )
        await context.route("**/*", lambda route, request: route.abort() if request.resource_type in ["image", "media", "font"] else route.continue_())
        page = await context.new_page()

        try:
            try: await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            except: return []

            await page.wait_for_timeout(2000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            cards = soup.select(selector_config["product_card"])
            page_items = []

            if cards:
                for card in cards[:30]:
                    try:
                        name_el = card.select_one(selector_config["name"])
                        if not name_el: continue
                        
                        raw_name = clean_text(name_el.get_text(" "))
                        card_text = clean_text(card.get_text(" "))
                        price = extract_price(card_text)
                        if price <= 4: continue

                        raw_qty = card_text 
                        final_name = clean_product_name(raw_name, price)
                        
                        # ✅ PASS NAME to normalize for smart unit detection
                        qty, unit, u_price = normalize_unit_data(final_name, raw_qty, price)

                        page_items.append({
                            "WINNER": retailer_name,
                            "Product Name": final_name,
                            "Product Type": "",
                            "Quantity": raw_qty,
                            "BaseQty": qty,
                            "BaseUnit": unit,
                            "Price": price,
                            "Unit Price": u_price,
                        })
                    except: continue
            
            if not page_items:
                page_items = heuristic_scrape(soup, retailer_name)

            results.extend(page_items)
        finally:
            await browser.close()

    print(f"✅ {retailer_name} found {len(results)} items")
    return results
# 
def find_best_deals(df):
    return df