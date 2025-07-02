import sqlite3

geneesmiddel = "risperidon"
# geneesmiddel = "ezetimib/atorvastatine"  # voorbeeld met verborgen spatie verwijderd

# Open database
conn = sqlite3.connect("geneesmiddelen.db")
c = conn.cursor()

# Query alle matches voor het opgegeven geneesmiddel
c.execute("SELECT groep, SPKode FROM geneesmiddelen WHERE geneesmiddel = ?", (geneesmiddel,))
results = c.fetchall()

if results:
    print(f"Matches voor geneesmiddel '{geneesmiddel}':")
    for idx, (groep, spkode) in enumerate(results, start=1):
        print(f"{idx}. Groep: {groep} | SPKode: {spkode}")
else:
    print(f"Geneesmiddel '{geneesmiddel}' niet gevonden.")

conn.close()
