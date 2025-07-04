import os
from collections import defaultdict
from datetime import datetime
from docx import Document
from docx.shared import RGBColor, Cm
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

    # Marges en logo
    try:
        section = doc.sections[0]
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)

        header = section.header
        header_para = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        header_para.alignment = 2  # Rechts uitlijnen
        run = header_para.add_run()
        logo_path = os.path.join("Data", "logo_apotheek_rgb.jpg")
        if os.path.exists(logo_path):
            run.add_picture(logo_path, width=Cm(4))
        else:
            print(f"Waarschuwing: Logo niet gevonden op {logo_path}")
    except Exception as e:
        print(f"Waarschuwing: Fout bij toevoegen van logo: {str(e)}")

    # Hoofdtitel
    doc.add_heading(f"Medicatie Review - Afdeling {afdeling}", level=1)
    doc.paragraphs[-1].runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0x80)

    vandaag = datetime.today().strftime("%d-%m-%Y")

    for patiënt in patiënten_data:
        heading = doc.add_heading(f"{patiënt['naam']}", level=2)
        heading.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0x80)

        # Arts, apotheker, datum
        para = doc.add_paragraph()
        for label, value in [("Arts:", ""), ("Apotheker:", ""), ("Datum:", vandaag)]:
            run = para.add_run(f"{label} ")
            run.bold = True
            para.add_run(f"{value}\n")

        # STOPP criteria
        heading = doc.add_heading("STOPP-criteria:", level=3)
        heading.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0x80)

        if patiënt["stopp"]:
            table = doc.add_table(rows=1, cols=5)
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            headers = ["Criteriumcode", "Categorie", "Beschrijving", "Argument", "Getriggerd door"]
            for i, text in enumerate(headers):
                run = hdr_cells[i].paragraphs[0].add_run(text)
                run.bold = True

            for item in patiënt["stopp"]:
                row_cells = table.add_row().cells
                row_cells[0].text = item['id']
                row_cells[1].text = item['category']
                row_cells[2].text = item['description']
                row_cells[3].text = item['argument']
                row_cells[4].text = item['triggering_medicines']
        else:
            doc.add_paragraph("Geen STOPP-criteria getriggerd.")

        # Dubbelmedicatie
        heading = doc.add_heading("Dubbelmedicatie:", level=3)
        heading.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0x80)

        if patiënt["dubbelmedicatie"]:
            for item in patiënt["dubbelmedicatie"]:
                doc.add_paragraph(f"Groep: {item['groep']}", style='List Bullet')
                doc.add_paragraph(f"Middelen: {', '.join(item['middelen'])}")
        else:
            doc.add_paragraph("Geen dubbelmedicatie gevonden.")

        # ACB-score
        heading = doc.add_heading("Anticholinerge belastingscore (ACB-score):", level=3)
        heading.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0x80)
        score, interpretatie, middelen_met_bijdrage = patiënt["acb"]
        doc.add_paragraph(f"Totale score: {score} ({interpretatie})")
        if middelen_met_bijdrage:
            lijst = ", ".join(f"{m['middel']} (ACB-score: {m['score']})" for m in middelen_met_bijdrage)
            doc.add_paragraph("Bijdragende middelen: " + lijst)

        # Medicatieoverzicht per groep
        heading = doc.add_heading("Medicatieoverzicht:", level=3)
        heading.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0x80)

        groepen_dict = defaultdict(list)
        for gm in patiënt["geneesmiddelen"]:
            jansen_omschrijving = gm["jansen_omschrijving"] if gm["jansen_omschrijving"] else "Overig"
            groepen_dict[jansen_omschrijving].append(gm)

        gesorteerde_keys = sorted(groepen_dict.keys(), key=lambda k: (k == "Overig", k.lower()))

        for jansen_omschrijving in gesorteerde_keys:
            middelen = groepen_dict[jansen_omschrijving]
            heading = doc.add_heading(f"{jansen_omschrijving}", level=4)
            heading.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0x80)

            table = doc.add_table(rows=1, cols=4)
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            headers = ["Geneesmiddel", "Geneesmiddelgroep", "Gebruik", "Opmerking"]
            for i, text in enumerate(headers):
                run = hdr_cells[i].paragraphs[0].add_run(text)
                run.bold = True

            for gm in middelen:
                row_cells = table.add_row().cells
                row_cells[0].text = gm["clean"]
                row_cells[1].text = gm["groep"] if gm["groep"] else "-"
                row_cells[2].text = gm["gebruik"]
                row_cells[3].text = gm["opmerking"]

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
            fk_naam, fk_groep, atc_groep, atc_omschrijving, jansen_omschrijving = parse_medimo.match_to_fk_database(
                gm["SPKode"], atc_db_path="ATC_groepen.db"
            ) if gm["SPKode"] else (None, None, None, None, None)
            
            gm["groep"] = fk_groep
            gm["atc_groep"] = atc_groep
            gm["atc_omschrijving"] = atc_omschrijving
            gm["jansen_omschrijving"] = jansen_omschrijving

            # Alleen toevoegen aan medicatielijst als een herkenbare naam beschikbaar is
            medicatielijst.append(fk_naam if fk_naam else gm["clean"])
            middelen_clean.append(gm)

        leeftijd = 75  # Of dynamisch uitlezen indien beschikbaar
        stopp = check_stopp_criteria(medicatielijst, leeftijd)
        acb_score, interpretatie, middelen_met_bijdrage = bereken_acb_score(medicatielijst)
        acb = (acb_score, interpretatie, middelen_met_bijdrage)
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