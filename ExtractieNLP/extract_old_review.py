# -*- coding: utf-8 -*-
"""
Koppelt oude Word-discussies (Wie-blokken) aan Medimo per patiënt:
- Fuzzy patient matching (naam + geboortedatum)
- Fuzzy medicatie matching op KERNAAM (niet de hele regel)
- Alleen aliassen uit extern JSON-bestand (geen ingebouwde alias-map)
- Discussie: van middel-startregel t/m regel vóór volgende middel
- GFR/eGFR extractie
- Optioneel zins-splitsing met spaCy (fallback zonder spaCy)

Uitvoer (incl. debug): ExtractieNLP/nlp_koppeling_debug.json
"""

import os
import re
import json
import unicodedata
from typing import List, Dict, Optional, Tuple

# -------------------- PADEN --------------------
DOCX_PATH = "Data/argusvlinder november 2024.docx"
MEDIMO_PATH = "Data/medimo_input.txt"
ALIASES_JSON = "ExtractieNLP/aliases.json"    # <-- Voor geneesmiddel aliases
OUTPUT_JSON = "ExtractieNLP/nlp_koppeling_debug.json"

# -------------------- FUZZY BACKEND --------------------
_FUZZ_BACKEND = None
try:
    from rapidfuzz import fuzz as _rf_fuzz
    _FUZZ_BACKEND = "rapidfuzz"
except Exception:
    try:
        from fuzzywuzzy import fuzz as _fz_fuzz
        _FUZZ_BACKEND = "fuzzywuzzy"
    except Exception:
        _FUZZ_BACKEND = "difflib"
        from difflib import SequenceMatcher

def _ratio(a: str, b: str) -> int:
    if _FUZZ_BACKEND == "rapidfuzz":
        return int(_rf_fuzz.ratio(a, b))
    elif _FUZZ_BACKEND == "fuzzywuzzy":
        return int(_fz_fuzz.ratio(a, b))
    else:
        return int(SequenceMatcher(None, a, b).ratio() * 100)

def _partial_ratio(a: str, b: str) -> int:
    if _FUZZ_BACKEND == "rapidfuzz":
        return int(_rf_fuzz.partial_ratio(a, b))
    elif _FUZZ_BACKEND == "fuzzywuzzy":
        return int(_fz_fuzz.partial_ratio(a, b))
    else:
        # heel simpele fallback
        return _ratio(a, b)

def _token_sort_ratio(a: str, b: str) -> int:
    if _FUZZ_BACKEND == "rapidfuzz":
        return int(_rf_fuzz.token_sort_ratio(a, b))
    elif _FUZZ_BACKEND == "fuzzywuzzy":
        return int(_fz_fuzz.token_sort_ratio(a, b))
    else:
        sa = " ".join(sorted(a.split()))
        sb = " ".join(sorted(b.split()))
        return _ratio(sa, sb)

# -------------------- NLP (optioneel) --------------------
_NLP = None
try:
    import spacy
    try:
        _NLP = spacy.load("nl_core_news_sm")
    except Exception:
        _NLP = None
except Exception:
    _NLP = None

def nlp_sentences(text: str) -> List[str]:
    if not _NLP:
        parts = re.split(r"(?<=[\.\?!])\s+|\n", text)
        return [p.strip() for p in parts if p.strip()]
    doc = _NLP(text)
    return [s.text.strip() for s in doc.sents if s.text.strip()]

# -------------------- HULPFUNCTIES: normalisatie --------------------
def normalize_text_basic(s: str) -> str:
    s = s.lower()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
    s = re.sub(r"\s+", " ", s).strip()
    return s

TITLE_MAP = {
    "mw": "mevr", "mevr.": "mevr", "mevrouw": "mevr",
    "dhr": "dhr", "dhr.": "dhr", "hr": "dhr", "hr.": "dhr"
}

def normalize_title_and_name(name: str) -> str:
    name = normalize_text_basic(name)
    parts = name.split()
    if not parts:
        return name
    t = parts[0].strip(".")
    t_norm = TITLE_MAP.get(t, t)
    rest = " ".join(parts[1:])
    return f"{t_norm} {rest}".strip()

