# medimo_parser_atc3.py
# -------------------------------------------------
# Parseert Medimo-export en koppelt per geneesmiddel:
# - NMNR (BST020T) op basis van naam
# - SPKode via 3/4 routes (BST711 direct, via PR, via HP, via HPNAMN)
# - ATC-code via BST711 (kolom 118:126) o.b.v. SPKode
# - ATC3/4/5/7 codes + omschrijvingen:
#     * ATC3: omschrijving + Jansen-omschrijving uit ATC_groepen.db
#     * ATC4/5/7: NL-omschrijving direct uit BST801T (géén DB)
#
# Geen gebruik van 'geneesmiddelen.db'.

import os
import re
import sqlite3
import unicodedata
import json
from collections import Counter
import glob, threading, time
from datetime import datetime

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
def _attempt_resolve_sp(nmnr, bst052, bst004, bst070, bst711, bst031, debug=False):
    """
    Alle routes NMNR → SPKode. Retourneert (nmnr, hpkode, spkode) of None.
    Stop direct bij de eerste SPKode-hit (short-circuit).

    Routes:
      (1) 711-direct:    GPNMNR/GPSTNR → SPKODE
      (2) PR→GP→SP:      PRNMNR (BST052) → GPKODE → SPKODE (BST711)
      (3) ATNMNR→HP→GP→SP: ATNMNR (BST004) → HPKODE → GPKODE (BST070) → SPKODE (BST711)
      (4) HPNAMN→HP→GP→SP: HPNAMN (BST031) → HPKODE → GPKODE (BST070) → SPKODE (BST711)
    """
    if not nmnr:
        if debug:
            print("    [_attempt] nmnr=None → stop")
        return None

    # (1) Direct via BST711T
    for row in bst711:
        if row["SPKODE"] and (row["GPSTNR"] == nmnr or row["GPNMNR"] == nmnr):
            if debug:
                print(f"    [_attempt] hit 711-direct → SP={row['SPKODE']}")
            return nmnr, None, row["SPKODE"]

    # (2) Via PR → GP → SP
    for row in bst052:
        if row["PRNMNR"] == nmnr:
            gpkode = row["GPKODE"]
            for rij in bst711:
                if rij["SPKODE"] and (rij["GPKODE"] == gpkode or rij["GSKODE"] == gpkode):
                    if debug:
                        print(f"    [_attempt] hit PR→GP→SP (GP={gpkode}) → SP={rij['SPKODE']}")
                    return nmnr, None, rij["SPKODE"]

    # (3) Via ATNMNR→HP→GP→SP (BST004 → BST070 → BST711)
    for r in bst004:
        if r["ATNMNR"] == nmnr:
            hpkode = r["HPKODE"]
            for row in bst070:
                if row["HPKODE"] == hpkode:
                    gpkode = row["GPKODE"]
                    for rij in bst711:
                        if rij["SPKODE"] and (rij["GPKODE"] == gpkode or rij["GSKODE"] == gpkode):
                            if debug:
                                print(f"    [_attempt] hit ATNMNR→HP→GP→SP (HP={hpkode}, GP={gpkode}) → SP={rij['SPKODE']}")
                            return nmnr, hpkode, rij["SPKODE"]

    # (4) Via HPNAMN→HP→GP→SP (BST031 → BST070 → BST711)
    for r in bst031:
        if r["HPNAMN"] == nmnr:
            hpkode = r["HPKODE"]
            for row in bst070:
                if row["HPKODE"] == hpkode:
                    gpkode = row["GPKODE"]
                    for rij in bst711:
                        if rij["SPKODE"] and (rij["GPKODE"] == gpkode or rij["GSKODE"] == gpkode):
                            if debug:
                                print(f"    [_attempt] hit HPNAMN→HP→GP→SP (HP={hpkode}, GP={gpkode}) → SP={rij['SPKODE']}")
                            return nmnr, hpkode, rij["SPKODE"]

    if debug:
        print("    [_attempt] geen SPKODE via routes gevonden.")
    return None

