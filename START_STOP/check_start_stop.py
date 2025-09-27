# START_STOP/check_start_stop.py
import json

def check_stopp_criteria(medicatielijst, leeftijd, json_path='START_STOP/START_STOPP.json'):
    """
    Controleert STOPP-criteria op basis van ATC-codes uit de parser-output (geen DB).
    
    Verwacht:
      medicatielijst: list[dict] met o.a. per item:
        - "clean": str (weergavenaam)
        - "ATC3": str|None
        - "ATC4": str|None
        - "ATC5": str|None
        - "ATC7": str|None

    JSON (START_STOPP.json):
      - "substances":   lijst met ATC7-codes die als stof gelden → match op ATC7
      - "group_codes":  lijst met ATC3/ATC4/ATC5-codes → match op corresponderend niveau
      - Optioneel "combination_x/y/z": elk item mag ATC7 of ATC3/4/5 zijn

    Retourneert: list[dict] met velden:
      - id, category, description, argument, triggering_medicines
    """
    # ---- laad criteria
    with open(json_path, 'r', encoding='utf-8') as f:
        stopp_data = json.load(f)
    criteria = stopp_data.get('criteria', [])

    # ---- indexen opbouwen (snel lookup per code → middel-namen)
    meds_by_atc7 = {}
    meds_by_atc5 = {}
    meds_by_atc4 = {}
    meds_by_atc3 = {}

    def _add(dct, key, name):
        if not key:
            return
        dct.setdefault(key, set()).add(name)

    for gm in medicatielijst or []:
        name = (gm.get("clean") or "").strip() or "Onbekend middel"
        _add(meds_by_atc7, gm.get("ATC7"), name)
        _add(meds_by_atc5, gm.get("ATC5"), name)
        _add(meds_by_atc4, gm.get("ATC4"), name)
        _add(meds_by_atc3, gm.get("ATC3"), name)

    def meds_for_substance_token(tok):
        """Substances → ATC7-match."""
        tok = (tok or "").strip().upper()
        return set(meds_by_atc7.get(tok, set()))

    def meds_for_group_token(tok):
        """Group codes → probeer exact op ATC5, anders ATC4, anders ATC3."""
        tok = (tok or "").strip().upper()
        if tok in meds_by_atc5:  # strengst eerst
            return set(meds_by_atc5[tok])
        if tok in meds_by_atc4:
            return set(meds_by_atc4[tok])
        if tok in meds_by_atc3:
            return set(meds_by_atc3[tok])
        return set()

    def meds_for_any_token(tok):
        """Gebruik in combinaties: laat item zowel als ATC7 (substance) als groep (ATC5/4/3) matchen."""
        return meds_for_substance_token(tok) | meds_for_group_token(tok)

    triggered_criteria = []

    for criterion in criteria:
        if criterion.get("type") != "STOP":
            continue
        if criterion.get("requires_age", False) and leeftijd < criterion.get("age_min", 0):
            continue

        matched_meds = set()

        # 1) Substances → ATC7
        for sub in criterion.get("substances", []):
            matched_meds |= meds_for_substance_token(sub)

        # 2) Groepen → ATC5/4/3
        for gr in criterion.get("group_codes", []):
            matched_meds |= meds_for_group_token(gr)

        # 3) Combinaties (elk onderdeel kan ATC7 of ATC 3/4/5 zijn)
        combi_x = criterion.get("combination_x", [])
        combi_y = criterion.get("combination_y", [])
        combi_z = criterion.get("combination_z", [])

        def has_any(items):
            return any(meds_for_any_token(t) for t in items)

        combi_match = False
        if combi_x and combi_y and combi_z:
            combi_match = has_any(combi_x) and has_any(combi_y) and has_any(combi_z)
        elif combi_x and combi_y:
            combi_match = has_any(combi_x) and has_any(combi_y)

        if combi_match:
            # Voeg alle betrokken middelen (per onderdeel) toe voor rapportage
            for part in (combi_x + combi_y + combi_z):
                matched_meds |= meds_for_any_token(part)

        if matched_meds:
            meds_list = sorted(matched_meds, key=str.lower)
            if combi_match:
                triggering_text = f"Combinatie: {' + '.join(meds_list)}"
            else:
                triggering_text = ", ".join(meds_list)

            triggered_criteria.append({
                "id": criterion.get("id", ""),
                "category": criterion.get("category", ""),
                "description": criterion.get("description", ""),
                "argument": criterion.get("argument", ""),
                "triggering_medicines": triggering_text
            })

    return triggered_criteria