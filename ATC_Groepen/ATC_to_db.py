import os
import pandas as pd
import sqlite3

# ==== 1) Excel (ATC-3 + Jansen-omschrijving) opnieuw inlezen/aanmaken ====
# Lees de Excel file in
df = pd.read_excel('ATC_Groepen/ATC_groepen.xlsx')  # verwacht kolommen: ATC_groep, ATC_omschrijving, Jansen_omschrijving
print("Kolommen uit Excel:", list(df.columns))

# Maak/overschrijf database + tabel
conn = sqlite3.connect('ATC_groepen.db')
c = conn.cursor()

c.execute('DROP TABLE IF EXISTS ATC_groepen')
c.execute('''
    CREATE TABLE ATC_groepen (
        ATC_groep TEXT,
        ATC_omschrijving TEXT,
        Jansen_omschrijving TEXT
    )
''')
conn.commit()

# Voeg Excel-gegevens toe
df.to_sql('ATC_groepen', conn, if_exists='append', index=False)

# Zorg dat ATC_groep uniek is
c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_atc_groep ON ATC_groepen(ATC_groep)')
conn.commit()

print("Basis (Excel) geladen in ATC_groepen.db.")

# ==== 2) Aanvullen met ATC-4 en ATC-5 uit G-Standaard/BST801T ====
bst801_path = os.path.join('G-Standaard', 'BST801T')
if not os.path.exists(bst801_path):
    raise FileNotFoundError(f"BST801T niet gevonden op pad: {bst801_path}")

def iter_bst801_lines(path):
    """
    Geeft tuples (atc_code, nl_omschrijving) uit BST801T.
    Posities volgens bestandsbeschrijving:
      ATCODE : pos 006-013  -> line[5:13]
      ATOMS  : pos 014-093  -> line[13:93]
    """
    # In de praktijk is BST vaak UTF-8; soms LATIN-1. We proberen UTF-8, anders LATIN-1.
    for enc in ('utf-8', 'latin-1'):
        try:
            with open(path, 'r', encoding=enc) as f:
                for line in f:
                    atc_code = line[5:13].strip()
                    nl_desc  = line[13:93].strip()
                    if atc_code and nl_desc:
                        yield atc_code, nl_desc
            break
        except UnicodeDecodeError:
            continue

# Verzamel ATC-4/5 en voeg toe
inserted_4 = inserted_5 = 0
for atc_code, nl_desc in iter_bst801_lines(bst801_path):
    lvl = len(atc_code)
    if lvl in (4, 5):  # Alleen ATC niveau 4 en 5 toevoegen
        # Jansen-omschrijving is niet beschikbaar voor 4/5 -> NULL
        c.execute(
            "INSERT OR IGNORE INTO ATC_groepen (ATC_groep, ATC_omschrijving, Jansen_omschrijving) VALUES (?, ?, NULL)",
            (atc_code, nl_desc)
        )
        if c.rowcount == 1:
            if lvl == 4:
                inserted_4 += 1
            else:
                inserted_5 += 1

conn.commit()
conn.close()

print(f"ATC-4 toegevoegd (nieuw): {inserted_4}")
print(f"ATC-5 toegevoegd (nieuw): {inserted_5}")
print("Database ATC_groepen.db is bijgewerkt met ATC-4 en ATC-5 omschrijvingen uit BST801T.")