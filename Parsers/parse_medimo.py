import os
import sqlite3
import re
import unicodedata

def load_fixed_width_file(file_path, columns):
    data = []
    with open(file_path, 'r', encoding='latin-1') as f:
        for line in f:
            row = {col[0]: line[col[1]:col[2]].strip() for col in columns}
            data.append(row)
    return data

def extract_patient_blocks(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    start = re.search(r"(Dhr\. |Mevr\. )", content)
    if not start:
        return []
    content = content[start.start():]
    raw_blocks = re.split(r'(?=Dhr\. |Mevr\. )', content)
    return [block.strip() for block in raw_blocks if block.strip().startswith(("Dhr.", "Mevr."))]

def clean_name(name):
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("\u200b", "")
    name = name.strip()
    return name

def parse_medimo_block(block):
    lines = block.strip().split("\n")
    geneesmiddelen = []
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(("C", "Z")):
            regel = re.sub(r"^[CZ]\s+", "", line)
            delen = re.split(r'\s{2,}|\t+', regel)
            if len(delen) < 2:
                i += 1
                continue
            gm_naam = delen[0].strip()
            gebruik = delen[1].strip()
            opmerking = ""
            if i + 1 < len(lines):
                volgende = lines[i + 1].strip()
                if volgende != "" and not volgende.startswith(("C", "Z", "Dhr.", "Mevr.")):
                    opmerking = volgende
                    i += 1
            geneesmiddelen.append({
                "origineel": regel,
                "clean": gm_naam,
                "gebruik": gebruik,
                "opmerking": opmerking
            })
        i += 1
    return geneesmiddelen

def lichte_fuzzy_match(gm_clean, bst020):
    gm_norm = clean_name(gm_clean).lower()
    gm_tokens = set(gm_norm.split())
    beste_match = None
    meeste_overlap = 0
    for row in bst020:
        naam = clean_name(row["NMNAAM"]).lower()
        naam_tokens = set(naam.split())
        gemeenschappelijk = len(gm_tokens & naam_tokens)
        min_aantal = min(len(gm_tokens), len(naam_tokens))
        overlap_ratio = gemeenschappelijk / min_aantal if min_aantal > 0 else 0
        if overlap_ratio > 0.6 or gm_norm in naam or naam in gm_norm:
            if gemeenschappelijk > meeste_overlap:
                beste_match = row
                meeste_overlap = gemeenschappelijk
    return beste_match["NMNR"] if beste_match else None

def match_to_spkode(gm_clean, bst020, bst052, bst004, bst070, bst711, db_spkodes):
    nmnr = lichte_fuzzy_match(gm_clean, bst020)
    if not nmnr:
        return None, None, None

    mogelijke_spkodes = []

    # 1. Direct via BST711T
    for row in bst711:
        if row["GPNMNR"] == nmnr or row["GPSTNR"] == nmnr:
            mogelijke_spkodes.append((None, row["SPKODE"]))

    # 2. Via PRKODE → GPKODE → SPKODE
    for row in bst052:
        if row["PRNMNR"] == nmnr:
            gpkode = row["GPKODE"]
            for rij in bst711:
                if rij["GPKODE"] == gpkode or rij["GSKODE"] == gpkode:
                    mogelijke_spkodes.append((None, rij["SPKODE"]))

    # 3. Via HPKODE → GPKODE → SPKODE
    hpkodes = [r["HPKODE"] for r in bst004 if r["ATNMNR"] == nmnr]
    for hpkode in hpkodes:
        for row in bst070:
            if row["HPKODE"] == hpkode:
                gpkode = row["GPKODE"]
                for rij in bst711:
                    if rij["GPKODE"] == gpkode or rij["GSKODE"] == gpkode:
                        mogelijke_spkodes.append((hpkode, rij["SPKODE"]))

    # Kies eerste SPKode die ook in de database zit
    for hpk, spk in mogelijke_spkodes:
        if spk in db_spkodes:
            return nmnr, hpk, spk

    # Anders neem gewoon eerste beschikbare
    if mogelijke_spkodes:
        return nmnr, mogelijke_spkodes[0][0], mogelijke_spkodes[0][1]

    return nmnr, None, None

def get_spkodes_in_db(db_path="geneesmiddelen.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT DISTINCT SPKode FROM geneesmiddelen")
    result = [row[0] for row in c.fetchall()]
    conn.close()
    return set(result)

def match_to_fk_database(spkode, db_path="geneesmiddelen.db", atc_db_path="ATC_groepen.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT geneesmiddel, groep, ATC_groep FROM geneesmiddelen WHERE SPKode = ?", (spkode,))
    result = c.fetchone()
    conn.close()

    if not result:
        return None, None, None, None, None  # geneesmiddel, groep, ATC_groep, ATC_omschrijving, Jansen_omschrijving

    geneesmiddel, groep, atc_groep = result

    if not atc_groep:
        return geneesmiddel, groep, None, None, None

    atc_conn = sqlite3.connect(atc_db_path)
    atc_c = atc_conn.cursor()
    atc_c.execute("SELECT ATC_groep, ATC_omschrijving, Jansen_omschrijving FROM ATC_groepen WHERE ATC_groep = ?", (atc_groep,))
    atc_result = atc_c.fetchone()
    atc_conn.close()

    if not atc_result:
        return geneesmiddel, groep, atc_groep, None, None

    atc_groep, atc_omschrijving, jansen_omschrijving = atc_result
    return geneesmiddel, groep, atc_groep, atc_omschrijving, jansen_omschrijving

def main():
    dir_path = "G-Standaard"
    bst020_path = os.path.join(dir_path, "BST020T")
    bst004_path = os.path.join(dir_path, "BST004T")
    bst052_path = os.path.join(dir_path, "BST052T")
    bst070_path = os.path.join(dir_path, "BST070T")
    bst711_path = os.path.join(dir_path, "BST711T")
    medimo_path = "Data/medimo_input.txt"

    bst020_cols = [("NMNR", 5, 12), ("NMNAAM", 85, 135)]
    bst004_cols = [("HPKODE", 13, 21), ("ATNMNR", 21, 28)]
    bst052_cols = [("PRKODE", 5, 13), ("PRNMNR", 13, 20), ("GPKODE", 20, 28)]
    bst070_cols = [("HPKODE", 5, 13), ("GPKODE", 29, 37)]
    bst711_cols = [
        ("GPKODE", 5, 13), ("GSKODE", 13, 21),
        ("GPNMNR", 33, 40), ("GPSTNR", 40, 47),
        ("SPKODE", 104, 112)
    ]

    bst020 = load_fixed_width_file(bst020_path, bst020_cols)
    bst004 = load_fixed_width_file(bst004_path, bst004_cols)
    bst052 = load_fixed_width_file(bst052_path, bst052_cols)
    bst070 = load_fixed_width_file(bst070_path, bst070_cols)
    bst711 = load_fixed_width_file(bst711_path, bst711_cols)

    db_spkodes = get_spkodes_in_db()

    patiënten = extract_patient_blocks(medimo_path)

    for patiënt in patiënten:
        regel1 = patiënt.split("\n")[0].strip()
        print(f"\nPatiënt: {regel1}")
        
        gm_list = parse_medimo_block(patiënt)
        for gm in gm_list:
            nmnr, hpkode, spkode = match_to_spkode(gm["clean"], bst020, bst052, bst004, bst070, bst711, db_spkodes)
            fk_naam, fk_groep, atc_groep, atc_omschrijving, jansen_omschrijving = (
                match_to_fk_database(spkode) if spkode else (None, None, None, None, None)
            )
            
            status = "✅" if fk_groep else "❌"

            print(f"  {status} {gm['clean']}")
            print(f"    → NMNR: {nmnr}, HPKODE: {hpkode}, SPKode: {spkode}")
            print(f"    → FK Groep: {fk_groep} ({fk_naam})")
            print(f"    → ATC Groep: {atc_groep}")
            print(f"    → ATC Omschrijving: {atc_omschrijving}")
            print(f"    → Jansen Omschrijving: {jansen_omschrijving}")
            print(f"    → Gebruik: {gm['gebruik']} | Opmerking: {gm['opmerking']}\n")

def run_parser():
    """
    Draait het volledige parse proces en retourneert een lijst van patiënt dicts + afdelingsnaam + db_spkodes.
    """
    dir_path = "G-Standaard"
    bst020_path = os.path.join(dir_path, "BST020T")
    bst004_path = os.path.join(dir_path, "BST004T")
    bst052_path = os.path.join(dir_path, "BST052T")
    bst070_path = os.path.join(dir_path, "BST070T")
    bst711_path = os.path.join(dir_path, "BST711T")
    medimo_path = "Data/medimo_input.txt"

    bst020_cols = [("NMNR", 5, 12), ("NMNAAM", 85, 135)]
    bst004_cols = [("HPKODE", 13, 21), ("ATNMNR", 21, 28)]
    bst052_cols = [("PRKODE", 5, 13), ("PRNMNR", 13, 20), ("GPKODE", 20, 28)]
    bst070_cols = [("HPKODE", 5, 13), ("GPKODE", 29, 37)]
    bst711_cols = [
        ("GPKODE", 5, 13), ("GSKODE", 13, 21),
        ("GPNMNR", 33, 40), ("GPSTNR", 40, 47),
        ("SPKODE", 104, 112)
    ]

    bst020 = load_fixed_width_file(bst020_path, bst020_cols)
    bst004 = load_fixed_width_file(bst004_path, bst004_cols)
    bst052 = load_fixed_width_file(bst052_path, bst052_cols)
    bst070 = load_fixed_width_file(bst070_path, bst070_cols)
    bst711 = load_fixed_width_file(bst711_path, bst711_cols)
    db_spkodes = get_spkodes_in_db()

    with open(medimo_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Afdelingsnaam extraheren
    afdeling_match = re.search(r"Een overzicht van alle actieve medicatie in afdeling (.+?)\.", content)
    afdeling = afdeling_match.group(1).strip() if afdeling_match else "Onbekend"

    patiënten = extract_patient_blocks(medimo_path)
    resultaat = []

    for patiënt in patiënten:
        gm_list = parse_medimo_block(patiënt)
        for gm in gm_list:
            nmnr, hpkode, spkode = match_to_spkode(gm["clean"], bst020, bst052, bst004, bst070, bst711, db_spkodes)
            gm["SPKode"] = spkode
        resultaat.append({"patiënt": patiënt.split("\n")[0].strip(), "geneesmiddelen": gm_list})

    return resultaat, db_spkodes, afdeling

if __name__ == "__main__":
    main()
