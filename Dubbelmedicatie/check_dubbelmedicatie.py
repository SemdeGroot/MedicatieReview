import sqlite3
from collections import defaultdict

def check_dubbelmedicatie(medicatielijst, db_path='geneesmiddelen.db'):
    """
    Controleert op dubbelmedicatie in een lijst van geneesmiddelen.
    Dubbelmedicatie = 2 of meer middelen in dezelfde geneesmiddelgroep.
    
    Returns:
        List van dicts met 'groep' en 'middelen'
    """
    # Maak verbinding met database
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Map: groep → lijst van middelen
    groep_dict = defaultdict(list)

    for middel in medicatielijst:
        c.execute("SELECT groep FROM geneesmiddelen WHERE geneesmiddel = ?", (middel.lower(),))
        result = c.fetchone()
        if result:
            groep = result[0]
            groep_dict[groep].append(middel)
        else:
            print(f"Waarschuwing: '{middel}' niet gevonden in database.")

    conn.close()

    # Filter groepen met dubbelmedicatie (≥2 middelen)
    dubbelmedicatie = []
    for groep, middelen in groep_dict.items():
        if len(middelen) >= 2:
            dubbelmedicatie.append({
                'groep': groep,
                'middelen': middelen
            })

    return dubbelmedicatie


if __name__ == "__main__":
    # Testlijst
    medicatielijst = [
        "verapamil",
        "diltiazem",
        "metoprolol",
        "bisoprolol",
        "haloperidol",
        "olanzapine",
        "clozapine"
    ]

    resultaat = check_dubbelmedicatie(medicatielijst)

    if resultaat:
        print("Dubbelmedicatie gevonden:\n")
        for item in resultaat:
            print(f"- Groep: {item['groep']}")
            print(f"  Middelen: {', '.join(item['middelen'])}\n")
    else:
        print("Geen dubbelmedicatie gevonden.")