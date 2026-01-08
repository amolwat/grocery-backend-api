import asyncio
from playwright.async_api import async_playwright

async def scrape_all_retailers(query: str):
    """
    🚀 OPTIMIZED SCRAPER:
    - Launches Browser ONCE (saves ~8 seconds)
    - Blocks Images/Fonts (saves bandwidth)
    - Scrapes BigC, Tops, and Makro in one go
    """
    
    # 1. Store Configuration
    retailers = [
        {
            "name": "BigC",
            "url": "https://www.bigc.co.th/search?q={q}",
            "selectors": {
                "product_card": ".productItem",
                "name": ".product-name",
                "price": ".product-price"
            }
        },
        {
            "name": "Tops",
            "url": "https://www.tops.co.th/en/search/{q}",
            "selectors": {
                "product_card": ".product-item",
                "name": ".product-title",
                "price": ".current-price"
            }
        },
        {
            "name": "Makro",
            "url": "https://www.makro.pro/en/search/?q={q}",
            "selectors": {
                "product_card": ".product-card", 
                "name": "[data-testid='product-title']",
                "price": "[data-testid='product-price']"
            }
        }
    ]

    all_results = []

    print(f"🚀 Starting scrape for: {query}")
    async with async_playwright() as p:
        # 2. Launch Browser (Headless & Low CPU)
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-gl-drawing']
        )
        
        # 3. Global Context (Blocks images for ALL tabs)
        context = await browser.new_context()
        await context.route("**/*", lambda route: 
            route.abort() if route.request.resource_type in ["image", "media", "font", "stylesheet"] 
            else route.continue_()
        )

        # 4. Scrape Loop
        for shop in retailers:
            print(f"🛒 Scraping {shop['name']}...")
            try:
                page = await context.new_page()
                target_url = shop["url"].format(q=query)
                
                try:
                    # Fast timeout (12s max per site)
                    await page.goto(target_url, timeout=12000, wait_until="domcontentloaded")
                    
                    # Wait for items
                    try:
                        await page.wait_for_selector(shop["selectors"]["product_card"], timeout=5000)
                    except:
                        print(f"   ⚠️ {shop['name']} found no items (Timeout/Empty)")
                        await page.close()
                        continue

                    # Extract Data
                    cards = await page.query_selector_all(shop["selectors"]["product_card"])
                    count = 0
                    for card in cards:
                        if count >= 8: break # Limit to top 8 items per store
                        try:
                            name_el = await card.query_selector(shop["selectors"]["name"])
                            price_el = await card.query_selector(shop["selectors"]["price"])
                            
                            if name_el and price_el:
                                n = await name_el.inner_text()
                                p_txt = await price_el.inner_text()
                                
                                # Clean Price (Remove '฿' and comma)
                                p_clean = p_txt.replace("฿", "").replace(",", "").split("\n")[0].strip()
                                
                                all_results.append({
                                    "Retailer": shop["name"],
                                    "Product Name": n.strip(),
                                    "Price": float(p_clean) if p_clean else 0.0,
                                    "Unit Price": float(p_clean) if p_clean else 0.0
                                })
                                count += 1
                        except:
                            continue
                except Exception as e:
                    print(f"   ❌ Error on {shop['name']}: {e}")
                
                await page.close() # Close tab immediately to free RAM
                
            except Exception as e:
                print(f"Critical Error {shop['name']}: {e}")

        await browser.close()
    
    print(f"✅ Scrape Complete. Found {len(all_results)} items.")
    return all_results