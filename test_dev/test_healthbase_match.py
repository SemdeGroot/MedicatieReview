import os
import re
import csv
import unicodedata
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any

# ============================================================
# PAD-INSTELLINGEN
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, "..", "raw_data")

MEDIMO_PATH = os.path.join(RAW_DIR, "medimo_input.txt")
HEALTHBASE_CSV = os.path.join(RAW_DIR, "healthbase/healthbase_taxe_dec2025.csv")  # pas eventueel aan


# ============================================================
# HULPFUNCTIES (GEKOPIEERD UIT JE BESTAANDE PARSER)
# ============================================================
def clean_name(name: str) -> str:
    """Normaliseer en maak geneesmiddelnaam schoon (idem aan je parser)."""
    if not name:
        return ""
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("\u200b", "")
    return name.strip()


def extract_patient_blocks(content: str) -> List[str]:
    """Splits medimo-tekst in patientblokken, startend bij Dhr./Mevr."""
    start = re.search(r"(Dhr\. |Mevr\. )", content)
    if not start:
        return []
    content = content[start.start():]
    raw_blocks = re.split(r'(?=Dhr\. |Mevr\. )', content)
    return [b.strip() for b in raw_blocks if b.strip().startswith(("Dhr.", "Mevr."))]


def parse_medimo_block(block: str) -> List[Dict[str, Any]]:
    """
    Parse 1 medimo-blok naar een lijst geneesmiddelen.
    Zelfde logica als in je bestaande parser.
    """
    lines = block.strip().split("\n")
    geneesmiddelen = []
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(("C", "Z", "T")):
            regel = re.sub(r"^[CZT]\s+", "", line)
            delen = re.split(r'\s{2,}|\t+', regel)
            if len(delen) < 2:
                i += 1
                continue

            opmerking = ""
            if i + 1 < len(lines):
                volgende = lines[i + 1].strip()
                if (
                    volgende
                    and not volgende.startswith(("C", "Z", "T", "Dhr.", "Mevr."))
                ):
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

            today = datetime.today().date()
            leeftijd = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        except ValueError:
            pass

    return naam, dob_iso, leeftijd


# ============================================================
# HEALTHBASE CSV LADEN (MET RECORDS + EXACT INDEX)
# ============================================================
def load_healthbase(csv_path: str) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    """
    Laad healthbase CSV in:
      - exact_index: clean_name(naam).lower() -> ATC
      - records: lijst met {"name": orig, "clean": clean, "atc": atc}
    CSV is ;-gescheiden, eerste rij is header.
    """
    exact_index: Dict[str, str] = {}
    records: List[Dict[str, str]] = []

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Healthbase CSV niet gevonden op: {csv_path}")

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader, None)  # header overslaan

        for row in reader:
            if len(row) < 9:
                continue

            raw_naam = (row[2] or "").strip()   # 3e kolom
            atc = (row[8] or "").strip()       # 9e kolom

            if not raw_naam or not atc:
                continue

            clean = clean_name(raw_naam).lower()
            if not clean:
                continue

            records.append({
                "name": raw_naam,
                "clean": clean,
                "atc": atc
            })

            # Eerste ATC wint bij dubbele namen, dat is voor test prima
            exact_index.setdefault(clean, atc)

    return exact_index, records


# ============================================================
# MATCHING MET WOORDEN-LOOP (GEÏNSPIREERD OP match_medicijn_sql)
# ============================================================
def find_atc_in_healthbase_smart(
    gm_name: str,
    exact_index: Dict[str, str],
    records: List[Dict[str, str]]
) -> Optional[str]:
    """
    Zoek ATC in healthbase op basis van opgeschoonde naam van Medimo.
    Strategie:
      1) exact match op volledige clean_name
      2) woorden-loop zoals in G-standaard parser:
         - tokens = full_clean.split()
         - voor k = n..1:
             * candidate = tokens[:k]
             * eerst exact op candidate
             * dan prefix-scan met boundary pattern
    """
    full_clean = clean_name(gm_name).lower()
    if not full_clean:
        return None

    # 1. exact match
    if full_clean in exact_index:
        return exact_index[full_clean]

    tokens = full_clean.split()
    n = len(tokens)

    # 2. woorden-loop van langste prefix naar kortste
    for k in range(n, 0, -1):
        candidate = " ".join(tokens[:k]).strip()
        # sla hele korte dingen over (zoals 'mg', '1', '2x', etc.)
        if len(candidate) < 3:
            continue

        # 2A. exact op ingekorte naam
        if candidate in exact_index:
            return exact_index[candidate]

        # 2B. boundary/prefix scan zoals in match_medicijn_sql
        # names die beginnen met candidate + spatie/streepje/boundary
        boundary_pat = re.compile(
            r'^' + re.escape(candidate) + r'(?:\b|[ \-/_]|$)'
        )

        for rec in records:
            nm_clean = rec["clean"]
            if boundary_pat.match(nm_clean):
                return rec["atc"]

    # Geen match gevonden
    return None


# ============================================================
# MAIN TESTLOGICA
# ============================================================
def main():
    # 1. Healthbase CSV indexeren
    print(f"🔍 Healthbase CSV laden vanuit: {HEALTHBASE_CSV}")
    exact_index, records = load_healthbase(HEALTHBASE_CSV)
    print(f"✅ {len(exact_index)} unieke namen met ATC in exact index.")
    print(f"✅ {len(records)} total records geladen.\n")

    # 2. Medimo tekst inlezen
    if not os.path.exists(MEDIMO_PATH):
        raise FileNotFoundError(f"medimo_input.txt niet gevonden op: {MEDIMO_PATH}")

    with open(MEDIMO_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    # 3. Patiënten + medicatie parsen (zelfde logica als je generator)
    blocks = extract_patient_blocks(text)
    print(f"📄 Gevonden patientblokken: {len(blocks)}\n")

    total_meds = 0
    matched_meds = 0

    for block in blocks:
        header_line = block.split("\n")[0].strip()
        patient_name, dob_iso, age = extract_patient_details(header_line)

        gm_list = parse_medimo_block(block)

        print(f"👤 Patiënt: {patient_name} (#{len(gm_list)} medicatie-items)")
        for gm in gm_list:
            total_meds += 1
            raw_name = gm["clean"]
            atc = find_atc_in_healthbase_smart(raw_name, exact_index, records)

            if atc:
                matched_meds += 1
                print(f"  ✅ '{raw_name}' → ATC (Healthbase): {atc}")
            else:
                print(f"  ⛔ '{raw_name}' → GEEN ATC-match in Healthbase")

        print()  # lege regel tussen patiënten

    print("============== SAMENVATTING ==============")
    print(f"Totaal aantal geneesmiddelen: {total_meds}")
    print(f"Aantal met ATC-match:        {matched_meds}")
    if total_meds > 0:
        pct = 100 * matched_meds / total_meds
        print(f"Matchpercentage:            {pct:.1f}%")
    print("===========================================")


if __name__ == "__main__":
    main()
