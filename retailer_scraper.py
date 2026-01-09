import asyncio
import random
import re
import gc # Garbage Collector
from typing import List, Dict, Any
from urllib.parse import quote
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# ==========================================
# 🔧 CONFIG & HELPERS
# ==========================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Optimize Browser Args for Low Memory
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--single-process", # Helps on low-RAM envs
    "--disable-gl-drawing"
]

HEADLESS = True 

# --- KEEP YOUR HELPER FUNCTIONS (clean_text, extract_price, etc.) ---
# (Paste your existing helper functions here: clean_text, extract_price, 
# extract_egg_quantity, normalize_unit_data, clean_product_name)
# I will not repeat them to save space, but DO NOT DELETE THEM!
def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip() if text else ""

def extract_price(text: str) -> float:
    if not text: return 0.0
    t = text.replace(",", "").strip()
    promo_patterns = [r"(?:promo|promotion|special|ลดเหลือ|เหลือเพียง)\s*฿?\s*(\d+(?:\.\d+)?)", r"฿\s*(\d+(?:\.\d+)?)\s*(?:from|แทน)"]
    for p in promo_patterns:
        m = re.search(p, t, flags=re.I)
        if m: return float(m.group(1))
    m = re.search(r"(?:฿|บาท|THB)\s*(\d+(?:\.\d{1,2})?)", t, flags=re.I)
    if m: return float(m.group(1))
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d{1,2})?", t)]
    nums = [n for n in nums if n >= 5] 
    return min(nums) if nums else 0.0

def extract_egg_quantity(text: str) -> float:
    s = text.lower().replace(" ", "")
    m = re.search(r"(\d+)(?:ฟอง|egg|eggs|pcs|ใบ)", s)
    if m: return float(m.group(1))
    m = re.search(r"(?:pack|แพ็ค|x)(\d+)", s)
    if m: return float(m.group(1))
    return 1.0

def normalize_unit_data(name: str, raw_qty: str, price: float):
    s = raw_qty.lower()
    s = re.sub(r"\b(\d+)\s+\1\b", r"\1", s)
    s = s.replace(" ", "")
    name_lower = name.lower()
    if "egg" in name_lower or "ไข่" in name_lower:
        qty = extract_egg_quantity(name + " " + s)
        return qty, "egg", round(price / qty, 2) if qty > 0 else price
    unit_regex = r"(kg|kgs|kilo|g|gm|ml|l|liter|pack|packs|pcs|piece|pieces|ขวด|แพ็ค|แพค|ชิ้น|กระป๋อง|กล่อง|กรัม|ก\.|กิโลกรัม|กิโล|กก\.?|ก\.ก\.?|มล\.?|ลิตร|ล\.?)"
    qty = 1.0; unit = "pcs"
    m1 = re.search(rf"(\d+(?:\.\d+)?)[x\*](\d+(?:\.\d+)?){unit_regex}", s)
    m2 = re.search(rf"(\d+(?:\.\d+)?){unit_regex}[x\*](\d+(?:\.\d+)?)", s)
    m3 = re.search(rf"(\d+(?:\.\d+)?){unit_regex}", s)
    if m1: qty = float(m1.group(1)) * float(m1.group(2)); unit = m1.group(3)
    elif m2: qty = float(m2.group(1)) * float(m2.group(3)); unit = m2.group(2)
    elif m3: qty = float(m3.group(1)); unit = m3.group(2)
    final_qty = qty; final_unit = "pcs"
    if unit in ["g", "gm", "กรัม", "ก."]: final_qty = qty / 1000.0; final_unit = "kg"
    elif unit in ["ml", "มล."]: final_qty = qty / 1000.0; final_unit = "L"
    elif any(u in unit for u in ["kg", "kilo", "กิโล", "กก", "l", "liter", "ลิตร", "ล."]):
        final_qty = qty
        if any(u in unit for u in ["l", "liter", "ลิตร", "ล."]): final_unit = "L"
        else: final_unit = "kg"
    if final_unit == "pcs":
        is_fresh_food = any(w in name_lower for w in ["pork", "chicken", "salmon", "fish", "meat", "beef", "หมู", "ไก่", "ปลา", "เนื้อ", "แซลมอน"])
        has_kg_keyword = any(w in name_lower for w in ["kg", "kilo", "กก", "กิโล", "/kg", "ต่อกก"])
        if is_fresh_food and has_kg_keyword: final_unit = "kg"; final_qty = 1.0
    if final_qty <= 0: final_qty = 1.0
    return final_qty, final_unit, round(price / final_qty, 2)

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

