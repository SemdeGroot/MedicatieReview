import os
import re
from typing import Iterator, Dict, Any, List, Optional, Tuple
from datetime import datetime
from core.database import get_db_connection as get_db
from core.lookup import (
    clean_name,
    match_medicijn_sql,
    get_atc_for_spkode,
    get_atc_details,
)

# ==============================================================================
# TEXT & REGEX TOOLS
# ==============================================================================

def extract_patient_blocks(content: str) -> List[str]:
    start = re.search(r"(Dhr\. |Mevr\. )", content)
    if not start: return []
    content = content[start.start():]
    raw_blocks = re.split(r'(?=Dhr\. |Mevr\. )', content)
    return [b.strip() for b in raw_blocks if b.strip().startswith(("Dhr.", "Mevr."))]

def parse_medimo_block(block: str) -> List[Dict]:
    lines = block.strip().split("\n")
    geneesmiddelen = []
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(("C", "Z", "T")):
            regel = re.sub(r"^[CZT]\s+", "", line)
            delen = re.split(r'\s{2,}|\t+', regel)
            if len(delen) < 2:
                i += 1; continue
            
            opmerking = ""
            if i + 1 < len(lines):
                volgende = lines[i + 1].strip()
                if volgende and not volgende.startswith(("C", "Z", "T", "Dhr.", "Mevr.")):
                    opmerking = volgende
                    i += 1
            
            geneesmiddelen.append({
                "clean": delen[0].strip(),
                "gebruik": delen[1].strip(),
                "opmerking": opmerking
            })
        i += 1
    return geneesmiddelen

def extract_patient_details(header_line: str) -> Tuple[str, Optional[str], Optional[int]]:
    """
    Haalt naam, geboortedatum (string) en leeftijd (int) uit de header.
    Format: "Mevr. X (01-01-1950)"
    Returns: (Naam, "1950-01-01", 74)
    """
    match = re.search(r"\((\d{1,2}-\d{1,2}-\d{4})\)", header_line)
    
    naam = header_line
    dob_iso = None
    leeftijd = None
    
    if match:
        datum_str = match.group(1)
        naam = header_line.replace(f"({datum_str})", "").strip()
        try:
            dob = datetime.strptime(datum_str, "%d-%m-%Y").date()
            dob_iso = dob.isoformat()
            
            # Bereken leeftijd voor analyses
            today = datetime.today().date()
            leeftijd = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        except ValueError:
            pass

    return naam, dob_iso, leeftijd


# ==============================================================================
# MAIN ENTRYPOINT (GENERATOR)
# ==============================================================================

def process_medimo_text_stream(text: str) -> Iterator[Dict[str, Any]]:
    """
    Generator functie die updates YIELDT.
    Dit maakt streaming progress mogelijk in FastAPI.
    """
    
    # 1. Initialisatie
    yield {"type": "status", "msg": "Database verbinden...", "pct": 0}
    conn = get_db()
    cursor = conn.cursor()

    # 2. Extractie
    afdeling = "Onbekend"
    m = re.search(r"Een overzicht van alle actieve medicatie in afdeling (.+?)\.", text)
    if m: afdeling = m.group(1).strip()
    
    blocks = extract_patient_blocks(text)
    total_blocks = len(blocks)
    yield {"type": "meta", "afdeling": afdeling, "total_patients": total_blocks}

    results = []

    # 3. Processing
    for idx, block in enumerate(blocks):
        # Pak de eerste regel (de header)
        header_line = block.split("\n")[0].strip()
        
        # NIEUW: Gebruik de helper om naam én leeftijd te splitsen
        patient_name, dob_iso, age = extract_patient_details(header_line)
        
        gm_list = parse_medimo_block(block)
        
        # Voortgang sturen
        pct = int(((idx) / total_blocks) * 100)
        yield {
            "type": "progress", 
            "pct": pct, 
            "current_patient": patient_name,
            "processed": idx,
            "total": total_blocks
        }

        # Medicijnen verwerken
        clean_meds = []
        for gm in gm_list:
            nmnr, hpkode, spkode, atc_override = match_medicijn_sql(gm["clean"], cursor)
            atc_code = atc_override or get_atc_for_spkode(spkode, cursor)
            details = get_atc_details(atc_code, cursor)

            med_entry = {**gm, **details}
            med_entry["NMNR"] = nmnr
            med_entry["HPKode"] = hpkode
            med_entry["SPKode"] = spkode
            clean_meds.append(med_entry)

        # <--- CORRECTIE: Dit blok moet BINNEN de for-loop vallen!
        results.append({
            "naam": patient_name,
            "geboortedatum": dob_iso, # Voor weergave / DB
            "leeftijd": age,          # Voor analyse logica (STOPP etc.)
            "geneesmiddelen": clean_meds
        })

    conn.close()
    
    # 4. Final Result
    yield {"type": "progress", "pct": 100, "msg": "Afronden..."}
    yield {"type": "result", "data": results, "afdeling": afdeling}