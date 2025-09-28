# Dubbelmedicatie/check_dubbelmedicatie.py
from collections import defaultdict

def _uniq_sorted(names):
    # Unieke namen, netjes alfabetisch (case-insensitive sort, originele case behouden)
    return sorted({n for n in names if n}, key=lambda x: x.lower())

def check_dubbelmedicatie(geneesmiddelen):
    """
    Detecteer dubbelmedicatie:
      - ATC5: 'echte' dubbelmedicatie (≥2 in exact dezelfde ATC5-code)
      - Géén pseudo (ATC4) meer.

    Input: list[dict] met o.a. per middel:
      - "clean": str
      - "ATC5": str | None
      - "ATC5_omschrijving": str | None

    Output: list[dict] met items:
      {
        "groep": "[ATC5] C07AB - Selectieve beta-blokkers",
        "middelen": ["metoprolol", "atenolol"]
      }
    """
    if not geneesmiddelen:
        return []

    # Verzamel per ATC5
    per_atc5 = defaultdict(lambda: {"desc": None, "names": []})

    for gm in geneesmiddelen:
        naam = gm.get("clean") or "Onbekend middel"
        atc5 = gm.get("ATC5")
        if atc5:
            if not per_atc5[atc5]["desc"]:
                per_atc5[atc5]["desc"] = gm.get("ATC5_omschrijving")
            per_atc5[atc5]["names"].append(naam)

    resultaten = []

    # Echte dubbelmedicatie (ATC5)
    for atc5, data in per_atc5.items():
        namen = _uniq_sorted(data["names"])
        if len(namen) >= 2:
            desc = (data["desc"] or "").strip()
            label = f"[ATC5] {atc5}" + (f" - {desc}" if desc else "")
            resultaten.append({
                "groep": label,
                "middelen": namen
            })

    # Sorteer alfabetisch op groep
    resultaten.sort(key=lambda item: (item.get("groep") or "").lower())
    return resultaten