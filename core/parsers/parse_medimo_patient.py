# core/parsers/parse_medimo_patient.py

import os
import re
from typing import Iterator, Dict, Any, List, Optional, Tuple

from core.database import get_db_connection as get_db

# Hergebruik exact dezelfde matching/ATC logica als je afdeling-parser
from core.parsers.parse_medimo_afdeling import extract_patient_details
from core.lookup import (
    clean_name,
    match_medicijn_sql,
    get_atc_for_spkode,
    get_atc_details,
)

# ==============================================================================
# Regex/config
# ==============================================================================

_SECTION_STOP_RE = re.compile(
    r"^\s*(Episodes|Contra-?indicaties|Allergie|Allergieën|Intoleranties)\b",
    re.IGNORECASE,
)

_HEADER_RE = re.compile(
    r"^\s*Medicatie\b.*\bDosering\b.*\bIngang\b.*\bStopt\b",
    re.IGNORECASE,
)

# Nieuwe rij begint met "C " / "Z " / "T " (dus GEEN tab na C/Z/T)
_ROW_START_RE = re.compile(r"^\s*([CZT])\s+", re.IGNORECASE)

# Nederlandse datumvelden dd-mm-jjjj (ingang/stop)
_DATE_RE = re.compile(r"\b(\d{2}-\d{2}-\d{4})\b")

# Schema: x - x - x - x (x = getal, 0.5, 0,5, of x)
_SCHEMA_RE = re.compile(
    r"(?P<schema>(?:\d+(?:[.,]\d+)?|x)\s*-\s*(?:\d+(?:[.,]\d+)?|x)\s*-\s*(?:\d+(?:[.,]\d+)?|x)\s*-\s*(?:\d+(?:[.,]\d+)?|x))",
    re.IGNORECASE,
)

_TYPE_MAP = {"C": "Continu", "Z": "Zo nodig", "T": "Tijdelijk"}


# ==============================================================================
# Helpers
# ==============================================================================

def _strip_ais_suffixes(name: str) -> str:
    """
    Strip trailing AIS-tags ARBO/KK/OW uit geneesmiddelnaam.
    Werkt ook als vastgeplakt: 'tabletARBO' -> 'tablet'
    """
    if not name:
        return ""

    s = name.strip()

    # maak vastgeplakte suffixen los, en strip dan trailing tags
    s = re.sub(r"(ARBO|KK|OW)\s*$", r" \1", s, flags=re.IGNORECASE).strip()
    while True:
        s2 = re.sub(r"[\s\-\(\)\[\]]*(ARBO|KK|OW)\s*$", "", s, flags=re.IGNORECASE).strip()
        if s2 == s:
            break
        s = s2

    return s.strip()


