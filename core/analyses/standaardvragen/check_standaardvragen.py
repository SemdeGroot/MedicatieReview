import json
import os
from typing import List, Dict, Set, Any, Optional

# ==============================================================================
# 1. CONFIGURATIE & GLOBAL DATA
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "data", "vragen.json")

# Cache variabele
VRAGEN_CACHE = []

def load_vragen_data():
    """Laadt de standaardvragen 1x in het geheugen bij start container."""
    global VRAGEN_CACHE
    if not VRAGEN_CACHE and os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                VRAGEN_CACHE = data.get('criteria', [])
            # print(f"✅ Loaded {len(VRAGEN_CACHE)} standaardvragen.") 
        except Exception as e:
            print(f"❌ Error loading vragen.json: {e}")
            VRAGEN_CACHE = []

# Direct laden (Warm Start)
load_vragen_data()

# ==============================================================================
# 2. ANALYSE LOGICA
# ==============================================================================

def check_standaardvragen(medicatielijst: List[Dict[str, Any]], leeftijd: int = 75) -> List[Dict[str, Any]]:
    """
    Controleert standaardvragen op basis van ATC-codes.
    
    Ondersteunt:
    - Substances (ATC7 match)
    - Group Codes (ATC3/4/5 match)
    - Combinaties (X + Y + Z)
    - Exclusie combinaties (NOT Y: als Y aanwezig is, trigger dan niet)
    """
    
    # Fallback load
    if not VRAGEN_CACHE:
        load_vragen_data()
        if not VRAGEN_CACHE: return []

    # ---- Indexen opbouwen (O(1) lookup) ----
    meds_by_atc7: Dict[str, Set[str]] = {}
    meds_by_atc5: Dict[str, Set[str]] = {}
    meds_by_atc4: Dict[str, Set[str]] = {}
    meds_by_atc3: Dict[str, Set[str]] = {}

    def _add(dct: Dict, key: Optional[str], name: str):
        if not key: return
        k = str(key).strip().upper()
        dct.setdefault(k, set()).add(name)

    for gm in medicatielijst:
        name = (gm.get("clean") or "").strip() or "Onbekend middel"
        
        # ATC codes verzamelen
        atc_full = gm.get("ATC") or gm.get("ATC7")
        
        _add(meds_by_atc7, atc_full, name)
        _add(meds_by_atc5, gm.get("ATC5"), name)
        _add(meds_by_atc4, gm.get("ATC4"), name)
        _add(meds_by_atc3, gm.get("ATC3"), name)

    # ---- Helper functies ----
    
    def meds_for_substance_token(tok: str) -> Set[str]:
        return meds_by_atc7.get(str(tok).strip().upper(), set())

    def meds_for_group_token(tok: str) -> Set[str]:
        t = str(tok).strip().upper()
        if t in meds_by_atc5: return meds_by_atc5[t]
        if t in meds_by_atc4: return meds_by_atc4[t]
        if t in meds_by_atc3: return meds_by_atc3[t]
        return set()

    def meds_for_any_token(tok: str) -> Set[str]:
        return meds_for_substance_token(tok) | meds_for_group_token(tok)

    triggered_vragen = []

    # ---- Criteria Loop ----
    for vraag in VRAGEN_CACHE:
        
        # Lege regels overslaan
        if not vraag.get("description"):
            continue

        # Leeftijdscheck
        if vraag.get("requires_age", False):
            age_min = int(vraag.get("age_min", 0))
            if leeftijd < age_min:
                continue

        matched_meds = set()

        # A) Substances
        for sub in vraag.get("substances", []):
            matched_meds |= meds_for_substance_token(sub)

        # B) Groups
        for gr in vraag.get("group_codes", []):
            matched_meds |= meds_for_group_token(gr)

        # C) Combinaties & Exclusies
        cx = vraag.get("combination_x", [])
        cy = vraag.get("combination_y", [])
        cz = vraag.get("combination_z", [])
        not_y = vraag.get("combination_NOT_y", []) # NIEUW: Exclusie lijst

        def hits(token_list):
            return any(meds_for_any_token(t) for t in token_list)

        # Logica voor NOT Y: Als er een match is in NOT_Y, dan skippen we deze vraag
        if not_y and hits(not_y):
            continue

        # Normale combinatie logica
        if cx or cy:
            match_x = hits(cx) if cx else True
            match_y = hits(cy) if cy else True
            match_z = hits(cz) if cz else True
            
            is_combi_match = False
            if cx and cy and cz:
                is_combi_match = match_x and match_y and match_z
            elif cx and cy:
                is_combi_match = match_x and match_y
            
            if is_combi_match:
                for part in (cx + cy + cz):
                    matched_meds |= meds_for_any_token(part)

        # ---- Resultaat opslaan ----
        if matched_meds:
            meds_list = sorted(list(matched_meds), key=str.lower)
            trigger_txt = ", ".join(meds_list)
            
            triggered_vragen.append({
                "id": vraag.get("id", ""),
                "categorie": vraag.get("type", ""),
                "subcategorie": vraag.get("subtype", ""),
                "vraag": vraag.get("description", ""),
                "toelichting": vraag.get("argument", ""),
                "betrokken_middelen": trigger_txt
            })

    return triggered_vragen