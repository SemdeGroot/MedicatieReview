import sqlite3

# Open database
conn = sqlite3.connect("geneesmiddelen.db")
c = conn.cursor()

# Selecteer alle geneesmiddelen zonder GPKode
c.execute("SELECT groep, geneesmiddel FROM geneesmiddelen WHERE GPKode IS NULL")
results = c.fetchall()

if results:
    print("Geneesmiddelen zonder GPKode:\n")
    for groep, geneesmiddel in results:
        print(f"- {geneesmiddel} (groep: {groep})")
else:
    print("Alle geneesmiddelen hebben een GPKode.")

conn.close()