def match_to_spkode(gm_clean, bst020, bst052, bst004, bst070, bst711, bst031, debug=False):
    """
    SPKode is primair. Stop direct bij eerste SPKode (short-circuit).
    - Volledige naam → NMNR → routes
    - Prefixen (N-1 → 1 woord):
        * NMNR → routes
        * Als geen SP: prefix-scan in BST020 met woordgrens (spatie/-/_///einde),
          probeer per hit direct routes en stop bij eerste SP.
    """
    full_clean = clean_name(gm_clean)
    if not full_clean:
        if debug:
            print("[match] gm_clean leeg na clean_name()")
        return None, None, None

    tokens = full_clean.split()
    n = len(tokens)

    def dbg(*args):
        if debug:
            print(*args)

    def _norm(s: str) -> str:
        return clean_name(s).lower()

    # 0) Volledige naam
    nmnr_full = exact_nmnr_match(full_clean, bst020)
    dbg(f"[match full] cand='{full_clean}' → NMNR={nmnr_full}")
    if nmnr_full:
        res_full = _attempt_resolve_sp(nmnr_full, bst052, bst004, bst070, bst711, bst031, debug=debug)
        dbg(f"[match full] SP={res_full[2] if res_full else None}")
        if res_full:
            return res_full

    # 1) Prefixen: N-1 → 1 woord (telkens laatste woord eraf)
    for k in range(n - 1, 0, -1):
        candidate = " ".join(tokens[:k])
        cand_norm = _norm(candidate)

        # 1a) Eerst: exacte NMNR op de prefix
        nmnr_k = exact_nmnr_match(candidate, bst020)
        dbg(f"[match k={k}] cand='{candidate}' → NMNR={nmnr_k}")
        if nmnr_k:
            res_k = _attempt_resolve_sp(nmnr_k, bst052, bst004, bst070, bst711, bst031, debug=debug)
            dbg(f"[match k={k}] SP={res_k[2] if res_k else None}")
            if res_k:
                return res_k

        # 1b) Dan: prefix-scan met woordgrens/scheidingsteken, en STOP bij eerste SP
        boundary_pat = re.compile(r'^' + re.escape(cand_norm) + r'(?:\b|[ \-/_]|$)')
        hits = 0
        for row in bst020:
            nmnaam_norm = _norm(row["NMNAAM"])
            if boundary_pat.match(nmnaam_norm):
                hits += 1
                nmnr_pref = row["NMNR"]
                res_pref = _attempt_resolve_sp(nmnr_pref, bst052, bst004, bst070, bst711, bst031, debug=debug)
                dbg(f"[match k={k}]   try '{row['NMNAAM']}' → SP={res_pref[2] if res_pref else None}")
                if res_pref:
                    return res_pref
        if debug:
            dbg(f"[match k={k}] prefix-scan hits (wb): {hits}")

    dbg("[match] geen SPKode gevonden na alle prefixes + prefix-scan.")
    return None, None, None

