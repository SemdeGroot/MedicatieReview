# Dubbelmedicatie/check_dubbelmedicatie.py
from collections import defaultdict

def check_dubbelmedicatie(geneesmiddelen):
    """
    Detecteer dubbelmedicatie o.b.v. ATC3-groepen.
    Input:
        geneesmiddelen: list[dict] met o.a. velden:
            - "clean": str
            - "ATC3": str | None     (of "ATC3_key" als fallback)
            - "ATC3_omschrijving": str | None
    Output:
        list[dict] met items zoals:
            {
              "groep": "C07 - Beta-blokkerende middelen",  # ATC3 + omschrijving (samengevoegd)
              "middelen": ["metoprolol", "atenolol"]
            }
        Alleen groepen met ≥ 2 middelen worden geretourneerd.
    """
    if not geneesmiddelen:
        return []

    # verzamel per ATC3-code
    per_atc3 = defaultdict(lambda: {"desc": None, "names": []})

    for gm in geneesmiddelen:
        atc3 = gm.get("ATC3") or gm.get("ATC3_key")
        if not atc3:
            continue

        naam = gm.get("clean") or "Onbekend middel"
        desc = gm.get("ATC3_omschrijving")  # kan None zijn

        # bewaar eerste niet-lege omschrijving die we tegenkomen
        if desc and not per_atc3[atc3]["desc"]:
            per_atc3[atc3]["desc"] = desc

        per_atc3[atc3]["names"].append(naam)

    resultaten = []
    for atc3, data in per_atc3.items():
        unieke_namen = sorted(set(data["names"]), key=lambda x: x.lower())
        if len(unieke_namen) >= 2:
            omschrijving = data["desc"]
            groep_label = f"{atc3} - {omschrijving}" if (atc3 and omschrijving) else (atc3 or omschrijving or "Onbekend")
            resultaten.append({
                "groep": groep_label,   # ← samengevoegd zoals in je grouping
                "middelen": unieke_namen
            })

    resultaten.sort(key=lambda x: x["groep"] or "")
    return resultaten