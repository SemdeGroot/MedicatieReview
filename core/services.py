import json
from typing import Iterator, Dict, Any, Callable

# --- Parsers importeren ---
# Zorg dat de bestandsnaam klopt met wat je hebt (medimo_parser.py of parse_medimo_afdeling.py)
from core.parsers.parse_medimo_afdeling import process_medimo_text_stream

# --- Analyses importeren ---
from core.analyses.start_stop.check_start_stop import check_stopp_criteria
from core.analyses.anticholinerge_score.check_acb import bereken_acb_score
from core.analyses.dubbelmedicatie.check_dubbelmedicatie import check_dubbelmedicatie
from core.analyses.standaardvragen.check_standaardvragen import check_standaardvragen

# ==============================================================================
# PARSER REGISTRY (De "Verkeersregelaar")
# ==============================================================================
# Hier koppel je (bron, scope) aan een specifieke parser functie.
# Als je later 'pharmacom' toevoegt, hoef je alleen deze dict en de import aan te passen.

PARSER_MAPPING: Dict[tuple, Callable] = {
    ("medimo", "afdeling"): process_medimo_text_stream,
    ("medimo", "patient"): process_medimo_text_stream, # Voor nu dezelfde, later misschien anders?
    # ("pharmacom", "patient"): process_pharmacom_stream,  <-- Toekomstmuziek
}

def get_parser(source: str, scope: str) -> Callable:
    return PARSER_MAPPING.get((source, scope))

# ==============================================================================
# MAIN SERVICE
# ==============================================================================

def run_review_service(text: str, source: str, scope: str) -> Iterator[Dict[str, Any]]:
    """
    Orchestreert het hele proces:
    1. Kiest de juiste Parser
    2. Streamt parsing progress
    3. Voert Analyses uit (STOPP, ACB, Dubbel, Vragen)
    4. Geeft resultaat
    """
    
    # 1. Kies de juiste parser
    parser_func = get_parser(source, scope)
    
    if not parser_func:
        yield {"type": "error", "msg": f"Combinatie bron='{source}' en scope='{scope}' wordt nog niet ondersteund."}
        return

    # 2. Start de stream (Generator)
    parser_stream = parser_func(text)

    for item in parser_stream:
        # A. Progress/Status updates direct doorsturen naar frontend
        if item["type"] in ["status", "progress", "meta", "error"]:
            yield item
        
        # B. Resultaat van parser binnen? Start analyses!
        elif item["type"] == "result":
            raw_patients = item["data"] 
            afdeling = item.get("afdeling", "Onbekend")
            
            analyzed_patients = []
            
            yield {"type": "status", "msg": "Analyses uitvoeren..."}
            
            # Loop over patiënten (dit gaat in geheugen razendsnel)
            for patient in raw_patients:
                meds = patient.get("geneesmiddelen", [])
                
                # Leeftijd uit parser (kan None zijn)
                leeftijd = patient.get("leeftijd")
                
                # --- Analyses draaien ---
                stopp_res = check_stopp_criteria(meds, leeftijd)
                acb_score, acb_interp, acb_bijdrage = bereken_acb_score(meds)
                dubbel_res = check_dubbelmedicatie(meds)
                vragen_res = check_standaardvragen(meds, leeftijd)

                # Samenvoegen
                analyzed_patients.append({
                    "naam": patient["naam"],
                    "leeftijd": leeftijd, # Handig voor frontend om te tonen
                    "geneesmiddelen": meds,
                    "analyses": {
                        "stopp": stopp_res,
                        "acb": {
                            "score": acb_score,
                            "interpretatie": acb_interp,
                            "details": acb_bijdrage
                        },
                        "dubbelmedicatie": dubbel_res,
                        "standaardvragen": vragen_res
                    }
                })

            # --- EINDRESULTAAT ---
            yield {
                "type": "result", 
                "afdeling": afdeling,
                "data": analyzed_patients
            }