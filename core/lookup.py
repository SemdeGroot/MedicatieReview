# core/lookup.py
# Centrale lookup module voor medicatie matching via G-Standaard en Healthbase.
# Gebaseerd op de verbeterde lookup uit ApotheekPortaal, met MedicatieReview-specifieke
# features (Jansen groepen, ATC preferent remap).

import difflib
import json
import os
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, Optional, Tuple

from core.database import get_db_connection as get_db

# ==============================================================================
# CONFIGURATIE & GLOBAL CACHE
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREF_JSON_PATH = os.path.join(BASE_DIR, "parsers", "data", "ATC_preferent.json")

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
                        if k:
                            ATC_REMAP_EXACT[k] = prefer
        except Exception as e:
            print(f"Fout laden ATC_preferent.json: {e}")


load_global_data()


# ==============================================================================
# TEXT TOOLS
# ==============================================================================

def clean_name(name: str) -> str:
    if not name:
        return ""
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("\u200b", "")
    return name.strip()


# ==============================================================================
# FUZZY MATCHING HELPERS (uit ApotheekPortaal)
# ==============================================================================

_DOSAGE_RE = re.compile(r"^\d|^mg|^ml|^mcg|^ug|^do$|^g$", re.IGNORECASE)


def _extract_stof_prefixes(naam: str) -> list[str]:
    """Extract substance prefixes from a (possibly abbreviated) drug name.

    Splits on '/' to get components, takes the first word of each,
    and filters out dosage-like tokens (starting with digits, units, or < 3 chars).
    """
    parts = naam.split("/")
    prefixes = []
    for part in parts:
        word = part.strip().split()[0] if part.strip() else ""
        if word and len(word) >= 3 and not _DOSAGE_RE.match(word):
            prefixes.append(word.lower())
    return prefixes


def _candidate_matches_prefix(nmnaam: str, prefix: str) -> bool:
    """Check if any word in a G-Standaard name starts with the given prefix."""
    words = re.split(r"[\s/\-()]+", nmnaam.lower())
    return any(w.startswith(prefix) for w in words)


def _best_fuzzy_match(query_lower: str, candidates, text_fn, threshold: float = 0.45):
    """Return the candidate with the highest difflib ratio, or None if below threshold."""
    best_score = 0.0
    best_row = None
    for row in candidates:
        score = difflib.SequenceMatcher(None, query_lower, text_fn(row).lower()).ratio()
        if score > best_score:
            best_score = score
            best_row = row
    return best_row if best_score >= threshold else None


# ==============================================================================
# HEALTHBASE HELPERS
# ==============================================================================

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
    prefix = naam.split()[0][:4] if naam.split() else ""
    if not prefix:
        return None
    cursor.execute(
        "SELECT etiketnaam, atc FROM healthbase_etiketnamen WHERE LOWER(etiketnaam) LIKE LOWER(?) LIMIT 200",
        (prefix + "%",),
    )
    candidates = cursor.fetchall()
    match = _best_fuzzy_match(naam.lower(), candidates, lambda r: r["etiketnaam"], threshold=0.85)
    if match:
        atc_code = (match["atc"] or "").strip().upper()
        if atc_code:
            return atc_code
    return None


# ==============================================================================
# CORE LOOKUP LOGICA
# ==============================================================================

def find_nmnr_exact(clean_nm: str, cursor) -> Optional[str]:
    """Zoek NMNR via exact match (case-insensitive)."""
    cursor.execute(
        "SELECT nmnr FROM bst020_namen WHERE nmnaam = ? COLLATE NOCASE LIMIT 1",
        (clean_nm,),
    )
    row = cursor.fetchone()
    return row['nmnr'] if row else None


