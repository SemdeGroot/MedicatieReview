# core/parsers/parse_pharmacom_patient.py

import io
import re
from datetime import date, datetime
from typing import Iterator, Dict, Any, Optional, List, Tuple

import pdfplumber

from core.database import get_db_connection as get_db
from core.lookup import (
    clean_name,
    match_medicijn_sql,
    get_atc_for_spkode,
    get_atc_details,
)

_ALL_DATES_RE = re.compile(r"\d{2}-\d{2}-\d{4}")


def _parse_date_nl(s: str) -> Optional[date]:
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _calc_leeftijd(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _title_med_naam(s: str) -> str:
    """Title-case medication name. Digit-prefixed tokens stay lowercase."""
    parts = []
    for word in s.split():
        if word and word[0].isalpha():
            parts.append(word[0].upper() + word[1:].lower())
        else:
            parts.append(word.lower())
    return " ".join(parts)


# ==============================================================================
# PDF EXTRACTION
# ==============================================================================

def _extract_patient_info(text: str) -> Tuple[Optional[str], Optional[date], Optional[str]]:
    """Extract naam, geboortedatum, geslacht from first page text."""
    naam = None
    geboortedatum = None
    geslacht = None

    name_m = re.search(r"^(.+?)\s+BSN\s*:", text, re.MULTILINE)
    if name_m:
        raw = name_m.group(1).strip()
        naam = raw.title() if raw else None

    dob_m = re.search(r"Geboortedatum:\s*(\d{2}-\d{2}-\d{4})", text)
    if dob_m:
        geboortedatum = _parse_date_nl(dob_m.group(1))

    gender_m = re.search(r"Geslacht\s*:\s*([MV])", text)
    if gender_m:
        geslacht = gender_m.group(1)

    return naam, geboortedatum, geslacht


def _collect_verstrekte_rows(pdf) -> List[list]:
    """Collect only 'Verstrekte medicatie' table rows from all pages."""
    rows: List[list] = []

    for page in pdf.pages:
        for table in page.extract_tables():
            if not table or not table[0]:
                continue
            header_cell = (table[0][0] or "").strip()

            if "Verstrekte medicatie" in header_cell:
                for row in table[1:]:
                    if row and "Gestopte medicatie" in (row[0] or ""):
                        break
                    rows.append(row)
            # Skip ICA/ADE, LAB waarden, Gestopte medicatie tables

    return rows


def _extract_medicaties(rows: List[list]) -> List[Dict[str, Any]]:
    """Extract medications from verstrekte medicatie table rows."""
    medicaties = []
    seen: set = set()

    for row in rows:
        if not row or not row[0]:
            continue
        naam_raw = row[0].split("\n")[0].strip()
        if not naam_raw:
            continue

        naam = _title_med_naam(naam_raw)

        # col[1]: start dates
        raw_dates = _ALL_DATES_RE.findall(row[1] or "") if len(row) > 1 else []
        parsed_dates = [d for s in raw_dates if (d := _parse_date_nl(s))]
        ingang_per = min(parsed_dates) if parsed_dates else None

        # col[2]: stop dates
        stopt_per = None
        if len(row) > 2 and row[2]:
            afgel_dates = [d for s in _ALL_DATES_RE.findall(row[2]) if (d := _parse_date_nl(s))]
            stopt_per = max(afgel_dates) if afgel_dates else None

        # col[3]: dosering, col[4]: toedienweg
        dosering = row[3].split("\n")[0].strip() if len(row) > 3 and row[3] else ""
        toedienweg = row[4].split("\n")[0].strip() if len(row) > 4 and row[4] else ""

        # Build composite gebruik
        basis = f"{dosering} {toedienweg}".strip()
        gebruik_parts = [basis] if basis else []
        if ingang_per:
            gebruik_parts.append(f"ingang: {ingang_per.strftime('%d-%m-%Y')}")
        if stopt_per:
            gebruik_parts.append(f"stop: {stopt_per.strftime('%d-%m-%Y')}")
        gebruik = " | ".join(gebruik_parts)

        key = (naam.lower(), gebruik, ingang_per, stopt_per)
        if key in seen:
            continue
        seen.add(key)

        medicaties.append({
            "naam": naam,
            "clean": clean_name(naam),
            "gebruik": gebruik,
            "opmerking": "",
            "ingang_per": ingang_per,
            "stopt_per": stopt_per,
        })

    return medicaties


# ==============================================================================
# MAIN ENTRYPOINT (GENERATOR)
# ==============================================================================

def process_pharmacom_patient_pdf_stream(file_bytes: bytes) -> Iterator[Dict[str, Any]]:
    """
    Parse Pharmacom PDF en yield streaming events.
    Zelfde event-types als medimo parsers: status, meta, progress, result.
    """
    yield {"type": "status", "msg": "PDF openen...", "pct": 0}

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page1_text = pdf.pages[0].extract_text() or "" if pdf.pages else ""
            verstrekte_rows = _collect_verstrekte_rows(pdf)
    except Exception as e:
        yield {"type": "error", "msg": f"Kan PDF niet lezen: {str(e)}"}
        return

    naam, geboortedatum, geslacht = _extract_patient_info(page1_text)

    if naam is None:
        yield {"type": "error", "msg": "Kan geen patientgegevens uit de PDF halen."}
        return

    if geslacht == "M":
        naam = f"Dhr. {naam}"
    elif geslacht == "V":
        naam = f"Mevr. {naam}"

    leeftijd = _calc_leeftijd(geboortedatum) if geboortedatum else None

    # Filter gestopte medicatie
    today = date.today()
    medicaties = [
        m for m in _extract_medicaties(verstrekte_rows)
        if not (m.get("stopt_per") and m["stopt_per"] < today)
    ]

    total = len(medicaties)
    yield {"type": "meta", "afdeling": "Individueel", "total_patients": 1}

    # ATC verrijking
    yield {"type": "status", "msg": "Database verbinden...", "pct": 10}
    conn = get_db()
    cursor = conn.cursor()

    clean_meds = []
    for idx, med in enumerate(medicaties):
        pct = 10 + int((idx / max(total, 1)) * 80)
        yield {
            "type": "progress",
            "pct": pct,
            "current_patient": naam,
            "processed": idx,
            "total": total,
        }

        nmnr, hpkode, spkode, atc_override = match_medicijn_sql(med["clean"], cursor)
        atc_code = atc_override or get_atc_for_spkode(spkode, cursor)
        details = get_atc_details(atc_code, cursor)

        med_entry = {
            "clean": med["clean"],
            "gebruik": med["gebruik"],
            "opmerking": "",
            **details,
            "NMNR": nmnr,
            "HPKode": hpkode,
            "SPKode": spkode,
        }
        clean_meds.append(med_entry)

    conn.close()

    dob_iso = geboortedatum.isoformat() if geboortedatum else None

    results = [{
        "naam": naam,
        "geboortedatum": dob_iso,
        "leeftijd": leeftijd,
        "geneesmiddelen": clean_meds,
    }]

    yield {"type": "progress", "pct": 100, "msg": "Afronden..."}
    yield {"type": "result", "data": results, "afdeling": "Individueel"}
