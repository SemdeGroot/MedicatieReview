import os
import json
import time
from typing import List, Dict, Tuple, Optional
import locale
from datetime import datetime

# ===== Medimo Parser =====
from Parsers import parse_medimo

# ===== Externe analyses  =====
from START_STOP.check_start_stop import check_stopp_criteria
from Anticholinerge_Score.check_acb import bereken_acb_score
from Dubbelmedicatie.check_dubbelmedicatie import check_dubbelmedicatie
from WordExport.genereer_docx import genereer_word_document

def _sanitize(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_") or "Onbekend"

def _as_str(x, default=""):
    """Zachte cast naar string (voorkomt typefouten)."""
    if x is None:
        return default
    try:
        s = str(x)
    except Exception:
        return default
    return s

def main(
    input_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    progress_path: Optional[str] = None,
    cancel_flag_path: Optional[str] = None,
) -> None:
    """
    Per-run paden (voor web) óf default legacy paden (standalone).
    """
    project_root = os.path.dirname(os.path.abspath(__file__))
    data_dir  = os.path.join(project_root, "Data")
    out_dir   = os.path.join(project_root, "Output")
    temp_dir  = os.path.join(data_dir, "Temp")

    input_path      = input_path      or os.path.join(data_dir, "medimo_input.txt")
    output_dir      = output_dir      or out_dir
    progress_path   = progress_path   or os.path.join(temp_dir, "progress.json")  # enkel voor compat; run_parser gebruikt eigen progress_path
    cancel_flag_path= cancel_flag_path or os.path.join(temp_dir, "cancel.flag")

    os.makedirs(output_dir, exist_ok=True)

    # >>> Belangrijk: run_parser schrijft alleen naar de MEEGEGEVEN paden <<<
    data, afdeling = parse_medimo.run_parser(
        input_path=input_path,
        progress_path=progress_path,         # in web-flow: .../Temp/<run_id>/progress.json
        cancel_flag_path=cancel_flag_path,   # in web-flow: .../Temp/<run_id>/cancel.flag
    )

    # Stel Nederlandse locale in (werkt op de meeste systemen)
    try:
        locale.setlocale(locale.LC_TIME, 'nl_NL.UTF-8')
    except locale.Error:
        # fallback als locale niet beschikbaar is (Windows of sommige servers)
        pass

    # Analyses per patiënt
    patiënten_data: List[Dict] = []
    for patiënt in data:
        naam = patiënt.get("patiënt", "Onbekend")
        middelen_clean = []
        for gm in patiënt.get("geneesmiddelen", []):
            middelen_clean.append(gm)

        leeftijd = patiënt.get("leeftijd", 75)
        stopp = check_stopp_criteria(middelen_clean, leeftijd)
        acb_score, interpretatie, middelen_met_bijdrage = bereken_acb_score(middelen_clean)
        acb = (acb_score, interpretatie, middelen_met_bijdrage)
        dubbel = check_dubbelmedicatie(middelen_clean)

        patiënten_data.append({
            "naam": naam,
            "geneesmiddelen": middelen_clean,
            "stopp": stopp,
            "acb": acb,
            "dubbelmedicatie": dubbel
        })

    # Bestandsnaam met afdeling (zoals je oude gedrag)
    safe_afdeling = _sanitize(afdeling or "Onbekend")
    output_path = os.path.join(output_dir, f"MedicatieReview_{_as_str(afdeling)}_{datetime.today().strftime('%b%Y')}.docx")

    # Laat je exporter nu óók output_path accepteren
    try:
        genereer_word_document(patiënten_data, afdeling, output_path=output_path)
    except TypeError:
        # Valt terug op oude signature en schrijft naar Output/...
        genereer_word_document(patiënten_data, afdeling)

if __name__ == "__main__":
    print("Bezig met analyseren...")
    main()
    print("Klaar! Word-document in Output/")