# -----------------------------
# SPKode → ATC (BST711 kolom 118:126)
# -----------------------------
def build_spkode_to_atc_map(bst711):
    """
    Bouw dict: SPKode -> ATC_code (volledige string uit kolommen 118:126).

    Werkwijze:
    1) Verzamel ALLE ATC-codes per SPKode uit BST711.
    2) Kies de meest voorkomende ATC-code per SPKode (zonder remap).
    3) Remap daarna ALLEEN die gekozen code als die exact voorkomt in ATC_preferent.json.

    JSON (lijst van items) in Parsers/ATC_preferent.json:
    [
      {
        "geneesmiddel": "triamcinolon",         # optioneel
        "ATC_preferent": "D07AB09",
        "ATC_mogelijk": ["S02BA", "R01AD11"]    # exact te remappen codes (alle lengtes toegestaan)
      }
    ]
    """
    # --- 1) Lees preferentie-json en bouw exact-remap dict ---
    remap_exact = {}
    pref_path = os.path.join(os.getcwd(), "Parsers", "ATC_preferent.json")
    if os.path.exists(pref_path):
        try:
            with open(pref_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    prefer = (item.get("ATC_preferent") or "").strip().upper()
                    mogelijk_list = item.get("ATC_mogelijk") or []
                    if prefer and isinstance(mogelijk_list, list):
                        for m in mogelijk_list:
                            k = (m or "").strip().upper()
                            if k:
                                remap_exact[k] = prefer
        except Exception as e:
            print(f"Fout bij inlezen ATC_preferent.json: {e}")

    # --- 2) Verzamel alle ATC-codes per SPKode ---
    spkode_to_all_atcs = {}
    for row in bst711:
        spk = (row.get("SPKODE") or "").strip()
        atc = (row.get("ATC") or "").strip().upper()
        if not spk or not atc:
            continue
        spkode_to_all_atcs.setdefault(spk, []).append(atc)

    # --- 3) Kies meest voorkomende ATC en remap exact indien nodig ---
    mapping = {}
    for spk, atc_list in spkode_to_all_atcs.items():
        # meest voorkomende ATC (Counter behoudt bij gelijke frequentie volgorde van voorkomen)
        gekozen_atc = Counter(atc_list).most_common(1)[0][0]
        # pas daarna exact remap toe (alleen als gekozen_atc exact in remap_exact zit)
        atc_final = remap_exact.get(gekozen_atc, gekozen_atc)
        mapping[spk] = atc_final

    return mapping

def atc_levels(atc_code):
    """
    Geef ATC niveaus (3/4/5/7) als tuple (atc3, atc4, atc5, atc7).
    """
    if not atc_code:
        return None, None, None, None
    atc_code = atc_code.strip().upper()
    atc3 = atc_code[:3] if len(atc_code) >= 3 else None
    atc4 = atc_code[:4] if len(atc_code) >= 4 else None
    atc5 = atc_code[:5] if len(atc_code) >= 5 else None
    atc7 = atc_code[:7] if len(atc_code) >= 7 else None
    return atc3, atc4, atc5, atc7

# -----------------------------
# BST801T: ATC-code → NL-omschrijving (direct, geen DB)
# -----------------------------
def load_bst801_map(bst801_path):
    """
    Laadt BST801T naar dict: code → NL-omschrijving.
    ATCODE (006-013) → line[5:13], ATOMS (014-093) → line[13:93].
    Probeert UTF-8, valt terug op Latin-1.
    """
    mapping = {}
    for enc in ('utf-8', 'latin-1'):
        try:
            with open(bst801_path, 'r', encoding=enc) as f:
                for line in f:
                    atc_code = line[5:13].strip()
                    nl_desc  = line[13:93].strip()
                    if atc_code:
                        mapping[atc_code] = nl_desc
            break
        except UnicodeDecodeError:
            continue
    return mapping

# -----------------------------
# ATC_groepen.db lookup (ATC3 → +Jansen)
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
    bst031_path = os.path.join(dir_path, "BST031T")
    bst801_path = os.path.join(dir_path, "BST801T")
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
    bst031_cols = [
        ("HPKODE", 5, 13),
        ("PRKODE", 13, 21),
        ("MHKODE", 21, 29),
        ("HPNAMN", 29, 36),
    ]

    # Inlezen G-Standaard
    bst020 = load_fixed_width_file(bst020_path, bst020_cols)
    bst004 = load_fixed_width_file(bst004_path, bst004_cols)
    bst052 = load_fixed_width_file(bst052_path, bst052_cols)
    bst070 = load_fixed_width_file(bst070_path, bst070_cols)
    bst711 = load_fixed_width_file(bst711_path, bst711_cols)
    bst031 = load_fixed_width_file(bst031_path, bst031_cols)

    # BST801: code → NL-omschrijving (voor ATC4/5/7 en ook ATC3 fallback)
    atc_desc_map = load_bst801_map(bst801_path)

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
                gm["clean"], bst020, bst052, bst004, bst070, bst711, bst031, debug=False
            )

            atc_code = spkode_to_atc.get(spkode)
            atc3, atc4, atc5, atc7 = atc_levels(atc_code)

            # Omschrijvingen:
            # - ATC3: omschrijving + Jansen uit DB
            atc3_key, atc3_omschrijving, atc3_jansen = lookup_atc3_info(atc3)
            # - ATC4/5/7: NL-omschrijving direct uit BST801
            atc4_oms = atc_desc_map.get(atc4) if atc4 else None
            atc5_oms = atc_desc_map.get(atc5) if atc5 else None
            atc7_oms = atc_desc_map.get(atc7) if atc7 else None

            status = "✅" if spkode and atc3_key else "❌"
            print(f"  {status} {gm['clean']}")
            print(f"    → NMNR: {nmnr}, HPKODE: {hpkode}, SPKode: {spkode}")
            print(f"    → ATC: {atc_code}  | ATC3: {atc3} | ATC4: {atc4} | ATC5: {atc5} | ATC7: {atc7}")
            print(f"    → ATC3 DB: {atc3_key} | Omschr: {atc3_omschrijving} | Jansen: {atc3_jansen}")
            print(f"    → ATC4 omschr: {atc4_oms}")
            print(f"    → ATC5 omschr: {atc5_oms}")
            print(f"    → ATC7 omschr: {atc7_oms}")
            print(f"    → Gebruik: {gm['gebruik']} | Opmerking: {gm['opmerking']}\n")

