import json
import os
from typing import List, Dict, Set, Any, Optional

# ==============================================================================
# 1. CONFIGURATIE & GLOBAL DATA
# ==============================================================================
# We bepalen het pad relatief aan dit bestand, zodat het altijd werkt
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "data", "start_stop.json")

# Cache variabele
STOPP_CRITERIA_CACHE = []

def load_stopp_data():
    """Laadt de criteria 1x in het geheugen bij start van de container."""
    global STOPP_CRITERIA_CACHE
    if not STOPP_CRITERIA_CACHE and os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                STOPP_CRITERIA_CACHE = data.get('criteria', [])
            # print(f"✅ Loaded {len(STOPP_CRITERIA_CACHE)} STOPP criteria.") 
        except Exception as e:
            print(f"❌ Error loading START_STOPP.json: {e}")
            STOPP_CRITERIA_CACHE = []

# Direct laden bij import (Warm Start optimalisatie)
load_stopp_data()

# ==============================================================================
# 2. ANALYSE LOGICA
# ==============================================================================

def check_stopp_criteria(medicatielijst: List[Dict[str, Any]], leeftijd: int = 75) -> List[Dict[str, Any]]:
    """
    Controleert STOPP-criteria op basis van ATC-codes.
    Gebruikt de in-memory cache voor snelheid.
    
    Args:
        medicatielijst: Lijst met geneesmiddelen (output van parser).
                        Moet velden bevatten: 'clean', 'ATC', 'ATC3', 'ATC4', 'ATC5'.
        leeftijd: Leeftijd van de patiënt (default 75).

    Returns:
        Lijst met getriggerde waarschuwingen.
    """
    
    # Als de cache leeg is (bv bestand niet gevonden), probeer nog 1x te laden
    if not STOPP_CRITERIA_CACHE:
        load_stopp_data()
        if not STOPP_CRITERIA_CACHE:
            return [] # Geen criteria = geen waarschuwingen

    # ---- Indexen opbouwen (Snelheid: O(1) lookup per code) ----
    # We maken sets van alle codes die de patiënt gebruikt
    meds_by_atc7: Dict[str, Set[str]] = {}
    meds_by_atc5: Dict[str, Set[str]] = {}
    meds_by_atc4: Dict[str, Set[str]] = {}
    meds_by_atc3: Dict[str, Set[str]] = {}

    def _add(dct: Dict, key: Optional[str], name: str):
        if not key: return
        k = str(key).strip().upper()
        dct.setdefault(k, set()).add(name)

    for gm in medicatielijst:
        # Naam van medicijn (fallback naar 'Onbekend')
        name = (gm.get("clean") or "").strip() or "Onbekend middel"
        
        # Voeg toe aan indexen (gebruik de keys zoals je parser ze oplevert)
        # Parser levert: ATC (de volledige), ATC3, ATC4, ATC5, ATC7
        
        # ATC7 is vaak gelijk aan 'ATC' (de volledige code)
        atc_full = gm.get("ATC") or gm.get("ATC7")
        
        _add(meds_by_atc7, atc_full, name)
        _add(meds_by_atc5, gm.get("ATC5"), name)
        _add(meds_by_atc4, gm.get("ATC4"), name)
        _add(meds_by_atc3, gm.get("ATC3"), name)

    # ---- Helper functies voor matching ----
    
    def meds_for_substance_token(tok: str) -> Set[str]:
        """Match op volledige code (ATC7)."""
        return meds_by_atc7.get(str(tok).strip().upper(), set())

    def meds_for_group_token(tok: str) -> Set[str]:
        """Match op groep (ATC5, anders ATC4, anders ATC3)."""
        t = str(tok).strip().upper()
        # Probeer strengste match eerst
        if t in meds_by_atc5: return meds_by_atc5[t]
        if t in meds_by_atc4: return meds_by_atc4[t]
        if t in meds_by_atc3: return meds_by_atc3[t]
        return set()

    def meds_for_any_token(tok: str) -> Set[str]:
        """Match zowel als stof of als groep (voor combinaties)."""
        return meds_for_substance_token(tok) | meds_for_group_token(tok)

    triggered_criteria = []

    # ---- Criteria Loop ----
    for criterion in STOPP_CRITERIA_CACHE:
        
        # 1. Filter: Type check
        if criterion.get("type") != "STOP":
            continue
        
        # 2. Filter: Leeftijdscheck
        if criterion.get("requires_age", False):
            # Veilig casten naar int, default 0
            age_min = int(criterion.get("age_min", 0))
            if leeftijd < age_min:
                continue

        matched_meds = set()

        # 3. Check: Substances (ATC7)
        for sub in criterion.get("substances", []):
            matched_meds |= meds_for_substance_token(sub)

        # 4. Check: Group Codes (ATC3/4/5)
        for gr in criterion.get("group_codes", []):
            matched_meds |= meds_for_group_token(gr)

        # 5. Check: Combinaties
        # Haal lijsten op (defaults naar lege lijst)
        cx = criterion.get("combination_x", [])
        cy = criterion.get("combination_y", [])
        cz = criterion.get("combination_z", [])

        # Optimalisatie: check alleen als er combi-lijsten zijn
        if cx or cy:
            # Helper om te kijken of een lijst 'geraakt' wordt
            def hits(token_list):
                return any(meds_for_any_token(t) for t in token_list)

            match_x = hits(cx) if cx else True # True als leeg (geen eis)
            match_y = hits(cy) if cy else True
            match_z = hits(cz) if cz else True
            
            is_combi_match = False

            # Logica: X en Y (en Z indien aanwezig) moeten beide aanwezig zijn
            if cx and cy and cz:
                is_combi_match = match_x and match_y and match_z
            elif cx and cy:
                is_combi_match = match_x and match_y
            
            if is_combi_match:
                # Verzamel de namen van de triggers uit alle delen
                for part in (cx + cy + cz):
                    matched_meds |= meds_for_any_token(part)

        # ---- Resultaat opslaan ----
        if matched_meds:
            # Sorteer voor nette output
            meds_list = sorted(list(matched_meds), key=str.lower)
            
            # Tekst opmaak
            trigger_txt = ", ".join(meds_list)
            # Als het een combinatie was (en er dus meerdere middelen zijn), zet 'Combinatie:' ervoor
            if (cx and cy) and len(meds_list) > 1:
                 trigger_txt = f"Combinatie: {trigger_txt}"

            triggered_criteria.append({
                "id": criterion.get("id", ""),
                "category": criterion.get("category", ""),
                "description": criterion.get("description", ""),
                "argument": criterion.get("argument", ""),
                "triggering_medicines": trigger_txt
            })

    return triggered_criteria