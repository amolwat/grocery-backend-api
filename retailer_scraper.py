# retailer_scraper.py
import random
import re
from typing import List, Dict, Any
from urllib.parse import quote
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

HEADLESS = True

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
]

def clean_text(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip() if t else ""

def extract_price(text: str) -> float:
    m = re.search(r"(฿|บาท)\s*(\d+(?:\.\d+)?)", text)
    return float(m.group(2)) if m else 0.0

async def scrape_all_retailers(query: str) -> List[Dict[str, Any]]:
    q = quote(query)
    results = []

    retailers = [
        ("BigC", f"https://www.bigc.co.th/th/search?q={q}", ".productItem", ".product-name"),
        ("Tops", f"https://www.tops.co.th/en/search/{q}", ".product-item-info", ".product-item-link"),
        ("Makro", f"https://www.makro.pro/en/c/search?q={q}", ".product-card", "span"),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="th-TH"
        )

        await context.route(
            "**/*",
            lambda r, req: r.abort() if req.resource_type in ["image","media","font"] else r.continue_()
        )

        for name, url, card_sel, name_sel in retailers:
            page = await context.new_page()
            try:
                await page.goto(url, timeout=15000)
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                for card in soup.select(card_sel)[:10]:
                    txt = clean_text(card.get_text(" "))
                    price = extract_price(txt)
                    if price <= 0:
                        continue

                    results.append({
                        "WINNER": name,
                        "Product Name": txt[:120],
                        "Price": price,
                        "Unit Price": price,
                        "BaseUnit": "unit"
                    })
            except:
                pass
            await page.close()

        await browser.close()

    return results
