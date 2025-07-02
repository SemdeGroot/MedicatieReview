import sqlite3
import pandas as pd

# Open database
conn = sqlite3.connect("geneesmiddelen.db")

# Query alle unieke ATC_groep codes en omschrijvingen
query = """
    SELECT DISTINCT ATC_groep, ATC_omschrijving
    FROM geneesmiddelen
    WHERE ATC_groep IS NOT NULL
    ORDER BY ATC_groep
"""

df = pd.read_sql_query(query, conn)

# Sla op als Excel-bestand
df.to_excel("ATC_groepen.xlsx", index=False)

print(f"Excel-bestand 'ATC_groepen.xlsx' succesvol aangemaakt met {len(df)} unieke ATC-groepen.")

conn.close()