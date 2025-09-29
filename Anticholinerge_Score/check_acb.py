import json
from typing import Iterable, Tuple, List, Dict, Union

Geneesmiddel = Dict[str, Union[str, None]]
ACBResult = Tuple[int, str, List[Dict[str, Union[str, int]]]]

def bereken_acb_score(
    middelen: Iterable[Union[Geneesmiddel, str]],
    json_path: str = "Anticholinerge_Score/acb.json"
) -> ACBResult:
    """
    Berekent de ACB-score o.b.v. ATC7 (exacte match, geen prefix).
    
    Input:
      - middelen: iterable met óf geneesmiddel-dicts (zoals je 'middelen_clean' items
                  met velden 'clean', 'ATC7', 'ATC'), óf strings met ATC-codes.
      - json_path: pad naar ACB JSON met 'scores': {"1":[ATC7...], "2":[ATC7...], "3":[ATC7...]}

    Output:
      - (totaalscore, interpretatie, bijdragen)
        bijdragen = [{"middel": <naam of ATC7>, "atc7": <ATC7>, "score": 1|2|3}, ...]
    """
    # --- JSON laden ---
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            acb_data = json.load(f)
    except Exception as e:
        return 0, f"ACB kon niet berekend worden (config niet leesbaar: {e}).", []

    scores_map = acb_data.get("scores") or {}

    # Bouw mapping: ATC7 -> score (int)
    code2score: Dict[str, int] = {}
    for level_str, codes in scores_map.items():
        try:
            lvl = int(level_str)
        except Exception:
            continue
        for c in (codes or []):
            code = (c or "").strip().upper()
            if code:
                code2score[code] = lvl

    # Helpers
    def extract_atc7_and_name(item: Union[Geneesmiddel, str]) -> Tuple[str, str]:
        """
        Retourneert (ATC7, naamvoorbijdrage)
        - ATC7: exact 7 tekens indien beschikbaar; anders lege string.
        - naamvoorbijdrage: 'clean' indien aanwezig, anders ATC7/ATC.
        """
        if isinstance(item, dict):
            atc7 = (item.get("ATC7") or "").strip().upper()
            if not atc7:
                atc_raw = (item.get("ATC") or "").strip().upper()
                atc7 = atc_raw[:7] if len(atc_raw) >= 7 else ""
            naam = (item.get("clean") or "").strip()
            if not naam:
                naam = atc7 or (item.get("ATC") or "").strip().upper() or "Onbekend middel"
            return atc7, naam
        else:
            s = (item or "").strip().upper()
            atc7 = s[:7] if len(s) >= 7 else ""
            return atc7, (atc7 or s or "Onbekend middel")

    # Itereer middelen en tel unieke ATC7's
    totaal = 0
    bijdragen: List[Dict[str, Union[str, int]]] = []
    gezien: set[str] = set()

    for it in middelen:
        atc7, naam = extract_atc7_and_name(it)
        if not atc7 or len(atc7) != 7:
            continue  # alleen exacte ATC7 meenemen
        if atc7 in gezien:
            continue  # niet dubbel tellen
        score = code2score.get(atc7, 0)
        if score:
            totaal += score
            bijdragen.append({"middel": naam, "atc7": atc7, "score": score})
            gezien.add(atc7)

    # Interpretatie
    if totaal == 0:
        interpretatie = "Geen anticholinerge belasting (score = 0)."
    elif totaal == 1:
        interpretatie = "Lichte anticholinerge belasting (score = 1)."
    elif totaal == 2:
        interpretatie = "Matige anticholinerge belasting (score = 2)."
    else:
        interpretatie = "Hoge anticholinerge belasting (score ≥ 3)."

    return totaal, interpretatie, bijdragen