# ==========================================
# 🚀 RAM-SAFE SCRAPER (The Fix)
# ==========================================
async def scrape_all_retailers(query: str) -> List[Dict[str, Any]]:
    """
    Scrapes retailers sequentially, cleaning RAM after each one.
    """
    # 1. UNCOMMENT EVERYTHING
    retailers = [
        {
            "name": "BigC",
            "url_template": "https://www.bigc.co.th/en/search?q={q}",
            "selectors": {"product_card": 'div.productItem, div[data-testid="product-card"]', "name": ".product-name", "price": ".product-price"}
        },
        {
            "name": "Tops",
            "url_template": "https://www.tops.co.th/en/search/{q}",
            "selectors": {"product_card": ".product-item-info", "name": ".product-item-link", "price": ".price"}
        },
        {
            "name": "Makro",
            "url_template": "https://www.makro.pro/en/c/search?q={q}",
            "selectors": {"product_card": 'div[class*="product-card"]', "name": 'span[class*="name"]', "price": 'span[class*="price"]'}
        }
    ]

    all_results = []
    q_raw = (query or "").strip()
    if not q_raw: return []
    q_encoded = quote(q_raw, safe="")

    print(f"🚀 RAM-SAFE Scrape Started: {q_raw}")

    async with async_playwright() as p:
        # Launch Browser ONCE
        browser = await p.chromium.launch(headless=HEADLESS, args=BROWSER_ARGS)
        
        for shop in retailers:
            print(f"🛒 Scraping {shop['name']}...")
            
            # --- CRITICAL: New Context for EACH Shop ---
            # This isolates the memory. When we close it, RAM is freed.
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1024, "height": 768}, # Smaller screen saves RAM
                locale="th-TH"
            )
            # Block images aggressively
            await context.route("**/*", lambda route, request: route.abort() if request.resource_type in ["image", "media", "font", "stylesheet"] else route.continue_())

            page = await context.new_page()
            
            try:
                # BigC Logic
                final_url = shop["url_template"].format(q=q_encoded)
                if shop["name"] == "BigC":
                    has_thai = any("\u0E00" <= ch <= "\u0E7F" for ch in q_raw)
                    final_url = f"https://www.bigc.co.th/th/search?q={q_encoded}" if has_thai else f"https://www.bigc.co.th/en/search?q={q_encoded}"

                # Strict Timeout (12s max) - If it hangs, kill it to save the server
                try:
                    await page.goto(final_url, timeout=12000, wait_until="domcontentloaded")
                    
                    try:
                        await page.wait_for_selector(shop["selectors"]["product_card"], timeout=5000)
                    except:
                        pass # Continue even if timeout, maybe content loaded

                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    cards = soup.select(shop["selectors"]["product_card"])

                    count = 0
                    for card in cards:
                        if count >= 8: break # Lower limit to 8 items per store
                        try:
                            name_el = card.select_one(shop["selectors"]["name"])
                            if not name_el: continue
                            
                            raw_name = clean_text(name_el.get_text(" "))
                            card_text = clean_text(card.get_text(" "))
                            price = extract_price(card_text)
                            
                            if price <= 4: continue

                            final_name = clean_product_name(raw_name, price)
                            qty, unit, u_price = normalize_unit_data(final_name, card_text, price)

                            all_results.append({
                                "WINNER": shop["name"],
                                "Product Name": final_name,
                                "Product Type": "",
                                "Quantity": card_text[:50],
                                "BaseQty": qty,
                                "BaseUnit": unit,
                                "Price": price,
                                "Unit Price": u_price,
                            })
                            count += 1
                        except: continue

                except Exception as e:
                    print(f"   ⚠️ {shop['name']} Timeout/Error: {e}")

            except Exception as e:
                print(f"   ❌ Critical {shop['name']}: {e}")
            
            finally:
                # --- CRITICAL: CLOSE EVERYTHING IMMEDIATELY ---
                await page.close()
                await context.close()
                gc.collect() # Force Python to clean RAM
        
        await browser.close()
    
    print(f"✅ Batch Scrape Complete. Found {len(all_results)} items.")
    return all_results

def find_best_deals(df): return df