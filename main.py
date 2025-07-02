import os
import sqlite3
from collections import defaultdict
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from Parsers import parse_medimo
from START_STOP.check_start_stop import check_stopp_criteria
from Anticholinerge_Score.check_acb import bereken_acb_score
from Dubbelmedicatie.check_dubbelmedicatie import check_dubbelmedicatie

def maak_in_klapbare_heading(paragraph, text):
    run = paragraph.add_run(text)
    rPr = run._r.get_or_add_rPr()
    rStyle = OxmlElement('w:rStyle')
    rStyle.set(qn('w:val'), 'Heading3')
    rPr.append(rStyle)

def genereer_word_document(patiënten_data, afdeling):
    doc = Document()
    doc.add_heading(f"Medicatie Review - Afdeling {afdeling}", level=1)

    for patiënt in patiënten_data:
        doc.add_heading(f"{patiënt['naam']}", level=2)

        # STOPP criteria
        doc.add_heading("STOPP-criteria:", level=3)
        if patiënt["stopp"]:
            table = doc.add_table(rows=1, cols=2)
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'Criterium'
            hdr_cells[1].text = 'Getriggerd door'

            for item in patiënt["stopp"]:
                row_cells = table.add_row().cells
                row_cells[0].text = item['description']
                row_cells[1].text = ", ".join(item['triggering_medicines'])
        else:
            doc.add_paragraph("Geen STOPP-criteria getriggerd.")

        # ACB-score
        score, interpretatie = patiënt["acb"]
        doc.add_heading("ACB-score:", level=3)
        doc.add_paragraph(f"Totale score: {score} ({interpretatie})")

        # Dubbelmedicatie
        doc.add_heading("Dubbelmedicatie:", level=3)
        if patiënt["dubbelmedicatie"]:
            for item in patiënt["dubbelmedicatie"]:
                doc.add_paragraph(f"Groep: {item['groep']}", style='List Bullet')
                doc.add_paragraph(f"Middelen: {', '.join(item['middelen'])}")
        else:
            doc.add_paragraph("Geen dubbelmedicatie gevonden.")

        # Medicatieoverzicht per groep
        doc.add_heading("Medicatieoverzicht:", level=3)
        groepen_dict = defaultdict(list)
        geen_groep = []

        for gm in patiënt["geneesmiddelen"]:
            if gm["groep"]:
                groepen_dict[gm["groep"]].append(gm)
            else:
                geen_groep.append(gm)

        for groep, middelen in groepen_dict.items():
            doc.add_heading(f"Groep: {groep}", level=4)
            table = doc.add_table(rows=1, cols=3)
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'Geneesmiddel'
            hdr_cells[1].text = 'Gebruik'
            hdr_cells[2].text = 'Opmerking'

            for gm in middelen:
                row_cells = table.add_row().cells
                row_cells[0].text = gm["clean"]
                row_cells[1].text = gm["gebruik"]
                row_cells[2].text = gm["opmerking"]

        if geen_groep:
            doc.add_heading("Middelen zonder groep:", level=4)
            for gm in geen_groep:
                doc.add_paragraph(f"{gm['clean']} | Gebruik: {gm['gebruik']} | Opmerking: {gm['opmerking']}")

        doc.add_paragraph("Opmerking apotheker:\n")

    os.makedirs("Output", exist_ok=True)
    doc_path = f"Output/MedicatieReview_{afdeling}.docx"
    doc.save(doc_path)
    print(f"Word-document opgeslagen als: {doc_path}")

def main():
    data, db_spkodes, afdeling = parse_medimo.run_parser()

    patiënten_data = []
    for patiënt in data:
        naam = patiënt["patiënt"]

        middelen_clean = []
        medicatielijst = []
        for gm in patiënt["geneesmiddelen"]:
            fk_naam, fk_groep = parse_medimo.match_to_fk_database(gm["SPKode"]) if gm["SPKode"] else (None, None)
            gm["groep"] = fk_groep
            medicatielijst.append(fk_naam if fk_naam else gm["clean"])
            middelen_clean.append(gm)

        leeftijd = 75  # Of dynamisch uitlezen indien beschikbaar
        stopp = check_stopp_criteria(medicatielijst, leeftijd)
        acb = bereken_acb_score(medicatielijst)
        dubbel = check_dubbelmedicatie(medicatielijst)

        patiënten_data.append({
            "naam": naam,
            "geneesmiddelen": middelen_clean,
            "stopp": stopp,
            "acb": acb,
            "dubbelmedicatie": dubbel
        })

    genereer_word_document(patiënten_data, afdeling)

if __name__ == "__main__":
    main()