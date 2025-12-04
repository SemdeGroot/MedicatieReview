import os
import sys

# 1. Bepaal waar dit script staat (.../MedicatieReview/test_dev)
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. Ga één map omhoog naar de project root (.../MedicatieReview)
project_root = os.path.abspath(os.path.join(current_dir, ".."))

# 3. Voeg die root toe aan het zoekpad van Python
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.parsers.parse_medimo_afdeling import process_medimo_text_stream

# Plak hier een stukje anonimiseerde Medimo tekst
SAMPLE_TEXT = """
Overzicht medicatie Argusvlinder
Een overzicht van alle actieve medicatie in afdeling Argusvlinder. Per patient wordt weergegeven of en zo ja welke geneesmiddelen deze mensen gebruiken.

10 records in selectie.
________________________________________
Mevr. M Curie (07-11-1942)
C   Clozapine tablet 6,25mg	1-0-0 stuks, dagelijks, Continu
C   Clozapine tablet 6,25mg	0-4-0 stuks, dagelijks, Continu
C   Colecalciferol tablet 2800ie	2-0-0 stuks, 1x per week, Continu
=Vitamine D, mag gemalen worden
C   Duraphat tandpasta 5000ppm	0-0-x gram, dagelijks, Continu
Op verzoek tandarts
C   Macrogol/zouten pdr v drank (movic/molax/gen citr)	1-0-0 stuks, dagelijks, Continu
C   Paracetamol tablet 500mg	0-0-0 stuks, dagelijks, Continu
Zn 3dd2 stuks
Z   Covid-19 vaccin niet gespecificeerd injvlst	0-0-0 milliliter, dagelijks, Zo nodig
Z   Macrogol/zouten pdr v drank (movic/molax/gen citr)	0-0-0 stuks, dagelijks, Zo nodig
bij obstipatie
Z   Vaxigrip tetra injsusp 2024/2025 wwsp 0,5ml	0-0-0 milliliter, dagelijks, Zo nodig
Dhr. A Einstein (24-08-1940)
C   Clozapine tablet 6,25mg	0-0-4 stuks, dagelijks, Continu
C   Colecalciferol tablet 2800ie	2-0-0 stuks, 1x per week, Continu
=Vitamine D, mag gemalen worden
C   Macrogol/zouten pdr v drank (movic/molax/gen citr)	1-0-0 stuks, dagelijks, Continu
C   Mirtazapine tablet 15mg	0-0-1 stuks, dagelijks, Continu
C   Paracetamol tablet 500mg	2-0-2 stuks, dagelijks, Continu
Z   Berodual cfkvr aerosol spuitbus 200do + inhalator	0-0-0 doses, dagelijks, Zo nodig
zn bij benauwdheid en pols <100, max 4dd 1-2 puffs via voorzetkamer
Z   Covid-19 vaccin niet gespecificeerd injvlst	0-0-0 milliliter, dagelijks, Zo nodig
Z   Paracetamol tablet 500mg	0-0-0 stuks, dagelijks, Zo nodig
zo nodig 1dd2 stuks (4u minstens tussen andere giften laten zitten) bij pijn
Z   Vaxigrip tetra injsusp 2024/2025 wwsp 0,5ml	0-0-0 milliliter, dagelijks, Zo nodig
"""

def test_parser():
    print("--- Start Lokale Test ---")
    
    # We roepen de generator aan
    iterator = process_medimo_text_stream(SAMPLE_TEXT)
    
    # We loopen er doorheen zoals de API dat ook zou doen
    try:
        for update in iterator:
            if update["type"] == "status":
                print(f"🔵 STATUS: {update.get('msg')}")
            
            elif update["type"] == "progress":
                print(f"🟢 PROGRESS: {update.get('pct')}% - {update.get('current_patient', '')}")
            
            elif update["type"] == "result":
                print("\n🎉 RESULTAAT BINNEN!")
                data = update["data"]
                print(f"Aantal patiënten: {len(data)}")
                if data:
                    first_pat = data[0]
                    print(f"Eerste patiënt: {first_pat['naam']}")
                    for med in first_pat['geneesmiddelen']:
                        print(f"  - {med['clean']} -> ATC: {med['ATC']} (SPKode: {med['SPKode']})")
                        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_parser()