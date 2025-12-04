import pandas as pd
import os
import sys

def process_atc_excel(conn, file_path):
    """
    Leest atc_jansen.xlsx en schrijft naar SQLite tabel 'atc_jansen'.
    """
    filename = os.path.basename(file_path)
    print(f"\n🔵 [ATC Parser] Start verwerken: {filename}")
    
    if not os.path.exists(file_path):
        print(f"❌ Bestand niet gevonden: {file_path}")
        return

    try:
        # Excel inlezen (vereist openpyxl)
        # dtype=str zorgt dat alles tekst blijft
        df = pd.read_excel(file_path, dtype=str, engine="openpyxl")
        
        # Kolomnamen opschonen (spaties weg, lowercase mag ook, maar houden we origineel voor nu)
        df.columns = [c.strip() for c in df.columns]
        
        # Data opschonen (strip whitespace van alle cellen)
        df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

        # Tabelnaam
        table_name = "atc_jansen"
        
        # Schrijven naar DB
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"✅ {len(df)} rijen weggeschreven naar tabel '{table_name}'.")

        # INDEX: Jij zoekt op 'ATC_groep' in lookup_atc3_info
        if "ATC_groep" in df.columns:
            c = conn.cursor()
            # De index naam mag uniek zijn
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_atc_jansen_groep ON {table_name}(ATC_groep)")
            conn.commit()
            print("✅ Index op 'ATC_groep' aangemaakt.")
        else:
            print(f"⚠️  Let op: Kolom 'ATC_groep' niet gevonden.")

    except Exception as e:
        print(f"❌ Fout bij verwerken ATC Excel: {e}")