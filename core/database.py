# core/database.py
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# We gaan 1 map omhoog (naar core) en dan 1 naar medimo-api root, dan naar data
DB_PATH = os.path.join(BASE_DIR, "..", "data", "lookup.db")

def get_db_connection():
    """
    Maakt een read-only connectie met de lookup database.
    Gebruik check_same_thread=False voor FastAPI/Lambda concurrency.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database niet gevonden op: {DB_PATH}. Run scripts/build_db.py eerst.")
    
    # URI mode voor read-only is veiliger en sneller
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn