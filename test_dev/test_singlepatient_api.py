import json
import pathlib
import requests

URL = "http://127.0.0.1:8001/api/review"

API_KEY = "xxx"   # <-- vul hier jouw key in

payload = {
    "text": pathlib.Path("raw_data/medimo_single_patient.txt").read_text(encoding="utf-8"),
    "source": "medimo",
    "scope": "patient",
    "geboortedatum": "1942-11-07",
}

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
}

with requests.post(URL, json=payload, headers=headers, stream=True) as r:
    r.raise_for_status()

    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue

        obj = json.loads(line)
        print(obj)

        if obj.get("type") == "result":
            pathlib.Path("raw_data/result_single_patient.json").write_text(
                json.dumps(obj, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print("Saved raw_data/result_single_patient.json")
