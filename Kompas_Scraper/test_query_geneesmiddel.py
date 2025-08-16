import sqlite3

geneesmiddel = "macrogol/elektrolyten"

# Open database
conn = sqlite3.connect("geneesmiddelen.db")
c = conn.cursor()

# Query alle matches voor het opgegeven geneesmiddel
c.execute("""
    SELECT groep, geneesmiddel, SPKode, ATCcode, ATC_groep, ATC_omschrijving 
    FROM geneesmiddelen 
    WHERE geneesmiddel = ?
""", (geneesmiddel,))
results = c.fetchall()

if results:
    print(f"Matches voor geneesmiddel '{geneesmiddel}':")
    for idx, (groep, geneesmiddel, spkode, atccode, atc_groep, atc_omschrijving) in enumerate(results, start=1):
        print(f"{idx}. Groep: {groep} | Geneesmiddel: {geneesmiddel} | SPKode: {spkode} | ATC-code: {atccode} | ATC-groep: {atc_groep} | Omschrijving: {atc_omschrijving}")
else:
    print(f"Geneesmiddel '{geneesmiddel}' niet gevonden.")

conn.close()