def run_parser(
    input_path: str,
    progress_path: str,
    cancel_flag_path: str,
):
    """
    Parseert Medimo input en verrijkt middelen met SPKode/ATC etc.

    Retourneert:
      - resultaat: list[ { "patiënt": str, "geneesmiddelen": list[dict] } ]
      - afdeling: str

    Schrijft live voortgang naar `progress_path` (in *dezelfde run_id map*),
    en verwijdert `progress_path` bij 'done' of 'aborted'. Cancel checkt
    het per-run `cancel_flag_path`.
    """

    def write_progress(done: int, total: int, afdeling: str, status: str = "running"):
        pct = 0 if total == 0 else int(done * 100 / total)
        payload = {
            "afdeling": afdeling,
            "status": status,  # "running" | "done" | "aborted"
            "n_medicijnen_input": total,
            "n_medicijnen_geanalyseerd": done,
            "pct_geanalyseerd": pct,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        os.makedirs(os.path.dirname(progress_path) or ".", exist_ok=True)
        tmp = f"{progress_path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        # atomische replace met zachte retry (Windows locks)
        for _ in range(10):
            try:
                os.replace(tmp, progress_path)
                break
            except PermissionError:
                time.sleep(0.05)

    def _is_cancelled() -> bool:
        try:
            return os.path.exists(cancel_flag_path)
        except Exception:
            return False

    # ---- inlezen tabellen / mapping (zoals je al deed) ----
    dir_path = "G-Standaard"
    bst020_path = os.path.join(dir_path, "BST020T")
    bst004_path = os.path.join(dir_path, "BST004T")
    bst052_path = os.path.join(dir_path, "BST052T")
    bst070_path = os.path.join(dir_path, "BST070T")
    bst711_path = os.path.join(dir_path, "BST711T")
    bst031_path = os.path.join(dir_path, "BST031T")
    bst801_path = os.path.join(dir_path, "BST801T")

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
    bst031_cols = [
        ("HPKODE", 5, 13),
        ("PRKODE", 13, 21),
        ("MHKODE", 21, 29),
        ("HPNAMN", 29, 36),
    ]

    bst020 = load_fixed_width_file(bst020_path, bst020_cols)
    bst004 = load_fixed_width_file(bst004_path, bst004_cols)
    bst052 = load_fixed_width_file(bst052_path, bst052_cols)
    bst070 = load_fixed_width_file(bst070_path, bst070_cols)
    bst711 = load_fixed_width_file(bst711_path, bst711_cols)
    bst031 = load_fixed_width_file(bst031_path, bst031_cols)

    atc_desc_map = load_bst801_map(bst801_path)
    spkode_to_atc = build_spkode_to_atc_map(bst711)

    # --- lees input uit het meegegeven pad ---
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Afdeling uit tekst
    m = re.search(r"Een overzicht van alle actieve medicatie in afdeling (.+?)\.", content)
    afdeling = m.group(1).strip() if m else "Onbekend"

    # Blokken + totalen
    patient_blocks = extract_patient_blocks(input_path)
    parsed = []
    total_input = 0
    for block in patient_blocks:
        gm_list = parse_medimo_block(block)
        parsed.append((block, gm_list))
        total_input += len(gm_list)

    # Start progress
    done = 0
    write_progress(done, total_input, afdeling, "running")
    resultaat = []

    try:
        for block, gm_list in parsed:
            if _is_cancelled():
                raise KeyboardInterrupt("Cancelled")

            patient_name = block.split("\n")[0].strip()

            for gm in gm_list:
                if _is_cancelled():
                    raise KeyboardInterrupt("Cancelled")

                nmnr, hpkode, spkode = match_to_spkode(
                    gm["clean"], bst020, bst052, bst004, bst070, bst711, bst031, debug=False
                )
                atc_code = spkode_to_atc.get(spkode)
                atc3, atc4, atc5, atc7 = atc_levels(atc_code)

                atc3_key, atc3_omschrijving, atc3_jansen = lookup_atc3_info(atc3)
                atc4_oms = atc_desc_map.get(atc4) if atc4 else None
                atc5_oms = atc_desc_map.get(atc5) if atc5 else None
                atc7_oms = atc_desc_map.get(atc7) if atc7 else None

                gm["NMNR"] = nmnr
                gm["HPKode"] = hpkode
                gm["SPKode"] = spkode
                gm["ATC"] = atc_code

                gm["ATC3"] = atc3
                gm["ATC3_key"] = atc3_key
                gm["ATC3_omschrijving"] = atc3_omschrijving
                gm["ATC3_jansen"] = atc3_jansen

                gm["ATC4"] = atc4
                gm["ATC4_omschrijving"] = atc4_oms

                gm["ATC5"] = atc5
                gm["ATC5_omschrijving"] = atc5_oms

                gm["ATC7"] = atc7
                gm["ATC7_omschrijving"] = atc7_oms

                done += 1
                write_progress(done, total_input, afdeling, "running")

            resultaat.append({
                "patiënt": patient_name,
                "geneesmiddelen": gm_list
            })

        write_progress(done, total_input, afdeling, "done")
        # heel even laten staan zodat de UI 'done' ziet
        time.sleep(0.8)

    except KeyboardInterrupt:
        write_progress(done, total_input, afdeling, "aborted")

    # Cleanup: progress + eventuele tmp/bak weg (per-run map blijft verder intact)
    try:
        if os.path.exists(progress_path):
            os.remove(progress_path)
        for p in glob.glob(progress_path + "*"):
            try:
                os.remove(p)
            except:
                pass
    except Exception:
        pass

    return resultaat, afdeling

if __name__ == "__main__":
    main()