def get_atc_for_spkode(spkode: str, cursor) -> Optional[str]:
    """Haal ATC op uit BST711 en pas preferentie mapping toe."""
    if not spkode:
        return None

    cursor.execute("SELECT atc FROM bst711_generiek WHERE spkode = ?", (spkode,))
    rows = cursor.fetchall()
    atcs = [r['atc'].strip().upper() for r in rows if r['atc']]

    if not atcs:
        return None

    most_common = Counter(atcs).most_common(1)[0][0]
    return ATC_REMAP_EXACT.get(most_common, most_common)


def resolve_routes_sql(nmnr: str, cursor) -> Tuple[Any, Any, Any]:
    """Probeert alle 4 routes via SQL om van NMNR naar SPKode te komen."""
    if not nmnr:
        return None, None, None

    # Route 1: BST711 Direct
    cursor.execute(
        "SELECT spkode FROM bst711_generiek WHERE (gpstnr = ? OR gpnmnr = ?) AND spkode IS NOT NULL LIMIT 1",
        (nmnr, nmnr),
    )
    row = cursor.fetchone()
    if row:
        return nmnr, None, row['spkode']

    # Route 2: PR -> GP -> SP
    cursor.execute(
        """SELECT t.spkode
           FROM bst052_recept r
           JOIN bst711_generiek t ON (t.gpkode = r.gpkode OR t.gskode = r.gpkode)
           WHERE r.prnmnr = ? AND t.spkode IS NOT NULL
           LIMIT 1""",
        (nmnr,),
    )
    row = cursor.fetchone()
    if row:
        return nmnr, None, row['spkode']

    # Route 3: AT -> HP -> GP -> SP
    cursor.execute(
        """SELECT a.hpkode, t.spkode
           FROM bst004_artikelen a
           JOIN bst070_handelsproducten hp ON hp.hpkode = a.hpkode
           JOIN bst711_generiek t ON (t.gpkode = hp.gpkode OR t.gskode = hp.gpkode)
           WHERE a.atnmnr = ? AND t.spkode IS NOT NULL
           LIMIT 1""",
        (nmnr,),
    )
    row = cursor.fetchone()
    if row:
        return nmnr, row['hpkode'], row['spkode']

    # Route 4: HPNAMN -> HP -> GP -> SP
    cursor.execute(
        """SELECT v.hpkode, t.spkode
           FROM bst031_voorschrijfpr v
           JOIN bst070_handelsproducten hp ON hp.hpkode = v.hpkode
           JOIN bst711_generiek t ON (t.gpkode = hp.gpkode OR t.gskode = hp.gpkode)
           WHERE v.hpnamn = ? AND t.spkode IS NOT NULL
           LIMIT 1""",
        (nmnr,),
    )
    row = cursor.fetchone()
    if row:
        return nmnr, row['hpkode'], row['spkode']

    return None, None, None


