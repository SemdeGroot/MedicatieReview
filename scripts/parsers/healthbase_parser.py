"""
Parse Healthbase Taxe CSV and build healthbase_etiketnamen table in lookup.db.
"""
import csv
import os
import sqlite3

CSV_FILENAME = "healthbase-taxe-2604.csv"
CSV_DELIMITER = ";"
ETIKETNAAM_COL = 3
ATC_COL = 9
TABLE = "healthbase_etiketnamen"
BATCH_SIZE = 5000


def process_healthbase(conn: sqlite3.Connection, healthbase_dir: str):
    csv_path = os.path.join(healthbase_dir, CSV_FILENAME)
    if not os.path.exists(csv_path):
        print(f"  Healthbase CSV niet gevonden: {csv_path} - overgeslagen.")
        return

    print(f"  Healthbase: lezen van {csv_path} ...")
    rows = _read_csv(csv_path)
    print(f"  Healthbase: {len(rows)} unieke (etiketnaam, atc) rijen.")

    _build_table(conn, rows)
    print(f"  Healthbase: tabel '{TABLE}' aangemaakt.")


def _read_csv(csv_path: str) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    rows: list[tuple[str, str]] = []

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=CSV_DELIMITER)
        next(reader, None)  # skip header

        max_col = max(ETIKETNAAM_COL, ATC_COL)
        for row in reader:
            if len(row) <= max_col:
                continue
            etiketnaam = row[ETIKETNAAM_COL].strip()
            atc = row[ATC_COL].strip().upper()
            if not etiketnaam or not atc:
                continue
            key = (etiketnaam.lower(), atc)
            if key in seen:
                continue
            seen.add(key)
            rows.append((etiketnaam, atc))

    return rows


def _build_table(conn: sqlite3.Connection, rows: list[tuple[str, str]]):
    cursor = conn.cursor()

    cursor.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cursor.execute(f"""
        CREATE TABLE {TABLE} (
            etiketnaam TEXT NOT NULL,
            atc        TEXT NOT NULL
        )
    """)

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        cursor.executemany(
            f"INSERT INTO {TABLE} (etiketnaam, atc) VALUES (?, ?)",
            batch,
        )

    cursor.execute(f"CREATE INDEX idx_{TABLE}_etiketnaam ON {TABLE} (etiketnaam)")
    cursor.execute(f"CREATE INDEX idx_{TABLE}_atc ON {TABLE} (atc)")

    conn.commit()
