# medimo_parser_atc3.py
# -------------------------------------------------
# Parseert Medimo-export en koppelt per geneesmiddel:
# - NMNR (BST020T) op basis van naam
# - SPKode via 3 routes (BST711 direct, via PR, via HP)
# - ATC-code via BST711 (kolom 118:126) o.b.v. SPKode
# - ATC-groep (eerste 3 tekens) + omschrijving uit ATC_groepen.db
#
# Geen gebruik van 'geneesmiddelen.db'.

import os
import re
import sqlite3
import unicodedata

# -----------------------------
# Fixed-width inlezers
# -----------------------------
def load_fixed_width_file(file_path, columns, encoding='utf-8'):
    """
    Leest fixed-width bestand en geeft list[dict] met opgegeven kolommen.
    columns: lijst tuples (veldnaam, start_index, end_index)
    """
    data = []
    with open(file_path, 'r', encoding=encoding) as f:
        for line in f:
            row = {col[0]: line[col[1]:col[2]].strip() for col in columns}
            data.append(row)
    return data


# -----------------------------
# Medimo parsing
# -----------------------------
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
    return name.strip()


def parse_medimo_block(block):
    lines = block.strip().split("\n")
    geneesmiddelen = []
    i = 1  # regel 0 = naamregel (Dhr./Mevr.)
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
                if volgende and not volgende.startswith(("C", "Z", "Dhr.", "Mevr.")):
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


# -----------------------------
# Naam → NMNR (BST020T)
# -----------------------------
def exact_nmnr_match(name: str, bst020):
    """
    Zoek een exacte match (na normalisatie) in BST020 op NMNAAM.
    Retourneert NMNR of None als er geen match is.
    """
    name_norm = clean_name(name).lower()
    for row in bst020:
        if clean_name(row["NMNAAM"]).lower() == name_norm:
            return row["NMNR"]
    return None


# -----------------------------
# NMNR → SPKode via routes
# -----------------------------
def _attempt_resolve_sp(nmnr, bst052, bst004, bst070, bst711):
    """
    Drie routes NMNR → SPKode. Retourneert (nmnr, hpkode, spkode) of None.
    """
    if not nmnr:
        return None

    mogelijke_spkodes = []

    # (1) Direct via BST711T
    for row in bst711:
        if row["SPKODE"] and (row["GPSTNR"] == nmnr or row["GPNMNR"] == nmnr):
            mogelijke_spkodes.append((None, row["SPKODE"]))

    # (2) Via PR → GP → SP
    for row in bst052:
        if row["PRNMNR"] == nmnr:
            gpkode = row["GPKODE"]
            for rij in bst711:
                if rij["SPKODE"] and (rij["GPKODE"] == gpkode or rij["GSKODE"] == gpkode):
                    mogelijke_spkodes.append((None, rij["SPKODE"]))

    # (3) Via HP → GP → SP
    hpkodes = [r["HPKODE"] for r in bst004 if r["ATNMNR"] == nmnr]
    for hpkode in hpkodes:
        for row in bst070:
            if row["HPKODE"] == hpkode:
                gpkode = row["GPKODE"]
                for rij in bst711:
                    if rij["SPKODE"] and (rij["GPKODE"] == gpkode or rij["GSKODE"] == gpkode):
                        mogelijke_spkodes.append((hpkode, rij["SPKODE"]))

    if mogelijke_spkodes:
        # eenvoudige strategie: eerste hit teruggeven
        return nmnr, mogelijke_spkodes[0][0], mogelijke_spkodes[0][1]

    return None


