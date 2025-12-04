from collections import defaultdict
from typing import List, Dict, Any, Optional

def _uniq_sorted(names: List[str]) -> List[str]:
    """
    Unieke namen, netjes alfabetisch.
    """
    # Filter lege namen eruit en sorteer case-insensitive
    valid_names = {n for n in names if n and n.strip()}
    return sorted(valid_names, key=lambda x: x.lower())

def check_dubbelmedicatie(geneesmiddelen: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detecteer dubbelmedicatie op basis van ATC5.
    
    Args:
        geneesmiddelen: Lijst met medicijnen (output van parser).
                        Moet 'ATC5', 'ATC5_omschrijving' en 'clean' bevatten.
    
    Returns:
        Lijst met gedetecteerde dubbelmedicaties.
    """
    if not geneesmiddelen:
        return []

    # Verzamel per ATC5 code
    # Structuur: { "C07AB02": {"desc": "Metoprolol", "names": ["Metoprolol", "Selokeen"]} }
    per_atc5 = defaultdict(lambda: {"desc": None, "names": []})

    for gm in geneesmiddelen:
        naam = (gm.get("clean") or "").strip() or "Onbekend middel"
        
        # Gebruik veilige get() en strip()
        atc5 = (gm.get("ATC5") or "").strip().upper()
        
        if atc5 and len(atc5) >= 5:
            # Sla omschrijving op (eerste die we tegenkomen is prima)
            if not per_atc5[atc5]["desc"]:
                per_atc5[atc5]["desc"] = gm.get("ATC5_omschrijving")
            
            per_atc5[atc5]["names"].append(naam)

    resultaten = []

    # Analyseer de groepen
    for atc5, data in per_atc5.items():
        # Alleen unieke namen tellen (dus 2x exact dezelfde string telt niet als dubbelmedicatie)
        # Of wil je dat 2x "Paracetamol" ook als dubbel telt? 
        # Jouw originele script filterde op unieke namen, dus dat laat ik zo.
        unieke_namen = _uniq_sorted(data["names"])
        
        if len(unieke_namen) >= 2:
            desc = (data["desc"] or "").strip()
            label = f"{atc5}"
            if desc:
                label += f" - {desc}"
            
            resultaten.append({
                "groep": label,
                "middelen": unieke_namen
            })

    # Sorteer alfabetisch op groepsnaam
    resultaten.sort(key=lambda item: (item.get("groep") or "").lower())
    
    return resultaten