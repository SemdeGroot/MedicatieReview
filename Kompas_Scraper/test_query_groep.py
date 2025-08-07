import sqlite3

groep = "laxantia__combinatiepreparaten"

# Open database opnieuw (of gebruik bestaand 'conn')
conn = sqlite3.connect("geneesmiddelen.db")
c = conn.cursor()

# Query alle geneesmiddelen in de opgegeven groep
c.execute("SELECT geneesmiddel FROM geneesmiddelen WHERE groep = ?", (groep,))
results = c.fetchall()

if results:
    print(f"Geneesmiddelen in de groep '{groep}':")
    for row in results:
        print(f" - {row[0]}")
else:
    print(f"Geen geneesmiddelen gevonden in de groep '{groep}'.")

conn.close()