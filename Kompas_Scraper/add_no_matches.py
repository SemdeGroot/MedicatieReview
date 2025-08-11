import json
import os
import re
import sqlite3
import unicodedata

BST_PATH = "G-Standaard/"
DB_PATH = "geneesmiddelen.db"
JSON_PATH = "Kompas_Scraper/SPK_match.json"

# ---------------------------
# Helpers
# ---------------------------

def clean_name(name: str) -> str:
    """Maak naam ASCII, haal (..), zero-width space weg, trim en lower."""
    if not name:
        return ""
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("\u200b", "")
    return name.strip().lower()

def load_bst020t(filepath: str):
    """
    Maak mapping: NMNAAM (clean, lower) -> NMNR
    Posities: NMNR [5:12], NMNAAM [85:135]
    """
    mapping = {}
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            nmnr = line[5:12].strip()
            nmnaam = line[85:135].strip()
            nmnaam = clean_name(nmnaam)
            if nmnaam and nmnr:
                mapping[nmnaam] = nmnr
    return mapping

def load_bst711t(filepath: str):
    """
    Lees BST711T in: we hebben GPNMNR [33:40], GPSTNR [40:47], SPKODE [104:112], ATCODE [118:126]
    (0-based slicing; ATCODE pos 119-126 -> slice [118:126])
    Return list of dicts
    """
    rows = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            rows.append({
                "GPNMNR": line[33:40].strip(),
                "GPSTNR": line[40:47].strip(),
                "SPKODE": line[104:112].strip(),
                "ATCODE": line[118:126].strip(),
            })
    return rows

def load_bst801t(filepath: str):
    """
    ATC-groep (eerste 3 tekens) -> NL omschrijving
    Posities: ATC-code [5:13], Omschrijving [13:93]
    Neem alleen entries waar de rest leeg is (pure 3-lettergroep).
    """
    mapping = {}
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            atc_code = line[5:13]
            atc_grp = atc_code[:3].strip()
            rest = atc_code[3:].strip()
            oms = line[13:93].strip()
            if atc_grp and (not rest) and oms:
                mapping[atc_grp] = oms
    return mapping

def pick_spk_atc(candidates):
    """
    Kies 1 kandidaat (SPKODE, ATCODE) uit een lijst (voorkeur: met ATCODE).
    """
    # unieks
    uniq = []
    seen = set()
    for spk, atc in candidates:
        key = (spk, atc)
        if key not in seen:
            seen.add(key)
            uniq.append((spk, atc))

    if not uniq:
        return None, None

    # 1) met ATC
    for spk, atc in uniq:
        if spk and len(spk) > 0 and atc:
            return spk, atc

    # 2) anders eerste met spk
    for spk, atc in uniq:
        if spk and len(spk) > 0:
            return spk, atc

    # 3) fallback
    return uniq[0]

def update_db_for_geneesmiddel(conn, geneesmiddel, spk, atc, atc3_to_omschrijving):
    """
    Werk ALLE rijen bij voor dit geneesmiddel (exacte naam, lowercased)
    Zet SPKode, ATCcode, ATC_groep, ATC_omschrijving.
    """
    atc_groep = atc[:3] if atc and len(atc) >= 3 else None
    atc_omschrijving = atc3_to_omschrijving.get(atc_groep) if atc_groep else None

    cur = conn.cursor()
    cur.execute("""
        UPDATE geneesmiddelen
        SET SPKode = ?, ATCcode = ?, ATC_groep = ?, ATC_omschrijving = ?
        WHERE geneesmiddel = ?
    """, (spk, atc, atc_groep, atc_omschrijving, clean_name(geneesmiddel)))
    conn.commit()
    return cur.rowcount

# ---------------------------
# Main logic
# ---------------------------

def main():
    # 1) Laad G-Standaard
    nmnaam_to_nmnr = load_bst020t(os.path.join(BST_PATH, "BST020T"))
    bst711 = load_bst711t(os.path.join(BST_PATH, "BST711T"))
    atc3_to_omschrijving = load_bst801t(os.path.join(BST_PATH, "BST801T"))

    # 2) Laad JSON mappings
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Ondersteun zowel { "mappings": [...] } als een pure lijst [...]
    mappings = data.get("mappings", data if isinstance(data, list) else [])

    if not mappings:
        print("Geen mappings gevonden in SPK_match.json")
        return

    # 3) Open DB
    conn = sqlite3.connect(DB_PATH)

    totaal_updates = 0

    for item in mappings:
        fk_geneesmiddel = item.get("fk_geneesmiddel")
        gpk_naam = item.get("gpk_naam")
        if not fk_geneesmiddel or not gpk_naam:
            print("⛔ Mapping overslaan (ontbrekende keys):", item)
            continue

        # 4) Vind NMNR via BST020T met gpk_naam
        gpk_key = clean_name(gpk_naam)
        nmnr = nmnaam_to_nmnr.get(gpk_key)

        if not nmnr:
            print(f"⚠️  NMNR niet gevonden voor gpk_naam='{gpk_naam}' (clean='{gpk_key}') — overslaan")
            continue

        # 5) Vind alle kandidaten in BST711T waar GPNMNR==nmnr of GPSTNR==nmnr
        candidates = []
        for row in bst711:
            if row["GPNMNR"] == nmnr or row["GPSTNR"] == nmnr:
                spk = row["SPKODE"]
                atc = row["ATCODE"]
                if spk:
                    candidates.append((spk, atc))

        if not candidates:
            print(f"⚠️  Geen SPKode-kandidaten gevonden in BST711T voor NMNR={nmnr} (gpk_naam='{gpk_naam}')")
            continue

        # 6) Kies 1 SPKODE (voorkeur: met ATC)
        spk, atc = pick_spk_atc(candidates)

        # 7) Update DB voor alle rijen met dit geneesmiddel
        rows = update_db_for_geneesmiddel(conn, fk_geneesmiddel, spk, atc, atc3_to_omschrijving)

        if rows > 0:
            totaal_updates += rows
            print(f"✅ Bijgewerkt: '{fk_geneesmiddel}' → SPKode={spk} ATC={atc} (rows: {rows})")
            # Optioneel: waarschuwing als er meerdere verschillende kandidaten bestonden
            if len(set(candidates)) > 1:
                uniq_spk = ", ".join(sorted({c[0] for c in candidates if c[0]}))
                print(f"   ℹ️  Meerdere SPKodes mogelijk gevonden ({uniq_spk}). Gekozen: {spk}")
        else:
            print(f"❌ Geen rijen geüpdatet voor geneesmiddel '{fk_geneesmiddel}' (niet gevonden in DB?)")

    conn.close()
    print(f"\nKlaar. Totaal geüpdatete rijen: {totaal_updates}")

if __name__ == "__main__":
    main()