def match_to_spkode(gm_clean, bst020, bst052, bst004, bst070, bst711):
    """
    PRIMAIRE UITKOMST: SPKode vinden m.b.v. gm_naam uit parse_medimo_block.
    Strategie:
      1) Probeer VOLLEDIGE gm_naam → NMNR → (routes) → SPKode.
      2) Als géén SPKode: herhaal met prefixen door telkens het LAATSTE woord te verwijderen:
         (N-1) woorden, dan (N-2), ... tot 1 woord over is.
      3) Voor elke kandidaatnaam:
           - NMNR = exact_nmnr_match(kandidaat, BST020)
           - Probeer SP via _attempt_resolve_sp (routes: direct/PR/HP)

    Retourneert: (nmnr, hpkode, spkode)
    """
    full_clean = clean_name(gm_clean)
    if not full_clean:
        return None, None, None

    tokens = full_clean.split()
    n = len(tokens)

    # 0) Volledige naam
    nmnr_full = exact_nmnr_match(full_clean, bst020)
    res_full = _attempt_resolve_sp(nmnr_full, bst052, bst004, bst070, bst711) if nmnr_full else None
    if res_full:
        return res_full  # (nmnr, hpkode, spkode)

    # 1) Prefixen: van N-1 naar 1 woord (telkens laatste woord eraf)
    for k in range(n - 1, 0, -1):
        candidate = " ".join(tokens[:k])
        nmnr_k = exact_nmnr_match(candidate, bst020)
        res_k = _attempt_resolve_sp(nmnr_k, bst052, bst004, bst070, bst711) if nmnr_k else None
        if res_k:
            return res_k  # (nmnr, hpkode, spkode)

    # 2) Geen SPKode gevonden
    return None, None, None


# -----------------------------
# SPKode → ATC (BST711 kolom 118:126)
# -----------------------------
def build_spkode_to_atc_map(bst711):
    """
    Bouw dict: SPKode -> ATC_code (volledige string uit kolommen 118:126).
    """
    mapping = {}
    for row in bst711:
        spk = row["SPKODE"]
        atc = row["ATC"]
        if spk and atc:
            mapping[spk] = atc
    return mapping


def atc_to_group3(atc_code):
    """
    Geef eerste 3 tekens van ATC-code (bijv. C07AB02 → C07).
    """
    if not atc_code or len(atc_code) < 3:
        return None
    return atc_code[:3]


# -----------------------------
# ATC_groepen.db lookup (3-tekens)
# -----------------------------
def lookup_atc3_info(atc3, atc_db_path="ATC_groepen.db"):
    """
    Zoekt ATC-groep (3 tekens) in ATC_groepen.db.
    Verwacht tabel: ATC_groepen(ATC_groep, ATC_omschrijving, Jansen_omschrijving)
    """
    if not atc3:
        return None, None, None
    conn = sqlite3.connect(atc_db_path)
    c = conn.cursor()
    c.execute(
        "SELECT ATC_groep, ATC_omschrijving, Jansen_omschrijving FROM ATC_groepen WHERE ATC_groep = ?",
        (atc3,)
    )
    row = c.fetchone()
    conn.close()
    if row:
        return row[0], row[1], row[2]
    return None, None, None