def _extract_dates_and_strip(text: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Zoekt dd-mm-jjjj datums (ingang/stop) in de tekst.
    - ingang = eerste datum
    - stop   = tweede datum (als aanwezig)
    Retourneert: (text_zonder_datums, ingang, stop)
    """
    if not text:
        return "", None, None

    dates = _DATE_RE.findall(text)
    ingang = dates[0] if len(dates) >= 1 else None
    stop = dates[1] if len(dates) >= 2 else None

    stripped = _DATE_RE.sub("", text)
    stripped = " ".join(stripped.split()).strip(" ,;|-")
    stripped = stripped.strip()
    return stripped, ingang, stop


def _split_dose_and_comment(kind_letter: str, dose_text: str) -> Tuple[str, str]:
    """
    Jij wil:
    - type komt NIET uit de tekst, maar uit C/Z/T
    - dosering = "<MappedType>, <schema> <unit>"
    - opmerking = rest van dose_text na unit (kan leeg)

    dose_text is "kolom 3" in jouw beschrijving (maar kan ook extra rommel bevatten).
    """
    mapped = _TYPE_MAP.get(kind_letter.upper(), kind_letter.upper())

    s = " ".join((dose_text or "").split()).strip()
    if not s:
        return f"{mapped},", ""

    m = _SCHEMA_RE.search(s)
    if not m:
        # Geen schema -> toch voorspelbaar: alles in gebruik, opmerking leeg
        return f"{s}, {mapped}".strip(), ""

    schema = m.group("schema").strip()
    after = s[m.end():].lstrip()

    unit = ""
    rest = ""
    if after:
        parts = after.split(maxsplit=1)
        unit = parts[0].strip()
        rest = parts[1].strip() if len(parts) > 1 else ""

    gebruik = f"{schema} {unit}, {mapped}".strip()
    return gebruik, rest


def _parse_row_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse één medicatieregel.

    Jouw format (belangrijk!):
    - Geen tab tussen C/Z/T en geneesmiddel (spatie)
    - Wel tab tussen geneesmiddel en 'doseringveld'
    - Geen betrouwbare tabs tussen ingang/stop/opmerking -> dat zijn datums (dd-mm-jjjj)
    - Alles vanaf '4e tab' wil je sowieso negeren, maar in praktijk gebruiken we datums om te strippen.

    Strategie:
    1) Pak C/Z/T + geneesmiddel tot aan eerste tab
    2) Alles na eerste tab = dose_blob (kan tabs bevatten; die nemen we mee als spaties)
    3) Strip datums uit dose_blob -> ingang/stop, rest = dose_without_dates
    4) Split dose_without_dates -> gebruik + opmerking (schema+unit)
    """
    m = _ROW_START_RE.match(line)
    if not m:
        return None

    kind = m.group(1).upper()
    rest = line[m.end():]

    # Verwacht minstens 1 tab die het medicijn van de rest scheidt
    if "\t" not in rest:
        return None

    left, right = rest.split("\t", 1)  # left = medicijn, right = alles daarna
    med_raw = left.strip()
    dose_blob = right.replace("\t", " ").strip()  # rest tabs zijn niet betrouwbaar -> maak spaties

    # AIS zooi strippen + clean_name (zoals afdeling)
    med_clean = clean_name(_strip_ais_suffixes(med_raw))

    # ingang/stop datums eruit halen (waar ze ook staan)
    dose_wo_dates, ingang, stop = _extract_dates_and_strip(dose_blob)

    # splits dose/comment volgens jouw schema+unit regel
    gebruik, opm = _split_dose_and_comment(kind, dose_wo_dates)

    return {
        "kind": kind,
        "clean": med_clean,
        "gebruik": gebruik,
        "opmerking": opm.strip(),
        # extra velden (optioneel; je kunt ze downstream negeren)
        "ingang_per": ingang,
        "stopt_per": stop,
    }


def _extract_rows_single_patient(text: str) -> List[Dict[str, Any]]:
    """
    Extract alle medicatieregels + continuation-lines (zoals afdeling-parser idee):
    - Nieuwe rij: begint met C/Z/T + spatie
    - Continuation: niet leeg, niet nieuwe rij, dan append naar opmerking
    - Stop bij Episodes/Contra/Allergieën etc.
    """
    rows: List[Dict[str, Any]] = []
    if not text:
        return rows

    in_table = False
    current: Optional[Dict[str, Any]] = None

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue

        if _SECTION_STOP_RE.match(line):
            break

        if _HEADER_RE.search(line):
            in_table = True
            continue

        if not in_table:
            continue

        parsed = _parse_row_line(line)
        if parsed:
            current = parsed
            rows.append(current)
            continue

        # continuation line -> bij opmerking plakken tot volgende C/Z/T start
        if current is not None:
            extra = " ".join(line.strip().split())
            if extra:
                if current["opmerking"]:
                    current["opmerking"] += " " + extra
                else:
                    current["opmerking"] = extra

    return rows


# ==============================================================================
# Main entrypoint (zelfde event-types als afdeling)
# ==============================================================================

def process_medimo_patient_text_stream(text: str) -> Iterator[Dict[str, Any]]:
    """
    Zelfde event-types als process_medimo_text_stream (afdeling):
    - status
    - meta
    - progress
    - result
    """
    yield {"type": "status", "msg": "Database verbinden...", "pct": 0}
    conn = get_db()
    cursor = conn.cursor()

    # best-effort patient info (vaak niet aanwezig in single export)
    patient_name = "Onbekend"
    dob_iso = None
    age = None
    m = re.search(
        r"^\s*(Dhr\.|Mevr\.)\s+.*\(\d{1,2}-\d{1,2}-\d{4}\)\s*$",
        text,
        flags=re.MULTILINE,
    )
    if m:
        patient_name, dob_iso, age = extract_patient_details(m.group(0).strip())

    rows = _extract_rows_single_patient(text)
    total = len(rows)

    yield {"type": "meta", "afdeling": "Individueel", "total_patients": 1}

    clean_meds = []
    for idx, gm in enumerate(rows):
        pct = int((idx / max(total, 1)) * 100)
        yield {
            "type": "progress",
            "pct": pct,
            "current_patient": patient_name,
            "processed": idx,
            "total": total,
        }

        nmnr, hpkode, spkode, atc_override = match_medicijn_sql(gm["clean"], cursor)
        atc_code = atc_override or get_atc_for_spkode(spkode, cursor)
        details = get_atc_details(atc_code, cursor)

        med_entry = {**gm, **details}
        med_entry["NMNR"] = nmnr
        med_entry["HPKode"] = hpkode
        med_entry["SPKode"] = spkode
        clean_meds.append(med_entry)

    conn.close()

    results = [
        {
            "naam": patient_name,
            "geboortedatum": dob_iso,
            "leeftijd": age,
            "geneesmiddelen": clean_meds,
        }
    ]

    yield {"type": "progress", "pct": 100, "msg": "Afronden..."}
    yield {"type": "result", "data": results, "afdeling": "Individueel"}


# ==============================================================================
# CLI test
# ==============================================================================

if __name__ == "__main__":
    path = os.path.join("raw_data", "medimo_single_patient.txt")
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()

    last = None
    for event in process_medimo_patient_text_stream(txt):
        if event["type"] in ("status", "meta", "progress"):
            print(event)
        last = event

    print("\n=== RESULT (laatste event) ===")
    print(last)
