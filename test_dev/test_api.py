import requests
import json
import os
import sys

# Configuratie
API_URL = "http://127.0.0.1:8001/api/review"
FILE_PATH = os.path.join("raw_data", "medimo_input.txt")

def test_with_real_file():
    # 1. Bestand controleren en inlezen
    if not os.path.exists(FILE_PATH):
        print(f"❌ Bestand niet gevonden: {FILE_PATH}")
        print("Zorg dat je 'medimo_input.txt' in de map 'raw_data' hebt staan.")
        return

    print(f"📂 Lezen van: {FILE_PATH}...")
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 2. Payload maken (zoals gedefinieerd in models.py)
    payload = {
        "text": content,
        "source": "medimo",
        "scope": "afdeling" # Of 'patient' als je dat wilt testen
    }

    print(f"🚀 Versturen naar API: {API_URL} ...\n")
    
    # 3. Request sturen met stream=True
    try:
        with requests.post(API_URL, json=payload, stream=True) as r:
            if r.status_code != 200:
                print(f"❌ API Error {r.status_code}:")
                print(r.text)
                return

            print("--- START STREAM ---")
            
            # 4. Stream lezen (NDJSON)
            for line in r.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    try:
                        data = json.loads(decoded_line)
                        
                        # --- Output Formatting ---
                        if data["type"] == "status":
                            print(f"ℹ️  [STATUS] {data['msg']}")
                        
                        elif data["type"] == "progress":
                            # Alleen elke 10% of bij specifieke events printen om spam te voorkomen
                            # Of gewoon alles printen:
                            print(f"⏳ [PROGR] {data.get('pct')}% - {data.get('current_patient', '')}")

                        elif data["type"] == "result":
                            print("\n✅ [RESULTAAT BINNEN]")
                            verwerk_resultaat(data)
                            
                        elif data["type"] == "error":
                            print(f"❌ [ERROR] {data['msg']}")

                    except json.JSONDecodeError:
                        print(f"⚠️  Kon regel niet parsen: {decoded_line}")
                        
            print("\n--- EINDE STREAM ---")

    except requests.exceptions.ConnectionError:
        print("❌ Kon geen verbinding maken. Draait 'uvicorn' wel?")

def verwerk_resultaat(data):
    """Print een mooie samenvatting van de analyses."""
    afdeling = data.get("afdeling", "?")
    patienten = data.get("data", [])
    
    print(f"🏥 Afdeling: {afdeling}")
    print(f"👥 Aantal patiënten: {len(patienten)}")
    print("-" * 40)
    
    for pat in patienten:
        print(f"\n👤 Patiënt: {pat['naam']} (Leeftijd: {pat['leeftijd'] or 'Onbekend'})")
        
        # 1. STOPP
        stopp = pat['analyses']['stopp']
        if stopp:
            print(f"   ⚠️  STOPP Criteria ({len(stopp)}):")
            for s in stopp:
                print(f"       - {s['description']} -> {s['triggering_medicines']}")
        else:
            print("   ✅ STOPP: Geen meldingen")

        # 2. ACB
        acb = pat['analyses']['acb']
        score = acb['score']
        print(f"   🧠 ACB Score: {score} ({acb['interpretatie']})")
        
        # 3. Dubbel
        dubbel = pat['analyses']['dubbelmedicatie']
        if dubbel:
            print(f"   👯 Dubbelmedicatie ({len(dubbel)}):")
            for d in dubbel:
                print(f"       - {d['groep']}: {', '.join(d['middelen'])}")

        # 4. Vragen
        vragen = pat['analyses']['standaardvragen']
        if vragen:
            print(f"   ❓ Standaardvragen ({len(vragen)}):")
            for v in vragen:
                print(f"       - {v['vraag']}")
        else:
            print("   ✅ Standaardvragen: Geen bijzonderheden")

if __name__ == "__main__":
    test_with_real_file()