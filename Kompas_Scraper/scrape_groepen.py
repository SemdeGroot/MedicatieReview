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
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("\u200b", "")
    name = name.strip()
    return name.lower()

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
# BST711T inlezen en NMNR → (SPKode, ATC-code) dictionary maken
# ===============================
def load_bst711t(filepath):
    nmnr_to_spk_atc = {}
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            nmnr = line[40:47].strip()
            spkode = line[104:112].strip()
            atc_code = line[118:126].strip()
            if nmnr:
                nmnr_to_spk_atc[nmnr] = (spkode, atc_code)
    return nmnr_to_spk_atc

# ===============================
# BST801T inlezen en ATC_groep → Nederlandse omschrijving dictionary maken
# ===============================
def load_bst801t(filepath):
    atc3_to_omschrijving = {}
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            atc_code = line[5:13]
            atc_groep = atc_code[:3].strip()
            rest = atc_code[3:].strip()
            omschrijving = line[13:93].strip()
            
            # We nemen alleen ATC-groep op als de eerste 3 tekens gevuld zijn
            # én de rest van het veld leeg is
            if atc_groep and not rest and omschrijving:
                atc3_to_omschrijving[atc_groep] = omschrijving
    return atc3_to_omschrijving

# ===============================
# Load BST data
# ===============================
nmnaam_to_nmnr = load_bst020t(BST_PATH + "BST020T")
nmnr_to_spk_atc = load_bst711t(BST_PATH + "BST711T")
atc3_to_omschrijving = load_bst801t(BST_PATH + "BST801T")

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
        SPKode TEXT,
        ATCcode TEXT,
        ATC_groep TEXT,
        ATC_omschrijving TEXT
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

        nmnr = nmnaam_to_nmnr.get(geneesmiddel)
        spk, atc, atc_groep, atc_omschrijving = (None, None, None, None)
        
        if nmnr and nmnr in nmnr_to_spk_atc:
            spk, atc = nmnr_to_spk_atc[nmnr]
            if atc and len(atc) >= 3:
                atc_groep = atc[:3]
                atc_omschrijving = atc3_to_omschrijving.get(atc_groep)

        status = "✅" if spk else "❌"
        print(f"  {status} {geneesmiddel}")

        c.execute(
            "INSERT INTO geneesmiddelen (groep, geneesmiddel, SPKode, ATCcode, ATC_groep, ATC_omschrijving) VALUES (?, ?, ?, ?, ?, ?)",
            (groepsnaam, geneesmiddel, spk, atc, atc_groep, atc_omschrijving)
        )
    conn.commit()
    time.sleep(random.uniform(0.5, 1.5))

conn.close()
print("\nKlaar! Alle gegevens opgeslagen in geneesmiddelen.db.")
