import pandas as pd
import sqlite3

# Lees de Excel file in
df = pd.read_excel('ATC_Groepen/ATC_groepen.xlsx')

# Check of de juiste kolommen aanwezig zijn
print(df.columns)

# Maak verbinding met SQLite database
conn = sqlite3.connect('ATC_groepen.db')
c = conn.cursor()

# Tabel droppen indien deze al bestaat
c.execute('DROP TABLE IF EXISTS ATC_groepen')

# Tabel opnieuw aanmaken
c.execute('''
    CREATE TABLE ATC_groepen (
        ATC_groep TEXT,
        ATC_omschrijving TEXT,
        Jansen_omschrijving TEXT
    )
''')

# Dataframe wegschrijven naar de tabel
df.to_sql('ATC_groepen', conn, if_exists='append', index=False)

# Verbinding sluiten
conn.close()

print("Database ATC_groepen.db is succesvol aangemaakt en bestaande tabel is overschreven.")