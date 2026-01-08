import sqlite3
import json
import time

DB_NAME = "grocery_cache.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Create table if not exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS product_cache (
            query TEXT PRIMARY KEY,
            data TEXT,
            timestamp REAL
        )
    ''')
    conn.commit()
    conn.close()

def get_cached_data(query: str, max_age_seconds=3600):
    """
    Retrieve data from DB if it exists and isn't too old.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT data, timestamp FROM product_cache WHERE query = ?", (query,))
        row = c.fetchone()
        conn.close()

        if row:
            data_json, timestamp = row
            # Check if expired
            if time.time() - timestamp < max_age_seconds:
                return json.loads(data_json)
    except Exception as e:
        print(f"⚠️ DB Read Error: {e}")
    return None

def save_to_cache(query: str, data: list):
    """
    Save scraped data to DB.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        # Insert or Replace (Update)
        c.execute("INSERT OR REPLACE INTO product_cache (query, data, timestamp) VALUES (?, ?, ?)",
                (query, json.dumps(data), time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ DB Write Error: {e}")