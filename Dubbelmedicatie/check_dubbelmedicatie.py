# Dubbelmedicatie/check_dubbelmedicatie.py
from collections import defaultdict

def _uniq_sorted(names):
    return sorted(set(n for n in names if n), key=lambda x: x.lower())

def check_dubbelmedicatie(geneesmiddelen):
    """
    Detecteer dubbelmedicatie:
      - ATC5: 'echte' dubbelmedicatie (≥2 in exact dezelfde ATC5-code)
      - ATC4: '(pseudo) dubbelmedicatie' (≥2 in dezelfde ATC4-code),
              maar alleen als er geen ATC5-dubbel onder valt (ruisonderdrukking).

    Input: list[dict] met o.a. per middel:
      - "clean": str
      - "ATC4": str | None
      - "ATC4_omschrijving": str | None
      - "ATC5": str | None
      - "ATC5_omschrijving": str | None

    Output: list[dict] met items:
      {
        "groep": "[ATC5] C07AB - Selectieve beta-blokkers"    # of "[ATC4] C07A - ... (pseudo)"
        "middelen": ["metoprolol", "atenolol"]
      }
    """
    if not geneesmiddelen:
        return []

    # Verzamel per ATC5 en ATC4
    per_atc5 = defaultdict(lambda: {"desc": None, "names": []})
    per_atc4 = defaultdict(lambda: {"desc": None, "names": []})

    for gm in geneesmiddelen:
        naam = gm.get("clean") or "Onbekend middel"

        atc5 = gm.get("ATC5")
        if atc5:
            if not per_atc5[atc5]["desc"]:
                per_atc5[atc5]["desc"] = gm.get("ATC5_omschrijving")
            per_atc5[atc5]["names"].append(naam)

        atc4 = gm.get("ATC4")
        if atc4:
            if not per_atc4[atc4]["desc"]:
                per_atc4[atc4]["desc"] = gm.get("ATC4_omschrijving")
            per_atc4[atc4]["names"].append(naam)

    resultaten = []

    # 1) Echte dubbelmedicatie (ATC5)
    atc4_with_real = set()  # ATC4-prefixen waarvoor al een ATC5-dubbel is gevonden
    for atc5, data in per_atc5.items():
        namen = _uniq_sorted(data["names"])
        if len(namen) >= 2:
            desc = data["desc"] or ""
            label = f"{atc5} - {desc}".strip().rstrip(" -")
            resultaten.append({
                "groep": label,
                "middelen": namen
            })
            # markeer ATC4-prefix voor ruisonderdrukking bij pseudo
            if len(atc5) >= 4:
                atc4_with_real.add(atc5[:4])

    # 2) (Pseudo) dubbelmedicatie (ATC4) — alleen als er geen ATC5-dubbel onder valt
    for atc4, data in per_atc4.items():
        if atc4 in atc4_with_real:
            continue  # er bestaat al een striktere ATC5-dubbel binnen deze ATC4
        namen = _uniq_sorted(data["names"])
        if len(namen) >= 2:
            desc = data["desc"] or ""
            label = f"{atc4} - {desc} (pseudo)".strip().rstrip(" -")
            resultaten.append({
                "groep": label,
                "middelen": namen
            })

    # Sorteer: eerst ATC5 meldingen, dan ATC4 pseudo's, alfabetisch binnen elk blok
    def sort_key(item):
        g = item["groep"] or ""
        # forceer volgorde: ATC5 eerst
        rank = 0 if g.startswith("[ATC5]") else 1
        return (rank, g.lower())

    resultaten.sort(key=sort_key)
    return resultaten
