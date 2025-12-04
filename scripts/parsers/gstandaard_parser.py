import pandas as pd
import os

# Configuratie van de Fixed Width Files
GST_CONFIG = {
    "BST020": {
        "filename": "BST020T",
        "table_name": "bst020_namen",
        "colspecs": [(5, 12), (85, 135)],
        "names": ["nmnr", "nmnaam"]
    },
    "BST004": {
        "filename": "BST004T",
        "table_name": "bst004_artikelen",
        "colspecs": [(13, 21), (21, 28)],
        "names": ["hpkode", "atnmnr"]
    },
    "BST052": {
        "filename": "BST052T",
        "table_name": "bst052_recept",
        "colspecs": [(5, 13), (13, 20), (20, 28)],
        "names": ["prkode", "prnmnr", "gpkode"]
    },
    "BST070": {
        "filename": "BST070T",
        "table_name": "bst070_handelsproducten",
        "colspecs": [(5, 13), (29, 37)],
        "names": ["hpkode", "gpkode"]
    },
    "BST711": {
        "filename": "BST711T",
        "table_name": "bst711_generiek",
        "colspecs": [(5, 13), (13, 21), (33, 40), (40, 47), (104, 112), (118, 126)],
        "names": ["gpkode", "gskode", "gpnmnr", "gpstnr", "spkode", "atc"]
    },
    "BST031": {
        "filename": "BST031T",
        "table_name": "bst031_voorschrijfpr",
        "colspecs": [(5, 13), (13, 21), (21, 29), (29, 36)],
        "names": ["hpkode", "prkode", "mhkode", "hpnamn"]
    },
    "BST801": {
        "filename": "BST801T",
        "table_name": "bst801_atc_teksten",
        "colspecs": [(5, 13), (13, 93)],
        "names": ["atcode", "atoms"]
    }
}

def process_gstandaard(conn, gst_folder_path):
    """
    Verwerkt G-Standaard bestanden uit de opgegeven map.
    """
    print(f"\n🟢 [G-Standaard Parser] Lezen uit map: {gst_folder_path}")
    
    if not os.path.exists(gst_folder_path):
        print(f"❌ Map niet gevonden: {gst_folder_path}")
        return

    for key, config in GST_CONFIG.items():
        file_path = os.path.join(gst_folder_path, config["filename"])
        
        if not os.path.exists(file_path):
            print(f"⚠️  Bestand niet gevonden: {config['filename']} (SKIP)")
            continue
            
        print(f"   ⏳ {config['filename']} -> {config['table_name']}...")
        
        try:
            df = pd.read_fwf(
                file_path, 
                colspecs=config["colspecs"], 
                header=None,                 
                names=config["names"],       
                encoding="latin-1",
                dtype=str
            )
            
            # String cleanup
            df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            
            df.to_sql(config["table_name"], conn, if_exists="replace", index=False)
            print(f"   ✅ {len(df)} rijen.")
            
        except Exception as e:
            print(f"   ❌ Fout bij {config['filename']}: {e}")

    # Indexen aanmaken
    _create_indexes(conn)

def _create_indexes(conn):
    print("\n🟡 [G-Standaard Parser] Indexen aanmaken op basis van zoekroutes...")
    c = conn.cursor()
    
    # Lijst van (IndexNaam, Tabel, Kolom)
    indices = [
        # --- BST020 (Namen) ---
        # Gebruikt in: exact_nmnr_match (zoeken op naam)
        ("idx_bst020_nmnaam", "bst020_namen", "nmnaam"),
        # Gebruikt in: logic om later terug te zoeken op nummer (optioneel, maar handig)
        ("idx_bst020_nmnr",   "bst020_namen", "nmnr"),

        # --- Route 1 (BST711 Direct) ---
        # Gebruikt in: _attempt_resolve_sp (row["GPSTNR"] == nmnr)
        ("idx_bst711_gpstnr", "bst711_generiek", "gpstnr"),
        # Gebruikt in: _attempt_resolve_sp (row["GPNMNR"] == nmnr)
        ("idx_bst711_gpnmnr", "bst711_generiek", "gpnmnr"),

        # --- Route 2 (Via PR) ---
        # Gebruikt in: _attempt_resolve_sp (row["PRNMNR"] == nmnr)
        ("idx_bst052_prnmnr", "bst052_recept", "prnmnr"),

        # --- Route 3 (Via AT) ---
        # Gebruikt in: _attempt_resolve_sp (r["ATNMNR"] == nmnr)
        ("idx_bst004_atnmnr", "bst004_artikelen", "atnmnr"),

        # --- Route 4 (Via HPNAMN) ---
        # Gebruikt in: _attempt_resolve_sp (r["HPNAMN"] == nmnr)
        ("idx_bst031_hpnamn", "bst031_voorschrijfpr", "hpnamn"),

        # --- Koppelingen (Joins / Lookups) ---
        # BST070 wordt gebruikt om van HPKODE naar GPKODE te gaan in Route 3 & 4
        ("idx_bst070_hpkode", "bst070_handelsproducten", "hpkode"),

        # BST711 wordt uiteindelijk altijd geraadpleegd op GPKODE of GSKODE
        ("idx_bst711_gpkode", "bst711_generiek", "gpkode"),
        ("idx_bst711_gskode", "bst711_generiek", "gskode"),
        
        # Output lookup (SPKode -> ATC)
        ("idx_bst711_spkode", "bst711_generiek", "spkode"),

        # --- Teksten (BST801) ---
        # Om ATC omschrijvingen op te halen
        ("idx_bst801_atcode", "bst801_atc_teksten", "atcode")
    ]

    for idx_name, table, col in indices:
        try:
            # Eerst checken of tabel bestaat (voor robuustheid)
            c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if c.fetchone():
                c.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({col})")
            else:
                print(f"   ⚠️ Tabel {table} bestaat niet, index {idx_name} overgeslagen.")
        except Exception as e:
            print(f"   ⚠️ Fout index {idx_name}: {e}")
    
    conn.commit()
    print("✅ G-Standaard indexen gereed.")