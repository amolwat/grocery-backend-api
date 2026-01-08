import re
import pandas as pd
from sentence_transformers import SentenceTransformer, util
# ❌ REMOVED: from transformers import pipeline (Not needed anymore)

# ==================================================
# 🧠 CONFIG: KNOWLEDGE BASE
# ==================================================

# 1. POSITIVE CONCEPTS
INGREDIENT_CONCEPTS = [
    "Pork Belly", "Pork Loin", "Pork Collar", "Minced Pork", "Chicken Breast", 
    "Whole Chicken", "Beef Steak", "Salmon Fillet", "Shrimp", "Squid",
    "Fresh Milk", "Soy Milk", "Butter", "Cheese", "Egg",
    "Coffee", "Syrup", "Rice", "Noodle", "Cooking Oil", "Fish Sauce",
    "Carrot", "Vegetable", "Fruit", "Morning Glory", "Water Spinach",
    "Coke", "Pepsi", "Soda"
]

# 2. MEAT CUT RULES
MEAT_CUT_RULES = [
    {"triggers": ["สันคอ", "collar"], "avoid": ["สันนอก", "loin", "sirloin"]},
    {"triggers": ["สันนอก", "loin"], "avoid": ["สันคอ", "collar", "สันใน", "tenderloin"]},
    {"triggers": ["สามชั้น", "belly"], "avoid": ["เนื้อแดง", "red meat", "lean", "minced", "บด"]},
    {"triggers": ["บด", "minced", "ground"], "avoid": ["slice", "สไลซ์", "ชิ้น", "steak"]},
]

# 3. LOW QUALITY PARTS
LOW_QUALITY_PARTS = [
    "head", "bone", "scrap", "skin", "trimmings", "carcass", "offal",
    "หัว", "กาง", "เศษ", "หนัง", "โครง", "กาก"
]

# 4. PET FOOD TRAPS
PET_KEYWORDS = [
    "cat food", "dog food", "kitten", "puppy", "adult", "senior",
    "me-o", "whiskas", "pedigree", "smartheart", "smart heart", "nekko", 
    "regalos", "kaniva", "pouch", "flavor", "flavour",
    "อาหารแมว", "อาหารสุนัข", "แมว", "สุนัข", "สัตว์เลี้ยง"
]

# 5. NON-FOOD TRAPS
NON_FOOD_TRAPS = [
    "doll", "toy", "plush", "pillow", "cushion", "shirt", "bag", "keychain", "model",
    "ตุ๊กตา", "ของเล่น", "หมอน", "เสื้อ", "กระเป๋า", "พวงกุญแจ", "โมเดล"
]

# 6. PROCESSED & BABY TRAPS
PROCESSED_TRAPS = [
    # Baby Food
    "baby", "infant", "toddler", "junior", "cerelac", "peachy", 
    "porridge", "soup", "instant", "cereal", "powder", "puree",
    "เด็ก", "ทารก", "โจ๊ก", "ข้าวต้ม", "ซีรีแล็ค", "ผง", "สำเร็จรูป",
    
    # Cooking Agents
    "flour", "batter", "mix", "coating", "tempura", "breading", "unclebarns",
    "แป้ง", "ชุบ", "ทอดกรอบ", "เกล็ดขนมปัง",
    
    # Ready Meals
    "curry", "meal", "box", "frozen meal", "retort", "nugget",
    "แกง", "ข้าวกล่อง", "พร้อมทาน", "นักเก็ต"
]

# 7. LIQUID TRAPS
LIQUID_KEYWORDS = [
    "juice", "drink", "beverage", "nectar", "cider", "water",
    "unif", "malee", "tipco", "ivy", "chabaa", "doi kham",
    "น้ำ", "เครื่องดื่ม", "น้ำผลไม้", "สกัด", "ยูนิฟ"
]

# ==================================================
# MODEL LOADER
# ==================================================
class AIModelHandler:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            print("🤖 Loading AI Model (Vector Only)...")
            
            # 🚀 OPTIMIZATION: We only load ONE model now.
            # This handles all the text understanding.
            vector_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            
            # ❌ REMOVED: classifier = pipeline(...) 
            # We don't need it because our "Trap Lists" do the same job 100x faster.
            
            cls._instance = vector_model
            print("✅ AI Model Loaded")
        return cls._instance

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

