import re
import pandas as pd
from difflib import SequenceMatcher

# ==================================================
# 🧠 CONFIG: KNOWLEDGE BASE (Keep your Trap Lists)
# ==================================================
# ... (Paste your existing Trap Lists here: INGREDIENT_CONCEPTS, PET_KEYWORDS, etc.) ...
# I am skipping them here to save space, but DO NOT DELETE THEM from your file.

# ❌ REMOVED: AIModelHandler Class (This was the RAM killer)

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

# ==================================================
# ⚡ LITE MATCHER (No Heavy AI)
# ==================================================
class SmartMatcher:
    def __init__(self, scraped_data: list):
        self.df = pd.DataFrame(scraped_data)
        # We do NOT load any vector model here. RAM Saved: ~400MB.

    # ----------------------------------------
    # 🛡️ TRAP & RULE FUNCTIONS (Keep these!)
    # ----------------------------------------
    # (Copy your existing _is_trap, _check_meat_mismatch, etc. functions here)
    # They work perfectly fine without the AI model.
    
    def _is_trap(self, name: str, query: str) -> bool:
        # ... (Your existing code) ...
        return False # Placeholder if you don't paste the full code

    # ----------------------------------------
    # ⚡ NEW: FAST SIMILARITY CHECK
    # ----------------------------------------
    def calculate_similarity(self, a, b):
        # This compares how many letters match. 
        # "Coke Can" vs "Coke" = 0.8 score
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def find_matches(self, user_query: str, threshold=0.25):
        if self.df.empty: return []

        q = user_query.strip()
        final_results = []
        
        for _, row in self.df.iterrows():
            name = str(row["Product Name"])
            
            # 1. Run Rules (Optional but recommended)
            # if self._is_trap(name, q): continue

            # 2. Calculate Score
            score = self.calculate_similarity(q, name)
            
            # 3. Boost for containing the exact word
            if q.lower() in name.lower():
                score += 0.4  # Big bonus if "Coke" is inside the name
            
            if score >= threshold:
                row["score"] = score
                final_results.append(row)

        if not final_results: return []

        # Sort by best match
        df_final = pd.DataFrame(final_results)
        df_final = df_final.sort_values(by="score", ascending=False).head(20)
        
        return df_final.to_dict(orient="records")