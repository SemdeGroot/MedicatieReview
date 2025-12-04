import json
import sqlite3
import os

def process_atc_json(conn: sqlite3.Connection, core_data_dir: str):
    """
    Leest JSON bestanden voor Jansen groepen en mappings en schrijft naar DB.
    """
    print(f"\n🔵 [ATC Parser] Verwerken JSONs uit {core_data_dir}")
    
    # Paden
    groups_path = os.path.join(core_data_dir, "jansen_groups.json")
    mapping_path = os.path.join(core_data_dir, "atc_to_jansen.json")
    
    if not os.path.exists(groups_path) or not os.path.exists(mapping_path):
        print(f"❌ JSON bestanden niet gevonden in {core_data_dir}")
        return

    c = conn.cursor()

    try:
        # 1. Jansen Groups tabel (ID -> Naam)
        with open(groups_path, "r", encoding="utf-8") as f:
            groups_data = json.load(f)
            
        c.execute("DROP TABLE IF EXISTS jansen_groups")
        c.execute("CREATE TABLE jansen_groups (id INTEGER PRIMARY KEY, name TEXT)")
        
        c.executemany(
            "INSERT INTO jansen_groups (id, name) VALUES (:id, :name)", 
            groups_data
        )
        print(f"✅ {len(groups_data)} groepen geladen in 'jansen_groups'.")

        # 2. ATC Mapping tabel (ATC -> ID)
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping_data = json.load(f)
            
        c.execute("DROP TABLE IF EXISTS atc_jansen_mapping")
        c.execute("""
            CREATE TABLE atc_jansen_mapping (
                atc TEXT PRIMARY KEY, 
                atc_desc TEXT,
                group_id INTEGER,
                FOREIGN KEY(group_id) REFERENCES jansen_groups(id)
            )
        """)
        
        c.executemany(
            "INSERT INTO atc_jansen_mapping (atc, atc_desc, group_id) VALUES (:atc, :atc_desc, :group_id)",
            mapping_data
        )
        print(f"✅ {len(mapping_data)} mappings geladen in 'atc_jansen_mapping'.")
        
        # Index
        c.execute("CREATE INDEX IF NOT EXISTS idx_atc_mapping ON atc_jansen_mapping(atc)")
        conn.commit()

    except Exception as e:
        print(f"❌ Fout bij verwerken JSONs: {e}")