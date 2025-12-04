import json
import os
from typing import List, Dict, Tuple, Any, Optional

# ==============================================================================
# 1. CONFIGURATIE & GLOBAL DATA
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "data", "acb.json")

# Lookup map: ATC-code -> Score (int)
# Dit maakt het opzoeken O(1) i.p.v. loopen door lijsten
ACB_LOOKUP_CACHE: Dict[str, int] = {}

def load_acb_data():
    """
    Laadt de ACB JSON en transformeert deze naar een snelle lookup map.
    Draait 1x bij start container (Warm Start).
    """
    global ACB_LOOKUP_CACHE
    if not ACB_LOOKUP_CACHE and os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            
            scores_map = raw_data.get("scores") or {}
            
            # Transformatie: Van { "3": ["A", "B"] } naar { "A": 3, "B": 3 }
            for score_str, codes in scores_map.items():
                try:
                    score_val = int(score_str)
                    for code in codes:
                        c = (code or "").strip().upper()
                        if len(c) == 7: # ACB werkt op stofniveau (ATC7)
                            ACB_LOOKUP_CACHE[c] = score_val
                except ValueError:
                    continue
                    
            # print(f"✅ Loaded {len(ACB_LOOKUP_CACHE)} ACB mappings.")
        except Exception as e:
            print(f"❌ Error loading acb.json: {e}")
            ACB_LOOKUP_CACHE = {}

# Direct laden bij import
load_acb_data()

# ==============================================================================
# 2. ANALYSE LOGICA
# ==============================================================================

# Type definitie voor resultaat
ACBResult = Tuple[int, str, List[Dict[str, Any]]]

def bereken_acb_score(medicatielijst: List[Dict[str, Any]]) -> ACBResult:
    """
    Berekent de ACB-score op basis van ATC-codes uit de parser.
    
    Args:
        medicatielijst: Lijst met geneesmiddelen (dicts met 'clean' en 'ATC').

    Returns:
        (totaalscore, interpretatie, bijdragen_lijst)
    """
    
    # Fallback als cache leeg is
    if not ACB_LOOKUP_CACHE:
        load_acb_data()

    totaal_score = 0
    bijdragen: List[Dict[str, Any]] = []
    
    # Set om dubbele tellingen van DEZELFDE stof te voorkomen
    # (Bijv: 2x Amitriptyline op de lijst mag maar 1x tellen voor de score)
    gezien_atc: set[str] = set()

    for gm in medicatielijst:
        # Haal ATC code op (voorkeur voor ATC7, anders ATC volledig)
        # De nieuwe parser levert "ATC" (volledig) en "ATC7" (de eerste 7 chars)
        atc_code = (gm.get("ATC7") or gm.get("ATC") or "").strip().upper()
        
        # Zorg dat we alleen echte ATC7 codes checken (7 karakters)
        if len(atc_code) < 7:
            atc_code = atc_code[:7] if len(atc_code) >= 7 else ""
        
        if not atc_code or len(atc_code) != 7:
            continue

        # Niet dubbel tellen
        if atc_code in gezien_atc:
            continue

        # O(1) Lookup in de map
        score = ACB_LOOKUP_CACHE.get(atc_code, 0)
        
        if score > 0:
            totaal_score += score
            gezien_atc.add(atc_code)
            
            # Naam bepalen voor rapportage
            naam = (gm.get("clean") or "").strip() or atc_code

            bijdragen.append({
                "middel": naam,
                "atc7": atc_code,
                "score": score
            })

    # Interpretatie
    interpretatie = ""
    if totaal_score == 0:
        interpretatie = "Geen anticholinerge belasting (score = 0)."
    elif totaal_score == 1:
        interpretatie = "Lichte anticholinerge belasting (score = 1)."
    elif totaal_score == 2:
        interpretatie = "Matige anticholinerge belasting (score = 2)."
    else:
        interpretatie = "Hoge anticholinerge belasting (score ≥ 3)."

    return totaal_score, interpretatie, bijdragen