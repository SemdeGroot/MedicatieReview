# query_atc_group.py
# --------------------------------------------
# Zoek ATC-groep(en) in ATC_groepen.db.
# - Exacte lookup; zo niet gevonden, dan fallback op langste prefix (5→4→3).
# - Werkt voor een enkele code via CLI-argument of interactieve prompt.
#
# Voorbeelden:
#   python query_atc_group.py C07AB02
#   python query_atc_group.py N02BE
#   python query_atc_group.py C07
#
# Database schema:
#   ATC_groepen(ATC_groep TEXT UNIQUE,
#               ATC_omschrijving TEXT,
#               Jansen_omschrijving TEXT)

import sys
import re
import sqlite3
from typing import Optional, Tuple

DB_PATH = "ATC_groepen.db"

def clean_code(code: str) -> str:
    """Normaliseer invoer: hoofdletters, verwijder spaties/slashes/puntjes/underscore."""
    if not code:
        return ""
    code = code.strip().upper()
    code = re.sub(r"[ \t\./_]+", "", code)
    return code

def fetch_row(conn, code: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """Haal één rij op voor exacte ATC_groep (= code)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT ATC_groep, ATC_omschrijving, IFNULL(Jansen_omschrijving,'') "
        "FROM ATC_groepen WHERE ATC_groep = ?",
        (code,)
    )
    row = cur.fetchone()
    return row if row else None

def best_match(conn, code: str) -> Tuple[Optional[Tuple[str,str,str]], str]:
    """
    Zoek beste match:
      1) exact
      2) prefix(len=5), prefix(len=4), prefix(len=3)
    Retourneert (row, methode) waarbij row = (ATC_groep, ATC_omschrijving, Jansen_omschrijving|''), 
    methode is 'exact' of 'prefix-lenX' of 'none'.
    """
    code = clean_code(code)
    if not code:
        return None, "none"

    # 1) exact
    row = fetch_row(conn, code)
    if row:
        return row, "exact"

    # 2) langste prefix naar 3
    for L in range(min(len(code), 5), 2, -1):  # 5,4,3
        pref = code[:L]
        row = fetch_row(conn, pref)
        if row:
            return row, f"prefix-len{L}"

    return None, "none"

def main():
    # code ophalen
    if len(sys.argv) >= 2:
        code = sys.argv[1]
    else:
        try:
            code = input("Voer een ATC-code in (bv. C07AB02 of C07): ").strip()
        except KeyboardInterrupt:
            print("\nAfgebroken.")
            return

    code = clean_code(code)
    if not code:
        print("Geen geldige code opgegeven.")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
    except sqlite3.Error as e:
        print(f"Kan database niet openen: {e}")
        return

    row, method = best_match(conn, code)
    conn.close()

    if not row:
        print(f"Geen ATC-groep gevonden voor '{code}'. (geprobeerd: exact, 5/4/3-prefix)")
        return

    atc_groep, atc_omschrijving, jansen_omschrijving = row

    print("— ATC lookup —")
    print(f"Invoer        : {code}")
    print(f"Match-methode : {method}")
    print(f"ATC_groep     : {atc_groep}")
    print(f"Omschrijving  : {atc_omschrijving if atc_omschrijving else '-'}")
    print(f"Jansen        : {jansen_omschrijving if jansen_omschrijving else '-'}")

if __name__ == "__main__":
    main()