def strip_initials(name: str) -> str:
    # verwijder enkel-letter initialen & punten (bijv. "M." of "I")
    name = re.sub(r"\b[A-Z]\.?\b", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()

def normalize_dob(dob: str) -> str:
    dob = dob.strip().replace("/", "-")
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", dob)
    if m:
        dd, mm, yyyy = m.groups()
        return f"{yyyy}-{mm}-{dd}"
    return dob

def normalize_line_for_match(line: str) -> str:
    return normalize_text_basic(line)

# -------------------- ALIASES (enkel extern JSON) --------------------
def load_external_aliases(path: str) -> Dict[str, str]:
    """
    Laadt aliassen uit JSON: { "alias": "canonieke_naam", ... }
    Slechts dit bestand bepaalt aliassen; geen defaults in code.
    Keys en values worden genormaliseerd (lowercase, ascii-fication).
    """
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # normaliseer keys/values
                norm = {}
                for k, v in data.items():
                    norm[normalize_text_basic(k)] = normalize_text_basic(v)
                return norm
        else:
            print(f"ℹ️ Geen aliases.json gevonden op: {path} (script draait door zonder aliassen)")
    except Exception as e:
        print(f"⚠️ Kon aliases.json niet laden: {e}")
    return {}

def apply_aliases(text: str, alias_map: Dict[str, str]) -> str:
    """
    Vervang losse alias-termen (woordgrens) door canonieke vorm.
    Langste alias eerst om 'vit d' vóór 'vit' te vervangen.
    """
    s = normalize_text_basic(text)
    if not alias_map:
        return s
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        pat = rf"\b{re.escape(alias)}\b"
        s = re.sub(pat, alias_map[alias], s)
    return s

# -------------------- MEDIMO PARSING (zoals jouw main.py) --------------------
def extract_patient_blocks(filepath: str) -> List[str]:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    start = re.search(r"(Dhr\. |Mevr\. )", content)
    if not start:
        return []
    content = content[start.start():]
    raw_blocks = re.split(r'(?=Dhr\. |Mevr\. )', content)
    return [block.strip() for block in raw_blocks if block.strip().startswith(("Dhr.", "Mevr."))]

def clean_name(name: str) -> str:
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("\u200b", "")
    name = name.strip()
    return name

def parse_medimo_block(block: str) -> Dict:
    lines = block.strip().split("\n")
    # Eerste regel bevat naam + DOB: bijv. "Mevr. M Curie (07-11-1942)"
    header = lines[0].strip()
    m = re.match(r"^(Mevr\.|Dhr\.)\s+([^\(]+)\((\d{2}-\d{2}-\d{4})\)", header)
    if not m:
        m = re.search(r"(Mevr\.|Dhr\.)\s+([^\(]+)\((\d{2}-\d{2}-\d{4})\)", header)
    if m:
        naam = f"{m.group(1)} {m.group(2).strip()}"
        geboortedatum = m.group(3)
    else:
        naam = header
        geboortedatum = ""

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

    return {
        "naam": clean_name(naam),
        "geboortedatum": geboortedatum,
        "geneesmiddelen": geneesmiddelen
    }

def parse_medimo(filepath: str) -> List[Dict]:
    blocks = extract_patient_blocks(filepath)
    pats = [parse_medimo_block(b) for b in blocks]
    print(f"📦 Medimo: {len(pats)} patiëntblokken geladen")
    return pats

# -------------------- KERNAAM EXTRACTIE --------------------
FORM_WORDS = {
    "tablet","tabletten","capsule","caps","drank","pdr","poeder","gel","zalf","creme","crème",
    "aerosol","spray","inhalator","inhalatie","injsusp","injvlst","infuus",
    "kauwtablet","msr","filmomhuld","fo","edo","ellipta","flacon","fl","oogdruppels"
}
UNITS = {"mg","mcg","ug","µg","g","gram","ie","ml","%","ppm","mg/ml"}

def extract_drug_core(text: str, alias_map: Dict[str,str]) -> str:
    """
    Bepaal een 'kernnaam' (1-3 tokens) uit medimo-regel of vrije tekst,
    waarbij eerst aliasvervanging wordt toegepast (alleen extern JSON).
    """
    s = apply_aliases(text, alias_map)
    # split tokens (letters en slash-combo's blijven)
    tokens = re.findall(r"[a-zA-Z/]+|\d+[a-zA-Z%/]*", s)
    core_tokens = []
    for tok in tokens:
        t = tok.lower()
        if t.isdigit():
            break
        if t in UNITS or t in FORM_WORDS:
            continue
        if re.search(r"\d", t):
            break
        core_tokens.append(t)
        if len(core_tokens) >= 3:
            break
    if not core_tokens and tokens:
        core_tokens = [re.sub(r"[^a-z/]", "", tokens[0].lower())]
    core = " ".join([t for t in core_tokens if t])
    return core.strip()

# -------------------- WORD PARSER (Wie-blokken) --------------------
def parse_word_docx(docx_path: str) -> List[Dict]:
    from docx import Document
    doc = Document(docx_path)
    full_text = "\n".join([p.text for p in doc.paragraphs])

    # split op patiëntblokken beginnend met 'Wie'
    raw_blocks = re.split(r"\nWie\s+", full_text)
    patients = []
    for raw in raw_blocks[1:]:
        block = "Wie " + raw.strip()
        # naam + DOB zoeken met toleranties tabs/spaties
        m = re.search(r"^Wie\s+([^\t\n]+?)\s+(\d{2}-\d{2}-\d{4})", block, re.MULTILINE)
        naam, dob = None, None
        if m:
            naam, dob = m.group(1).strip(), m.group(2).strip()
        else:
            m2 = re.search(r"^Wie\s+([^\n]+?)\s+(\d{2}-\d{2}-\d{4})", block, re.MULTILINE)
            if m2:
                naam, dob = m2.group(1).strip(), m2.group(2).strip()

        gfr_m = re.search(r"(?:^|\n)\s*(e?gfr\s*[: ]\s*[^\n]+)", block, flags=re.IGNORECASE)
        gfr_text = gfr_m.group(1).strip() if gfr_m else None

        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if naam:
            patients.append({
                "naam": naam,
                "geboortedatum": dob,
                "gfr_text": gfr_text,
                "lines": lines
            })
            print(f"✅ Word-patiënt: {naam} ({dob}) | GFR: {gfr_text or '-'}")
        else:
            print("⚠️ Kon geen naam/geboortedatum vinden in een 'Wie'-blok.")
    print(f"📄 Word: {len(patients)} patiënten gevonden")
    return patients

# -------------------- PATIENT MATCHING --------------------
def match_patients(word_pats: List[Dict], medimo_pats: List[Dict], threshold: int = 80)\
        -> List[Tuple[Dict, Optional[Dict], int]]:
    matches = []
    for wp in word_pats:
        best, best_score = None, 0
        w_name = strip_initials(normalize_title_and_name(wp["naam"]))
        w_dob = normalize_dob(wp["geboortedatum"] or "") if wp.get("geboortedatum") else ""

        for mp in medimo_pats:
            m_name = strip_initials(normalize_title_and_name(mp["naam"]))
            m_dob = normalize_dob(mp.get("geboortedatum",""))

            name_score = _token_sort_ratio(w_name, m_name)
            dob_score = _ratio(w_dob, m_dob) if w_dob and m_dob else 0
            score = int((name_score + dob_score) / (2 if w_dob and m_dob else 1))
            if score > best_score:
                best, best_score = mp, score

        if best and best_score >= threshold:
            print(f"🤝 Match: {wp['naam']} ({wp['geboortedatum']}) ↔ {best['naam']} ({best.get('geboortedatum','')}) | score={best_score}")
            matches.append((wp, best, best_score))
        else:
            print(f"❌ Geen (goede) match voor: {wp['naam']} ({wp.get('geboortedatum','')}) | beste score={best_score}")
            matches.append((wp, None, best_score))
    return matches

# -------------------- MEDICATIE MATCHING + DISCUSSIE --------------------
def find_med_starts_for_patient(word_lines: List[str], medimo_meds: List[Dict], alias_map: Dict[str,str], min_score: int = 70)\
        -> List[Tuple[int, int, str, int]]:
    """
    Fuzzy partial match op KERNAAM (incl. aliasvervanging via extern JSON) om startregels in Word te vinden.
    Return: lijst (line_index, medimo_index, med_core, score), gesorteerd op line_index.
    """
    starts = []
    med_cores = [extract_drug_core(m["clean"], alias_map) for m in medimo_meds]
    for j, core in enumerate(med_cores):
        if not core:
            continue
        best_i, best_sc = None, 0
        for i, ln in enumerate(word_lines):
            norm_line = apply_aliases(ln, alias_map)
            sc = _partial_ratio(core, normalize_line_for_match(norm_line))
            if sc > best_sc:
                best_i, best_sc = i, sc
        if best_i is not None and best_sc >= min_score:
            starts.append((best_i, j, core, best_sc))
    # Conflicten oplossen: per regel één middel (hoogste score)
    starts.sort(key=lambda x: (x[0], -x[3]))
    dedup, used = [], set()
    for s in starts:
        if s[0] in used:
            continue
        used.add(s[0])
        dedup.append(s)
    return sorted(dedup, key=lambda x: x[0])

def chunk_by_starts(lines: List[str], starts: List[Tuple[int,int,str,int]]) -> List[Tuple[int,int]]:
    if not starts:
        return []
    idxs = [s[0] for s in starts]
    chunks = []
    for k, start in enumerate(idxs):
        end = idxs[k+1] if k+1 < len(idxs) else len(lines)
        chunks.append((start, end))
    return chunks

# -------------------- PIPELINE --------------------
def run_pipeline(docx_path: str, medimo_path: str, out_json: str) -> str:
    os.makedirs(os.path.dirname(out_json), exist_ok=True)

    alias_map = load_external_aliases(ALIASES_JSON)  # <-- alleen extern JSON
    print(f"🔤 Aliases geladen: {len(alias_map)} (bron: {ALIASES_JSON})")

    medimo_pats = parse_medimo(medimo_path)
    word_pats = parse_word_docx(docx_path)

    matched = match_patients(word_pats, medimo_pats, threshold=80)

    result = []
    for wp, mp, score in matched:
        medimo_meds = mp["geneesmiddelen"] if mp else []
        starts = find_med_starts_for_patient(wp["lines"], medimo_meds, alias_map, min_score=70)
        chunks = chunk_by_starts(wp["lines"], starts)

        discussions = []
        for (start_i, end_i), start_meta in zip(chunks, starts):
            line_idx, medimo_idx, med_core, match_sc = start_meta
            lines_block = wp["lines"][start_i:end_i]
            block_text = "\n".join(lines_block).strip()
            sentences = nlp_sentences(block_text)
            med_raw = medimo_meds[medimo_idx] if medimo_meds else None

            discussions.append({
                "start_line_index": line_idx,
                "docx_first_line": wp["lines"][line_idx],
                "docx_lines": lines_block,
                "block_text": block_text,
                "sentences": sentences,
                "match_core": med_core,
                "match_score": match_sc,
                "medimo_middel": med_raw  # {origineel, clean, gebruik, opmerking}
            })

        result.append({
            "patient_word": {
                "naam": wp["naam"],
                "geboortedatum": wp.get("geboortedatum",""),
                "gfr_text": wp.get("gfr_text")
            },
            "patient_medimo": ({"naam": mp["naam"], "geboortedatum": mp.get("geboortedatum","")} if mp else None),
            "patient_match_score": score,
            "discussions": discussions
        })

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Klaar. Uitvoer: {out_json} | Word-patiënten: {len(word_pats)} | Records: {len(result)}")
    return out_json

# -------------------- MAIN --------------------
if __name__ == "__main__":
    run_pipeline(DOCX_PATH, MEDIMO_PATH, OUTPUT_JSON)