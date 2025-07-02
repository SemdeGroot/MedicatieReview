import json
import sqlite3

def check_stopp_criteria(medicatielijst, leeftijd, db_path='geneesmiddelen.db', json_path='START-STOP/START_STOPP.json'):
    """
    Controleert STOPP-criteria op basis van een opgegeven medicatielijst en leeftijd van een patiënt.

    Deze functie laadt de STOPP-criteria vanuit een JSON-bestand en vergelijkt de ingevoerde medicatie 
    met stoffen, geneesmiddelengroepen en combinaties die in de criteria genoemd worden. Daarbij wordt ook 
    rekening gehouden met leeftijdsafhankelijke voorwaarden.

    Args:
        medicatielijst (list of str): Lijst met geneesmiddelennamen zoals gebruikt door de patiënt.
        leeftijd (int): Leeftijd van de patiënt.
        db_path (str, optional): Pad naar de SQLite-database met geneesmiddelgroepen. 
                                 Default = 'geneesmiddelen.db'.
        json_path (str, optional): Pad naar het JSON-bestand met STOPP-criteria. 
                                   Default = 'START-STOP/START_STOPP.json'.

    Returns:
        list of dict: Een lijst van getriggerde STOPP-criteria, elk met:
                      - 'id': criterium ID
                      - 'description': beschrijving van het criterium
                      - 'matched_by': dict met matchende stoffen, groepen en/of combinaties
    """
    # Stap 1: laadt JSON met criteria
    with open(json_path, 'r', encoding='utf-8') as f:
        stopp_data = json.load(f)
    criteria = stopp_data['criteria']
    
    # Stap 2: haal groepen op van alle medicatie
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    middel_to_groep = {}
    for middel in medicatielijst:
        c.execute("SELECT groep FROM geneesmiddelen WHERE geneesmiddel = ?", (middel.lower(),))
        result = c.fetchone()
        if result:
            middel_to_groep[middel.lower()] = result[0]
        else:
            middel_to_groep[middel.lower()] = None  # Geen groep gevonden
    conn.close()

    # Verzamel alle gevonden groepen
    alle_groepen = set(filter(None, middel_to_groep.values()))
    alle_middelen = set(middel.lower() for middel in medicatielijst)

    # Stap 3: doorloop alle STOPP-criteria
    triggered_criteria = []
    for criterion in criteria:
        if criterion["type"] != "STOP":
            continue
        if criterion.get("requires_age", False) and leeftijd < criterion.get("age_min", 0):
            continue
        
        # Check directe stof-match
        stof_match = any(sub in alle_middelen for sub in criterion["substances"])
        
        # Check groep-match
        groep_match = any(gr in alle_groepen for gr in criterion["group_codes"])
        
        # Check combinatie-match
        combi_match = False
        combi_x = criterion.get("combination_x", [])
        combi_y = criterion.get("combination_y", [])
        combi_z = criterion.get("combination_z", [])

        if combi_x and combi_y and combi_z:
            x_hit = any(g in alle_groepen or g in alle_middelen for g in combi_x)
            y_hit = any(g in alle_groepen or g in alle_middelen for g in combi_y)
            z_hit = any(g in alle_groepen or g in alle_middelen for g in combi_z)
            combi_match = x_hit and y_hit and z_hit
        elif combi_x and combi_y:
            x_hit = any(g in alle_groepen or g in alle_middelen for g in combi_x)
            y_hit = any(g in alle_groepen or g in alle_middelen for g in combi_y)
            combi_match = x_hit and y_hit

        # Voeg toe als iets matcht
        if stof_match or groep_match or combi_match:
            triggered_criteria.append({
                "id": criterion["id"],
                "description": criterion["description"],
                "matched_by": {
                    "substance": [s for s in criterion["substances"] if s in alle_middelen],
                    "group": [g for g in criterion["group_codes"] if g in alle_groepen],
                    "combi_x": [g for g in combi_x if g in alle_groepen or g in alle_middelen],
                    "combi_y": [g for g in combi_y if g in alle_groepen or g in alle_middelen],
                    "combi_z": [g for g in combi_z if g in alle_groepen or g in alle_middelen] if combi_z else []
                }
            })

    return triggered_criteria


if __name__ == "__main__":
    medicatielijst = ["tramadol"]
    leeftijd = 75
    resultaat = check_stopp_criteria(medicatielijst, leeftijd)
    for item in resultaat:
        print(f"{item['id']}: {item['description']}")
        print("Getriggerd door:", item["matched_by"])
        print()
