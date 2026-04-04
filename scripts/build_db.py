import sqlite3
import os
import sys

# Paden
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(BASE_DIR, "..")
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "lookup.db")

# Input mappen
GST_DIR = os.path.join(ROOT_DIR, "raw_data", "g-standaard")
ATCJANSEN_DATA_DIR = os.path.join(ROOT_DIR, "raw_data", "atc_jansen")
HB_DIR = os.path.join(ROOT_DIR, "raw_data", "healthbase")

# Import parsers
try:
    from parsers.atc_groepen_parser import process_atc_json
    from parsers.gstandaard_parser import process_gstandaard
    from parsers.healthbase_parser import process_healthbase
except ImportError:
    sys.path.append(BASE_DIR)
    from parsers.atc_groepen_parser import process_atc_json
    from parsers.gstandaard_parser import process_gstandaard
    from parsers.healthbase_parser import process_healthbase

def main():
    print(f"--- Start Build Database ---")

    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except: pass

    conn = sqlite3.connect(DB_PATH)

    # 1. ATC Jansen (JSON -> SQL)
    process_atc_json(conn, ATCJANSEN_DATA_DIR)

    # 2. G-Standaard
    process_gstandaard(conn, GST_DIR)

    # 3. Healthbase etiketnamen
    process_healthbase(conn, HB_DIR)

    conn.close()
    print("\nDatabase gereed!")

if __name__ == "__main__":
    main()
