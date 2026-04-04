import os
import re
import sqlite3
import unicodedata
import json
from collections import Counter
from typing import Iterator, Dict, Any, List, Optional, Tuple
from datetime import datetime
from core.database import get_db_connection as get_db

# ==============================================================================
# CONFIGURATIE & GLOBAL CACHE
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Pad naar je lookup.db (vanuit core/parsers/ naar data/)
DB_PATH = os.path.join(BASE_DIR, "..", "..", "data", "lookup.db") 
PREF_JSON_PATH = os.path.join(BASE_DIR, "data", "ATC_preferent.json")

# ATC Remap Cache (Global load voor warm-start optimalisatie)
ATC_REMAP_EXACT = {}

def load_global_data():
    """Laad statische JSON config 1x in geheugen."""
    global ATC_REMAP_EXACT
    if not ATC_REMAP_EXACT and os.path.exists(PREF_JSON_PATH):
        try:
            with open(PREF_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    prefer = (item.get("ATC_preferent") or "").strip().upper()
                    mogelijk = item.get("ATC_mogelijk") or []
                    for m in mogelijk:
                        k = (m or "").strip().upper()
                        if k: ATC_REMAP_EXACT[k] = prefer
        except Exception as e:
            print(f"⚠️ Fout laden ATC_preferent.json: {e}")

load_global_data()

# ==============================================================================
# TEXT & REGEX TOOLS
# ==============================================================================
def clean_name(name: str) -> str:
    if not name: return ""
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("\u200b", "")
    return name.strip()

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
# CORE LOGICA (SQL VERVANGING)
# ==============================================================================

def find_nmnr_exact(clean_nm: str, cursor) -> Optional[str]:
    """Zoek NMNR via SQL Exact Match."""
    # COLLATE NOCASE zorgt dat hoofdletters niet uitmaken
    cursor.execute("SELECT nmnr FROM bst020_namen WHERE nmnaam = ? COLLATE NOCASE LIMIT 1", (clean_nm,))
    row = cursor.fetchone()
    return row['nmnr'] if row else None

def get_atc_for_spkode(spkode: str, cursor) -> str:
    """Haal ATC op uit BST711 en pas preferentie mapping toe."""
    if not spkode: return None
    
    # 1. Haal alle mogelijke ATCs op voor deze SPKode
    cursor.execute("SELECT atc FROM bst711_generiek WHERE spkode = ?", (spkode,))
    rows = cursor.fetchall()
    atcs = [r['atc'].strip().upper() for r in rows if r['atc']]
    
    if not atcs: return None
    
    # 2. Meest voorkomende
    most_common = Counter(atcs).most_common(1)[0][0]
    
    # 3. Remap via JSON cache
    return ATC_REMAP_EXACT.get(most_common, most_common)

def resolve_routes_sql(nmnr: str, cursor) -> Tuple[Any, Any, Any]:
    """Vervangt _attempt_resolve_sp. Probeert alle 4 routes via SQL."""
    if not nmnr: return None, None, None

    # Route 1: BST711 Direct
    cursor.execute("SELECT spkode FROM bst711_generiek WHERE (gpstnr = ? OR gpnmnr = ?) AND spkode IS NOT NULL LIMIT 1", (nmnr, nmnr))
    row = cursor.fetchone()
    if row: return nmnr, None, row['spkode']

    # Route 2: PR -> GP -> SP
    # Query met JOIN is veel sneller dan losse stappen in Python
    q2 = """
        SELECT t.spkode 
        FROM bst052_recept r
        JOIN bst711_generiek t ON (t.gpkode = r.gpkode OR t.gskode = r.gpkode)
        WHERE r.prnmnr = ? AND t.spkode IS NOT NULL
        LIMIT 1
    """
    cursor.execute(q2, (nmnr,))
    row = cursor.fetchone()
    if row: return nmnr, None, row['spkode']

    # Route 3: AT -> HP -> GP -> SP
    q3 = """
        SELECT a.hpkode, t.spkode
        FROM bst004_artikelen a
        JOIN bst070_handelsproducten hp ON hp.hpkode = a.hpkode
        JOIN bst711_generiek t ON (t.gpkode = hp.gpkode OR t.gskode = hp.gpkode)
        WHERE a.atnmnr = ? AND t.spkode IS NOT NULL
        LIMIT 1
    """
    cursor.execute(q3, (nmnr,))
    row = cursor.fetchone()
    if row: return nmnr, row['hpkode'], row['spkode']

    # Route 4: HPNAMN -> HP -> GP -> SP
    q4 = """
        SELECT v.hpkode, t.spkode
        FROM bst031_voorschrijfpr v
        JOIN bst070_handelsproducten hp ON hp.hpkode = v.hpkode
        JOIN bst711_generiek t ON (t.gpkode = hp.gpkode OR t.gskode = hp.gpkode)
        WHERE v.hpnamn = ? AND t.spkode IS NOT NULL
        LIMIT 1
    """
    cursor.execute(q4, (nmnr,))
    row = cursor.fetchone()
    if row: return nmnr, row['hpkode'], row['spkode']

    return None, None, None

def _healthbase_table_exists(cursor) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='healthbase_etiketnamen'"
    )
    return cursor.fetchone() is not None


def _lookup_healthbase_exact(naam: str, cursor) -> Optional[str]:
    """Exacte (case-insensitive) match op healthbase etiketnaam. Retourneert ATC code."""
    if not _healthbase_table_exists(cursor):
        return None
    cursor.execute(
        "SELECT atc FROM healthbase_etiketnamen WHERE LOWER(etiketnaam) = LOWER(?) LIMIT 1",
        (naam,),
    )
    row = cursor.fetchone()
    return row["atc"].strip().upper() if row and row["atc"] else None