# -----------------------------
# Main / Run
# -----------------------------
def main():
    dir_path = "G-Standaard"
    bst020_path = os.path.join(dir_path, "BST020T")
    bst004_path = os.path.join(dir_path, "BST004T")
    bst052_path = os.path.join(dir_path, "BST052T")
    bst070_path = os.path.join(dir_path, "BST070T")
    bst711_path = os.path.join(dir_path, "BST711T")
    medimo_path = "Data/medimo_input.txt"

    # Kolommen (posities conform jouw scripts)
    bst020_cols = [("NMNR", 5, 12), ("NMNAAM", 85, 135)]
    bst004_cols = [("HPKODE", 13, 21), ("ATNMNR", 21, 28)]
    bst052_cols = [("PRKODE", 5, 13), ("PRNMNR", 13, 20), ("GPKODE", 20, 28)]
    bst070_cols = [("HPKODE", 5, 13), ("GPKODE", 29, 37)]
    bst711_cols = [
        ("GPKODE", 5, 13), ("GSKODE", 13, 21),
        ("GPNMNR", 33, 40), ("GPSTNR", 40, 47),
        ("SPKODE", 104, 112),
        ("ATC", 118, 126),  # <-- ATC-code direct uit BST711
    ]

    # Inlezen G-Standaard
    bst020 = load_fixed_width_file(bst020_path, bst020_cols)
    bst004 = load_fixed_width_file(bst004_path, bst004_cols)
    bst052 = load_fixed_width_file(bst052_path, bst052_cols)
    bst070 = load_fixed_width_file(bst070_path, bst070_cols)
    bst711 = load_fixed_width_file(bst711_path, bst711_cols)

    # SPKode → ATC mapping opbouwen
    spkode_to_atc = build_spkode_to_atc_map(bst711)

    # Medimo
    patiënten = extract_patient_blocks(medimo_path)

    for patiënt in patiënten:
        regel1 = patiënt.split("\n")[0].strip()
        print(f"\nPatiënt: {regel1}")

        gm_list = parse_medimo_block(patiënt)
        for gm in gm_list:
            nmnr, hpkode, spkode = match_to_spkode(
                gm["clean"], bst020, bst052, bst004, bst070, bst711
            )

            atc_code = spkode_to_atc.get(spkode)
            atc3 = atc_to_group3(atc_code)
            atc3_key, atc3_omschrijving, atc3_jansen = lookup_atc3_info(atc3)

            status = "✅" if spkode and atc3_key else "❌"
            print(f"  {status} {gm['clean']}")
            print(f"    → NMNR: {nmnr}, HPKODE: {hpkode}, SPKode: {spkode}")
            print(f"    → ATC: {atc_code}  | ATC3: {atc3}")
            print(f"    → ATC3 uit DB: {atc3_key} | Omschrijving: {atc3_omschrijving} | Jansen: {atc3_jansen}")
            print(f"    → Gebruik: {gm['gebruik']} | Opmerking: {gm['opmerking']}\n")


def run_parser():
    """
    Retourneert:
      - lijst dicts per patiënt met geneesmiddelen + SPKode + ATC + ATC3 + ATC3-omschrijving
      - afdelingsnaam (indien aanwezig)
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
        ("SPKODE", 104, 112),
        ("ATC", 118, 126),
    ]

    bst020 = load_fixed_width_file(bst020_path, bst020_cols)
    bst004 = load_fixed_width_file(bst004_path, bst004_cols)
    bst052 = load_fixed_width_file(bst052_path, bst052_cols)
    bst070 = load_fixed_width_file(bst070_path, bst070_cols)
    bst711 = load_fixed_width_file(bst711_path, bst711_cols)

    spkode_to_atc = build_spkode_to_atc_map(bst711)

    with open(medimo_path, "r", encoding="utf-8") as f:
        content = f.read()
    afdeling_match = re.search(r"Een overzicht van alle actieve medicatie in afdeling (.+?)\.", content)
    afdeling = afdeling_match.group(1).strip() if afdeling_match else "Onbekend"

    patiënten = extract_patient_blocks(medimo_path)
    resultaat = []

    for patiënt in patiënten:
        gm_list = parse_medimo_block(patiënt)
        for gm in gm_list:
            nmnr, hpkode, spkode = match_to_spkode(
                gm["clean"], bst020, bst052, bst004, bst070, bst711
            )
            atc_code = spkode_to_atc.get(spkode)
            atc3 = atc_to_group3(atc_code)
            atc3_key, atc3_omschrijving, atc3_jansen = lookup_atc3_info(atc3)

            gm["NMNR"] = nmnr
            gm["HPKode"] = hpkode
            gm["SPKode"] = spkode
            gm["ATC"] = atc_code
            gm["ATC3"] = atc3
            gm["ATC3_key"] = atc3_key
            gm["ATC3_omschrijving"] = atc3_omschrijving
            gm["ATC3_jansen"] = atc3_jansen

        resultaat.append({
            "patiënt": patiënt.split("\n")[0].strip(),
            "geneesmiddelen": gm_list
        })

    return resultaat, afdeling


if __name__ == "__main__":
    main()