def match_medicijn_sql(gm_clean: str, cursor) -> Tuple[Any, Any, Any, Optional[str]]:
    """
    Zoek medicijn in databases. Retourneert (nmnr, hpkode, spkode, atc_override).
    atc_override is gezet wanneer Healthbase direct een ATC oplevert.

    Verbeterde matching (uit ApotheekPortaal):
    1. Exacte G-Standaard match
    2. Exacte Healthbase match
    3. Slash-aware prefix matching met candidate filtering
    4. Fuzzy G-Standaard matching met difflib
    5. Fuzzy Healthbase matching
    """
    full_clean = clean_name(gm_clean)
    if not full_clean:
        return None, None, None, None

    # 1. Exacte G-Standaard match
    nmnr = find_nmnr_exact(full_clean, cursor)
    if nmnr:
        res = resolve_routes_sql(nmnr, cursor)
        if res[2]:
            return res[0], res[1], res[2], None

    # 2. Exacte Healthbase match
    hb_atc = _lookup_healthbase_exact(full_clean, cursor)
    if hb_atc:
        return None, None, None, hb_atc

    # 3. Slash-aware prefix matching (verbeterd uit ApotheekPortaal)
    stof_prefixes = _extract_stof_prefixes(full_clean)
    first_token = stof_prefixes[0] if stof_prefixes else full_clean.split()[0]
    second_prefix = stof_prefixes[1] if len(stof_prefixes) >= 2 else None

    cursor.execute(
        "SELECT nmnr, nmnaam FROM bst020_namen WHERE LOWER(nmnaam) LIKE LOWER(?) LIMIT 50",
        (first_token + "%",),
    )
    candidates = cursor.fetchall()

    # Bij combinatiepreparaten (bijv. "Macro/zout"): filter op tweede stof-prefix
    if second_prefix:
        filtered = [r for r in candidates if _candidate_matches_prefix(r["nmnaam"], second_prefix)]
        if filtered:
            candidates = filtered

    for row in candidates:
        res = resolve_routes_sql(row['nmnr'], cursor)
        if res[2]:
            return res[0], res[1], res[2], None

    # 4. Fuzzy G-Standaard matching met difflib (nieuw uit ApotheekPortaal)
    prefix = full_clean.split()[0][:4]
    cursor.execute(
        "SELECT nmnr, nmnaam FROM bst020_namen WHERE LOWER(nmnaam) LIKE LOWER(?) LIMIT 200",
        (prefix + "%",),
    )
    candidates = cursor.fetchall()
    match = _best_fuzzy_match(
        full_clean.lower(), candidates, lambda r: r["nmnaam"], threshold=0.85
    )
    if match:
        res = resolve_routes_sql(match['nmnr'], cursor)
        if res[2]:
            return res[0], res[1], res[2], None

    # 5. Fuzzy Healthbase matching
    hb_atc_fuzzy = _lookup_healthbase_fuzzy(full_clean, cursor)
    if hb_atc_fuzzy:
        return None, None, None, hb_atc_fuzzy

    return None, None, None, None


def get_atc_details(atc_code: str, cursor) -> Dict:
    """Haalt ATC omschrijvingen en Jansen groepen op."""
    out = {
        "ATC": atc_code,
        "ATC3": None, "ATC4": None, "ATC5": None, "ATC7": None,
        "ATC3_omschrijving": None,
        "ATC3_jansen_id": None,
        "ATC3_jansen_naam": None,
        "ATC4_omschrijving": None, "ATC5_omschrijving": None, "ATC7_omschrijving": None,
    }
    if not atc_code:
        return out

    out["ATC3"] = atc_code[:3] if len(atc_code) >= 3 else None
    out["ATC4"] = atc_code[:4] if len(atc_code) >= 4 else None
    out["ATC5"] = atc_code[:5] if len(atc_code) >= 5 else None
    out["ATC7"] = atc_code[:7] if len(atc_code) >= 7 else None

    # ATC3 Jansen Lookup
    if out["ATC3"]:
        cursor.execute(
            """SELECT m.atc_desc, m.group_id, g.name
               FROM atc_jansen_mapping m
               LEFT JOIN jansen_groups g ON m.group_id = g.id
               WHERE m.atc = ?""",
            (out["ATC3"],),
        )
        row = cursor.fetchone()
        if row:
            out["ATC3_omschrijving"] = row['atc_desc']
            out["ATC3_jansen_id"] = row['group_id']
            out["ATC3_jansen_naam"] = row['name']

    # BST801 ATC Teksten
    codes = [c for c in [out["ATC4"], out["ATC5"], out["ATC7"]] if c]
    if codes:
        placeholders = ','.join(['?'] * len(codes))
        cursor.execute(
            f"SELECT atcode, atoms FROM bst801_atc_teksten WHERE atcode IN ({placeholders})",
            codes,
        )
        rows = cursor.fetchall()
        lookup = {r['atcode']: r['atoms'].strip() for r in rows}
        out["ATC4_omschrijving"] = lookup.get(out["ATC4"])
        out["ATC5_omschrijving"] = lookup.get(out["ATC5"])
        out["ATC7_omschrijving"] = lookup.get(out["ATC7"])

    return out
