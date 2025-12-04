# core/services.py
import json
from typing import Iterator, Dict, Any

# Imports van jouw modules
from core.parsers.medimo_parser import process_medimo_text_stream
from core.analyses.start_stop.check_start_stop import check_stopp_criteria
from core.analyses.anticholinerge_score.check_acb import bereken_acb_score
from core.analyses.dubbelmedicatie.check_dubbelmedicatie import check_dubbelmedicatie
from core.analyses.standaardvragen.check_standaardvragen import check_standaardvragen

def run_review_service(text: str, source: str, scope: str) -> Iterator[Dict[str, Any]]:
    """
    Orchestreert het hele proces:
    1. Parsing (streamed progress)
    2. Analyses (STOPP, ACB, Dubbel, Vragen)
    3. Final Result
    """
    
    # 1. Validatie (voor nu simpel)
    if source != "medimo":
        yield {"type": "error", "msg": f"Bron '{source}' nog niet ondersteund."}
        return

    # We gebruiken de stream generator van de parser
    # Dit zorgt dat de frontend al procentjes ziet lopen terwijl Python bezig is
    parser_stream = process_medimo_text_stream(text)

    for item in parser_stream:
        # A. Progress updates direct doorsturen
        if item["type"] in ["status", "progress", "meta"]:
            yield item
        
        # B. Resultaat binnen? Nu gaan we analyseren!
        elif item["type"] == "result":
            raw_patients = item["data"] # Lijst met patiënten en hun 'clean' medicatie
            afdeling = item.get("afdeling", "Onbekend")
            
            analyzed_patients = []
            
            # --- START ANALYSES ---
            yield {"type": "status", "msg": "Analyses uitvoeren (STOPP, ACB, etc.)..."}
            
            total_pat = len(raw_patients)
            for i, patient in enumerate(raw_patients):
                # Voortgang van analyse fase (optioneel, gaat vaak heel snel)
                # yield {"type": "progress", "pct": 90 + int((i/total_pat)*10), "msg": "Analyseren..."}

                meds = patient.get("geneesmiddelen", [])
                
                # Leeftijd uit gb datum gehaald
                leeftijd = patient.get("leeftijd")
                # 1. STOPP
                stopp_res = check_stopp_criteria(meds, leeftijd)
                
                # 2. ACB
                acb_score, acb_interp, acb_bijdrage = bereken_acb_score(meds)
                
                # 3. Dubbelmedicatie
                dubbel_res = check_dubbelmedicatie(meds)
                
                # 4. Standaard Vragen
                vragen_res = check_standaardvragen(meds, leeftijd)

                # Alles samenvoegen
                analyzed_patients.append({
                    "naam": patient["naam"],
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