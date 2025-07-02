import json
import sqlite3

def check_stopp_criteria(medicatielijst, leeftijd, db_path='geneesmiddelen.db', json_path='START_STOP/START_STOPP.json'):
    """
    Controleert STOPP-criteria en geeft geneesmiddelen terug die het criterium triggeren,
    ook als dit via groepscode ging.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        stopp_data = json.load(f)
    criteria = stopp_data['criteria']
    
    # Ophalen van groep per middel
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    middel_to_groep = {}
    for middel in medicatielijst:
        c.execute("SELECT groep FROM geneesmiddelen WHERE geneesmiddel = ?", (middel.lower(),))
        result = c.fetchone()
        middel_to_groep[middel.lower()] = result[0] if result else None
    conn.close()

    alle_groepen = set(filter(None, middel_to_groep.values()))
    alle_middelen = set(middel.lower() for middel in medicatielijst)

    triggered_criteria = []
    for criterion in criteria:
        if criterion["type"] != "STOP":
            continue
        if criterion.get("requires_age", False) and leeftijd < criterion.get("age_min", 0):
            continue

        matched_middelen = set()

        # Directe stofmatch → voeg geneesmiddel toe
        for sub in criterion["substances"]:
            if sub in alle_middelen:
                matched_middelen.add(sub)

        # Groepsmatch → voeg geneesmiddelen met die groep toe
        for gr in criterion["group_codes"]:
            if gr in alle_groepen:
                middelen_in_groep = [m for m, g in middel_to_groep.items() if g == gr]
                matched_middelen.update(middelen_in_groep)

        # Combinatiematch → alle onderdelen apart behandelen
        combi_x = criterion.get("combination_x", [])
        combi_y = criterion.get("combination_y", [])
        combi_z = criterion.get("combination_z", [])

        combi_x_hit = any(g in alle_groepen or g in alle_middelen for g in combi_x)
        combi_y_hit = any(g in alle_groepen or g in alle_middelen for g in combi_y)
        combi_z_hit = any(g in alle_groepen or g in alle_middelen for g in combi_z)

        combi_match = False
        if combi_x and combi_y and combi_z:
            combi_match = combi_x_hit and combi_y_hit and combi_z_hit
        elif combi_x and combi_y:
            combi_match = combi_x_hit and combi_y_hit

        if combi_match:
            for onderdeel in (combi_x + combi_y + combi_z):
                if onderdeel in alle_middelen:
                    matched_middelen.add(onderdeel)
                elif onderdeel in alle_groepen:
                    middelen_in_groep = [m for m, g in middel_to_groep.items() if g == onderdeel]
                    matched_middelen.update(middelen_in_groep)

        if matched_middelen:
            triggered_criteria.append({
                "id": criterion["id"],
                "description": criterion["description"],
                "triggering_medicines": sorted(matched_middelen)
            })

    return triggered_criteria