# ==================================================
# SMART MATCHER CLASS
# ==================================================
class SmartMatcher:
    def __init__(self, scraped_data: list):
        self.df = pd.DataFrame(scraped_data)
        # 🚀 Only get the vector model
        self.vector_model = AIModelHandler.get_instance()
        self.vectors = None

        if not self.df.empty:
            self.df["search_text"] = self.df["Product Name"].astype(str)
            self.vectors = self.vector_model.encode(self.df["search_text"].tolist())

    # ----------------------------------------
    # 🛡️ RULE 1: TRAP BLOCKER
    # ----------------------------------------
    def _is_trap(self, name: str, query: str) -> bool:
        n = _norm(name)
        q = _norm(query)
        
        # A. Pet Food Check
        is_pet_query = any(k in q for k in ["cat", "dog", "pet", "แมว", "สุนัข"])
        if not is_pet_query:
            if any(k in n for k in PET_KEYWORDS): return True

        # B. Non-Food Check
        if any(k in n for k in NON_FOOD_TRAPS): return True
        
        # C. Processed/Baby Check
        is_processed_query = any(k in q for k in ["baby", "porridge", "soup", "flour", "curry", "โจ๊ก", "แป้ง", "แกง"])
        if not is_processed_query:
            if any(k in n for k in PROCESSED_TRAPS): return True

        # D. Liquid Check
        is_liquid_query = any(k in q for k in LIQUID_KEYWORDS)
        if not is_liquid_query:
            if any(k in n for k in LIQUID_KEYWORDS):
                safe_liquids = [
                    "sauce", "oil", "milk", "tea", "coffee", "syrup", 
                    "coke", "cola", "pepsi", "est", "sprite", "fanta", "soda", 
                    "ซอส", "น้ำมัน", "นม", "ชา", "กาแฟ", "โค้ก", "เป๊ปซี่", "โซดา"
                ]
                if any(safe in n for safe in safe_liquids):
                    return False
                return True
        return False

    # ----------------------------------------
    # 🛡️ RULE 2: MEAT ENFORCER
    # ----------------------------------------
    def _check_meat_mismatch(self, name: str, query: str) -> bool:
        n = _norm(name)
        q = _norm(query)
        for rule in MEAT_CUT_RULES:
            if any(t in q for t in rule["triggers"]):
                if any(bad in n for bad in rule["avoid"]):
                    return False 
        return True

    # ----------------------------------------
    # 🛡️ RULE 3: STRICT NUMBERS
    # ----------------------------------------
    def _check_strict_numbers(self, name: str, query: str) -> bool:
        q = _norm(query)
        n = _norm(name)
        pattern = r"(?:no\.?|เบอร์|number|size)\s*(\d+)"
        q_match = re.search(pattern, q)
        if not q_match: return True 

        target_num = q_match.group(1)
        n_matches = re.findall(pattern, n)
        if not n_matches: return True 
        if target_num not in n_matches: return False 
        return True

    # ----------------------------------------
    # 🛡️ RULE 4: QUALITY CHECK
    # ----------------------------------------
    def _is_low_quality_part(self, name: str, query: str) -> bool:
        q = _norm(query)
        n = _norm(name)
        if any(part in q for part in LOW_QUALITY_PARTS): return False
        if any(part in n for part in LOW_QUALITY_PARTS): return True
        return False

    # ==================================================
    # 🚀 MAIN FINDER
    # ==================================================
    def find_matches(self, user_query: str, threshold=0.55):
        if self.vectors is None or self.df.empty:
            return []

        q = user_query.strip()
        if not q: return []

        query_vec = self.vector_model.encode([q])
        scores = util.cos_sim(query_vec, self.vectors)[0]
        self.df["score"] = scores.cpu().numpy()
        
        candidates = self.df[self.df["score"] >= threshold].copy()
        if candidates.empty: return []

        candidates = candidates.sort_values(by="score", ascending=False).head(35)
        
        final_results = []
        for _, row in candidates.iterrows():
            name = row["Product Name"]
            
            # --- RUN CHECKS ---
            if self._is_trap(name, q): continue
            if not self._check_meat_mismatch(name, q): continue
            if self._is_low_quality_part(name, q): continue
            if not self._check_strict_numbers(name, q): continue
            
            final_results.append(row)

        if not final_results:
            return []

        df_final = pd.DataFrame(final_results)
        
        # ⚡ RAW INGREDIENT BOOST ⚡
        def boost_logic(row):
            s = row["score"]
            name_lower = str(row["Product Name"]).lower()
            q_lower = q.lower()
            
            # 1. Exact Start Boost
            if name_lower.startswith(q_lower):
                s += 0.2
            
            # 2. Short Name Bonus
            if len(name_lower) <= len(q_lower) + 15:
                s += 0.25 
                
            return s
            
        df_final["final_score"] = df_final.apply(boost_logic, axis=1)

        if "Unit Price" in df_final.columns:
            df_final = df_final.sort_values(by=["final_score", "Unit Price"], ascending=[False, True])
        else:
            df_final = df_final.sort_values(by="final_score", ascending=False)

        return df_final.to_dict(orient="records")