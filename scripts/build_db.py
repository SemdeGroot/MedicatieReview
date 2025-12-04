import sqlite3
import os
import sys

# Paden bepalen
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DATA_DIR = os.path.join(BASE_DIR, "..", "raw_data")
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DB_PATH = os.path.join(DATA_DIR, "lookup.db")

# Specifieke paden volgens jouw vraag
# 1. G-Standaard map
GST_DIR = os.path.join(RAW_DATA_DIR, "g-standaard")

# 2. ATC Jansen Excel bestand
ATC_FILE = os.path.join(RAW_DATA_DIR, "atc_jansen", "atc_jansen.xlsx")

# Importeer de parsers
try:
    from parsers.atc_groepen_parser import process_atc_excel
    from parsers.gstandaard_parser import process_gstandaard
except ImportError:
    sys.path.append(BASE_DIR)
    from parsers.atc_groepen_parser import process_atc_excel
    from parsers.gstandaard_parser import process_gstandaard

def main():
    print(f"🚀 --- Start Build Database ---")
    print(f"📂 G-Standaard map: {GST_DIR}")
    print(f"📂 ATC bestand:     {ATC_FILE}")
    print(f"💾 Database doel:   {DB_PATH}")
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Oude DB verwijderen
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print("🗑️  Oude database verwijderd.")
        except PermissionError:
            print("❌ Kan oude database niet verwijderen (is hij nog open?).")
            return

    # Verbinding maken
    conn = sqlite3.connect(DB_PATH)
    
    # 1. ATC Jansen (Excel)
    process_atc_excel(conn, ATC_FILE)
    
    # 2. G-Standaard (Map met tekstbestanden)
    process_gstandaard(conn, GST_DIR)
    
    conn.close()
    print("\n🎉 Database volledig opgebouwd!")

if __name__ == "__main__":
    main()