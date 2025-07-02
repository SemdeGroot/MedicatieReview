import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import random
import re
import unicodedata

BASE_URL = "https://www.farmacotherapeutischkompas.nl"
BST_PATH = "G-Standaard/"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

# ===============================
# Functie om geneesmiddelnaam op te schonen
# ===============================
def clean_name(name):
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    name = re.sub(r"\(.*?\)", "", name)           # Haakjes verwijderen
    name = name.replace("\u200b", "")             # Verborgen spaties verwijderen
    name = name.strip()
    return name

# ===============================
# BST020T inlezen en naam → NMNR dictionary maken
# ===============================
def load_bst020t(filepath):
    nmnaam_to_nmnr = {}
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            nmnr = line[5:12].strip()
            nmnaam = line[85:135].strip().lower()
            nmnaam = unicodedata.normalize('NFKD', nmnaam).encode('ASCII', 'ignore').decode('ASCII')
            nmnaam_to_nmnr[nmnaam] = nmnr
    return nmnaam_to_nmnr

# ===============================
# BST711T inlezen en NMNR → SPKode dictionary maken
# ===============================
def load_bst711t(filepath):
    nmnr_to_spkode = {}
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            nmnr = line[40:47].strip()  # GPNMNR veld
            spkode = line[104:112].strip()  # SPKode veld (let op correcte slicing)
            if nmnr and spkode:
                nmnr_to_spkode[nmnr] = spkode
    return nmnr_to_spkode

# ===============================
# Load BST data
# ===============================
nmnaam_to_nmnr = load_bst020t(BST_PATH + "BST020T")
nmnr_to_spkode = load_bst711t(BST_PATH + "BST711T")

# ===============================
# Haal groep-links op uit het Kompas
# ===============================
response = requests.get(BASE_URL + "/bladeren/preparaatteksten/groep", headers=headers)
soup = BeautifulSoup(response.text, "html.parser")
groep_links = soup.select("#directory a[href^='/bladeren/preparaatteksten/groep/']")
groepen = [link["href"].split("/groep/")[1].split("#")[0] for link in groep_links]
print(f"Geselecteerde {len(groepen)} groepen om te scrapen.")

# ===============================
# Database aanmaken
# ===============================
conn = sqlite3.connect("geneesmiddelen.db")
c = conn.cursor()
c.execute("DROP TABLE IF EXISTS geneesmiddelen")
c.execute("""
    CREATE TABLE geneesmiddelen (
        groep TEXT,
        geneesmiddel TEXT,
        SPKode TEXT
    )
""")
conn.commit()

# ===============================
# Scrap en sla op in DB
# ===============================
for groepslug in groepen:
    url = f"{BASE_URL}/bladeren/preparaatteksten/groep/{groepslug}"
    group_response = requests.get(url, headers=headers)
    group_soup = BeautifulSoup(group_response.text, "html.parser")
    groepsnaam = groepslug

    print(f"\nVerwerk groep: {groepsnaam}")

    geneesmiddelen_links = group_soup.select("#medicine-listing a.medicine")

    for link in geneesmiddelen_links:
        raw_name = link.text.strip()
        geneesmiddel = clean_name(raw_name)
        lookup_key = geneesmiddel.lower()

        nmnr = nmnaam_to_nmnr.get(lookup_key)
        spk = nmnr_to_spkode.get(nmnr) if nmnr else None

        status = "✅" if spk else "❌"
        print(f"  {status} {geneesmiddel}")

        c.execute(
            "INSERT INTO geneesmiddelen (groep, geneesmiddel, SPKode) VALUES (?, ?, ?)",
            (groepsnaam, geneesmiddel, spk)
        )
    conn.commit()
    time.sleep(random.uniform(0.5, 1.5))

conn.close()
print("\nKlaar! Alle gegevens opgeslagen in geneesmiddelen.db.")
