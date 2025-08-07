import sqlite3

spkode = "00041793"  # Vervang dit door de SPKode die je wilt testen

# Open database
conn = sqlite3.connect("geneesmiddelen.db")
c = conn.cursor()

# Query alle matches voor de opgegeven SPKode
c.execute("""
    SELECT groep, geneesmiddel, SPKode, ATCcode, ATC_groep, ATC_omschrijving 
    FROM geneesmiddelen 
    WHERE SPKode = ?
""", (spkode,))
results = c.fetchall()

if results:
    print(f"Matches voor SPKode '{spkode}':")
    for idx, (groep, geneesmiddel, spkode, atccode, atc_groep, atc_omschrijving) in enumerate(results, start=1):
        print(f"{idx}. Groep: {groep} | Geneesmiddel: {geneesmiddel} | SPKode: {spkode} | ATC-code: {atccode} | ATC-groep: {atc_groep} | Omschrijving: {atc_omschrijving}")
else:
    print(f"SPKode '{spkode}' niet gevonden.")

conn.close()