def _lookup_healthbase_fuzzy(naam: str, cursor) -> Optional[str]:
    """Fuzzy match op healthbase etiketnaam. Retourneert ATC code."""
    if not _healthbase_table_exists(cursor):
        return None
    from difflib import SequenceMatcher
    prefix = naam.split()[0][:4] if naam.split() else ""
    if not prefix:
        return None
    cursor.execute(
        "SELECT etiketnaam, atc FROM healthbase_etiketnamen WHERE LOWER(etiketnaam) LIKE LOWER(?) LIMIT 200",
        (prefix + "%",),
    )
    rows = cursor.fetchall()
    if not rows:
        return None

    best_ratio = 0.0
    best_atc = None
    naam_lower = naam.lower()
    for r in rows:
        ratio = SequenceMatcher(None, naam_lower, r["etiketnaam"].lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_atc = r["atc"]
    if best_ratio >= 0.85 and best_atc:
        return best_atc.strip().upper()
    return None


def match_medicijn_sql(gm_clean: str, cursor) -> Tuple[Any, Any, Any, Optional[str]]:
    """
    Zoek medicijn in databases. Retourneert (nmnr, hpkode, spkode, atc_override).
    atc_override is gezet wanneer Healthbase direct een ATC oplevert (geen NMNR/SPKode pad).
    """
    full_clean = clean_name(gm_clean)
    if not full_clean: return None, None, None, None

    # 1. Exacte G-Standaard match
    nmnr = find_nmnr_exact(full_clean, cursor)
    if nmnr:
        res = resolve_routes_sql(nmnr, cursor)
        if res[2]: return res[0], res[1], res[2], None

    # 2. Exacte Healthbase etiketnaammatch
    hb_atc = _lookup_healthbase_exact(full_clean, cursor)
    if hb_atc:
        return None, None, None, hb_atc

    # 3. Prefix G-Standaard matching
    tokens = full_clean.split()
    n = len(tokens)

    for k in range(n - 1, 0, -1):
        candidate = " ".join(tokens[:k])

        nmnr_k = find_nmnr_exact(candidate, cursor)
        if nmnr_k:
            res = resolve_routes_sql(nmnr_k, cursor)
            if res[2]: return res[0], res[1], res[2], None

        query = """
            SELECT nmnr, nmnaam FROM bst020_namen
            WHERE nmnaam LIKE ?
            LIMIT 20
        """
        cursor.execute(query, (candidate + "%",))
        rows = cursor.fetchall()

        cand_norm = clean_name(candidate).lower()
        boundary_pat = re.compile(r'^' + re.escape(cand_norm) + r'(?:\b|[ \-/_]|$)')

        for r in rows:
            nm_clean = clean_name(r['nmnaam']).lower()
            if boundary_pat.match(nm_clean):
                res_pref = resolve_routes_sql(r['nmnr'], cursor)
                if res_pref[2]: return res_pref[0], res_pref[1], res_pref[2], None

    # 4. Fuzzy Healthbase
    hb_atc_fuzzy = _lookup_healthbase_fuzzy(full_clean, cursor)
    if hb_atc_fuzzy:
        return None, None, None, hb_atc_fuzzy

    return None, None, None, None

def get_atc_details(atc_code: str, cursor) -> Dict:
    """Haalt omschrijvingen en Jansen groepen op."""
    out = {
        "ATC": atc_code, 
        "ATC3": None, "ATC4": None, "ATC5": None, "ATC7": None,
        "ATC3_omschrijving": None, 
        
        # Nieuw: Jansen ID en Naam
        "ATC3_jansen_id": None,   
        "ATC3_jansen_naam": None,
        
        "ATC4_omschrijving": None, "ATC5_omschrijving": None, "ATC7_omschrijving": None
    }
    if not atc_code: return out

    out["ATC3"] = atc_code[:3] if len(atc_code) >= 3 else None
    out["ATC4"] = atc_code[:4] if len(atc_code) >= 4 else None
    out["ATC5"] = atc_code[:5] if len(atc_code) >= 5 else None
    out["ATC7"] = atc_code[:7] if len(atc_code) >= 7 else None

    # ATC3 Jansen Lookup (Met JOIN voor ID + Naam)
    if out["ATC3"]:
        # Let op de tabelnamen: 'atc_jansen_mapping' en 'jansen_groups'
        query = """
            SELECT m.atc_desc, m.group_id, g.name 
            FROM atc_jansen_mapping m
            LEFT JOIN jansen_groups g ON m.group_id = g.id
            WHERE m.atc = ?
        """
        cursor.execute(query, (out["ATC3"],))
        row = cursor.fetchone()
        
        if row:
            out["ATC3_omschrijving"] = row['atc_desc']
            out["ATC3_jansen_id"] = row['group_id']    # Integer ID
            out["ATC3_jansen_naam"] = row['name']      # String Naam

    # BST801 Teksten
    codes = [out["ATC4"], out["ATC5"], out["ATC7"]]
    codes = [c for c in codes if c]
    if codes:
        placeholders = ','.join(['?']*len(codes))
        cursor.execute(f"SELECT atcode, atoms FROM bst801_atc_teksten WHERE atcode IN ({placeholders})", codes)
        rows = cursor.fetchall()
        lookup = {r['atcode']: r['atoms'].strip() for r in rows}
        
        out["ATC4_omschrijving"] = lookup.get(out["ATC4"])
        out["ATC5_omschrijving"] = lookup.get(out["ATC5"])
        out["ATC7_omschrijving"] = lookup.get(out["ATC7"])
    
    return out

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